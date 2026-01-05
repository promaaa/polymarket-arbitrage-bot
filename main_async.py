#!/usr/bin/env python3
"""
Polymarket Arbitrage Bot - High-Performance Async Version

Optimizations:
1. Async/await for concurrent API calls
2. WebSocket for real-time price updates
3. Connection pooling
4. Response caching
"""
import argparse
import asyncio
import logging
import json
import os
import signal
from datetime import datetime
from typing import Optional, Dict, List

from config import Config
from async_scanner import AsyncMarketScanner, AsyncMockScanner
from websocket_client import PriceWebSocket, MockPriceWebSocket
from arbitrage_detector import ArbitrageDetector
from paper_trader import PaperTrader
from market_types import Market, Token, ArbitrageOpportunity

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


class AsyncArbitrageBot:
    """
    High-performance async arbitrage bot.
    
    Uses async scanning and WebSocket for maximum speed.
    """
    
    def __init__(self, simulate: bool = False, auto_trade: bool = True, use_websocket: bool = True):
        """
        Initialize async bot.
        
        Args:
            simulate: Use mock data
            auto_trade: Automatically execute trades
            use_websocket: Use WebSocket for real-time updates
        """
        self.simulate = simulate
        self.auto_trade = auto_trade
        self.use_websocket = use_websocket
        
        # Components
        if simulate:
            self.scanner = AsyncMockScanner()
            logger.info("Using async mock scanner")
        else:
            self.scanner = AsyncMarketScanner(cache_ttl=0.5)
            logger.info("Using async live scanner")
        
        self.detector = ArbitrageDetector()
        self.trader = PaperTrader()
        
        # WebSocket (optional)
        self.ws_client: Optional[PriceWebSocket] = None
        self._markets: Dict[str, Market] = {}
        self._token_to_market: Dict[str, Market] = {}
        
        # State
        self.running = False
        self.scan_count = 0
        self.last_scan = None
        self.recent_opportunities: List[ArbitrageOpportunity] = []
        
        # Performance stats
        self.total_scan_time = 0.0
        self.min_scan_time = float('inf')
        self.max_scan_time = 0.0
    
    async def start(self):
        """Start the bot."""
        self.running = True
        
        # Initial market fetch
        markets = await self.scanner.scan_all_markets()
        
        for market in markets:
            self._markets[market.id] = market
            for token in market.tokens:
                self._token_to_market[token.token_id] = market
        
        logger.info(f"Loaded {len(markets)} markets")
        
        # Start WebSocket if enabled
        if self.use_websocket and not self.simulate:
            await self._start_websocket()
    
    async def _start_websocket(self):
        """Initialize and start WebSocket connection."""
        self.ws_client = MockPriceWebSocket(self._on_price_update) if self.simulate else PriceWebSocket(self._on_price_update)
        
        await self.ws_client.connect()
        
        # Subscribe to all tokens
        token_ids = list(self._token_to_market.keys())
        await self.ws_client.subscribe(token_ids)
        
        logger.info(f"WebSocket subscribed to {len(token_ids)} tokens")
    
    def _on_price_update(self, token_id: str, price: float):
        """Handle real-time price update from WebSocket."""
        market = self._token_to_market.get(token_id)
        if not market:
            return
        
        # Update token price
        for token in market.tokens:
            if token.token_id == token_id:
                token.price = price
                break
        
        # Check for arbitrage immediately
        opp = self.detector.detect(market)
        if opp:
            logger.info(f"[WS] {opp}")
            self.recent_opportunities.append(opp)
            self.recent_opportunities = self.recent_opportunities[-100:]
            
            if self.auto_trade:
                position = self.trader.execute_arbitrage(opp)
                if position:
                    logger.info(f"[WS] Executed: {position.id}")
    
    async def scan_once(self) -> List[ArbitrageOpportunity]:
        """Perform a single async scan cycle."""
        start_time = asyncio.get_event_loop().time()
        
        try:
            # Fetch markets with prices
            markets = await self.scanner.scan_all_markets()
            
            # Update local cache
            for market in markets:
                self._markets[market.id] = market
                for token in market.tokens:
                    self._token_to_market[token.token_id] = market
            
            # Detect opportunities
            opportunities = self.detector.scan_markets(markets)
            
            self.scan_count += 1
            self.last_scan = datetime.now()
            
            # Update stats
            scan_time = asyncio.get_event_loop().time() - start_time
            self.total_scan_time += scan_time
            self.min_scan_time = min(self.min_scan_time, scan_time)
            self.max_scan_time = max(self.max_scan_time, scan_time)
            
            # Process opportunities
            for opp in opportunities:
                self.recent_opportunities.append(opp)
                self.recent_opportunities = self.recent_opportunities[-100:]
                
                if self.auto_trade:
                    position = self.trader.execute_arbitrage(opp)
                    if position:
                        logger.info(f"Executed: {position.id}")
            
            return opportunities
            
        except Exception as e:
            logger.error(f"Scan error: {e}")
            return []
    
    async def run_scanner(self):
        """Run continuous async scanning loop."""
        logger.info(f"Starting async scanner (interval: {Config.SCAN_INTERVAL}s)")
        
        while self.running:
            await self.scan_once()
            await asyncio.sleep(Config.SCAN_INTERVAL)
    
    async def run_hybrid(self):
        """
        Run hybrid mode: WebSocket + periodic polling.
        
        WebSocket provides real-time updates, polling catches missed updates
        and discovers new markets.
        """
        logger.info("Starting hybrid mode (WebSocket + polling)")
        
        async def poll_loop():
            while self.running:
                await asyncio.sleep(Config.SCAN_INTERVAL * 2)  # Poll less frequently
                await self.scan_once()
        
        async def ws_loop():
            if self.ws_client:
                await self.ws_client.listen()
        
        # Run both loops concurrently
        await asyncio.gather(
            poll_loop(),
            ws_loop(),
            return_exceptions=True,
        )
    
    async def stop(self):
        """Stop the bot gracefully."""
        self.running = False
        
        if self.ws_client:
            await self.ws_client.close()
        
        await self.scanner.close()
        
        logger.info("Bot stopped")
    
    async def monitor_external_scanner(self):
        """Monitor externally generated opportunities.json (from Rust scanner)."""
        logger.info("Monitoring opportunities.json from Rust scanner...")
        self.running = True
        
        last_mtime = 0
        file_path = "opportunities.json"
        
        while self.running:
            try:
                if os.path.exists(file_path):
                    mtime = os.path.getmtime(file_path)
                    if mtime > last_mtime:
                        last_mtime = mtime
                        try:
                            with open(file_path, "r") as f:
                                data = json.load(f)
                            
                            self.recent_opportunities = data.get("opportunities", [])
                            # Sort by profit %
                            self.recent_opportunities.sort(
                                key=lambda x: x.get("profit_percentage", 0), 
                                reverse=True
                            )
                            logger.info(f"Loaded {len(self.recent_opportunities)} opportunities from Rust scanner")
                        except json.JSONDecodeError:
                            pass # File might be partial write
                
            except Exception as e:
                logger.error(f"External scanner monitor error: {e}")
            
            await asyncio.sleep(1)

    def get_status(self) -> dict:
        """Get current bot status."""
        stats = self.trader.get_stats()
        # Handle case where scanner is external
        scanner_stats = self.scanner.get_stats() if hasattr(self.scanner, 'get_stats') else {}
        
        avg_scan_time = self.total_scan_time / max(1, self.scan_count)
        
        return {
            "running": self.running,
            "simulate": self.simulate,
            "use_websocket": self.use_websocket,
            "scan_count": self.scan_count,
            "last_scan": self.last_scan.isoformat() if self.last_scan else None,
            "stats": stats.to_dict(),
            "detector": self.detector.get_stats(),
            "scanner": scanner_stats,
            "performance": {
                "avg_scan_ms": round(avg_scan_time * 1000, 1),
                "min_scan_ms": round(self.min_scan_time * 1000, 1) if self.min_scan_time != float('inf') else 0,
                "max_scan_ms": round(self.max_scan_time * 1000, 1),
            },
            "websocket": self.ws_client.get_stats() if self.ws_client else None,
        }


async def main_async():
    """Async main entry point."""
    parser = argparse.ArgumentParser(
        description="Polymarket Arbitrage Bot - High Performance Async Version"
    )
    parser.add_argument("--simulate", "-s", action="store_true", help="Use simulated data")
    parser.add_argument("--dashboard", "-d", action="store_true", help="Start web dashboard")
    parser.add_argument("--no-trade", action="store_true", help="Detect only, don't trade")
    parser.add_argument("--no-websocket", action="store_true", help="Disable WebSocket, use polling only")
    parser.add_argument("--once", action="store_true", help="Single scan and exit")
    parser.add_argument("--benchmark", "-b", action="store_true", help="Run benchmark mode")
    parser.add_argument("--rust", action="store_true", help="Use external Rust scanner data")
    
    args = parser.parse_args()
    
    # Create bot
    bot = AsyncArbitrageBot(
        simulate=args.simulate,
        auto_trade=not args.no_trade,
        use_websocket=not args.no_websocket,
    )
    
    # Print banner
    print("\n" + "=" * 60)
    print("🚀 Polymarket Arbitrage Bot - ASYNC VERSION")
    print("=" * 60)
    print(f"Mode: {'SIMULATION' if args.simulate else 'LIVE'}")
    print(f"Auto-trade: {not args.no_trade}")
    print(f"WebSocket: {not args.no_websocket}")
    print(f"Dashboard: {args.dashboard}")
    print(f"Initial balance: ${Config.INITIAL_BALANCE:,.2f}")
    print(f"Trade size: ${Config.TRADE_SIZE:,.2f}")
    print("=" * 60 + "\n")
    
    # Handle shutdown
    loop = asyncio.get_event_loop()
    
    def signal_handler():
        logger.info("Shutdown signal received")
        asyncio.create_task(bot.stop())
    
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)
    
    try:
        await bot.start()
        
        if args.benchmark:
            # Benchmark mode - run 100 scans
            print("\n🏃 Running benchmark (100 scans)...\n")
            for i in range(100):
                await bot.scan_once()
            
            status = bot.get_status()
            perf = status["performance"]
            scanner = status["scanner"]
            
            print("\n📊 Benchmark Results:")
            print(f"  Scans: {status['scan_count']}")
            print(f"  Avg scan time: {perf['avg_scan_ms']:.1f}ms")
            print(f"  Min scan time: {perf['min_scan_ms']:.1f}ms")
            print(f"  Max scan time: {perf['max_scan_ms']:.1f}ms")
            print(f"  API calls: {scanner['api_calls']}")
            print(f"  Cache hits: {scanner['cache_hits']}")
            print(f"  Cache hit rate: {scanner['cache_hit_rate']*100:.1f}%")
            print(f"  Opportunities: {status['detector']['opportunities_found']}")
            
        elif args.once:
            opportunities = await bot.scan_once()
            status = bot.get_status()
            
            print(f"\nFound {len(opportunities)} opportunities")
            print(f"Scan time: {status['performance']['avg_scan_ms']:.1f}ms")
            print(f"Balance: ${status['stats']['current_balance']:,.2f}")
            
        else:
            # Continuous mode
            print("Press Ctrl+C to stop\n")
            
            # Start dashboard if requested
            if args.dashboard:
                from async_dashboard import AsyncDashboard
                dashboard = AsyncDashboard(bot)
                dashboard.run_in_thread()
                print(f"📊 Dashboard: http://localhost:{Config.DASHBOARD_PORT}\n")
            
            if args.rust:
                await bot.monitor_external_scanner()
            elif bot.use_websocket:
                await bot.run_hybrid()
            else:
                await bot.run_scanner()
    
    finally:
        await bot.stop()


def main():
    """Entry point."""
    asyncio.run(main_async())


if __name__ == "__main__":
    main()

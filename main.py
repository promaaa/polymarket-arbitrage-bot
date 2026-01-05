#!/usr/bin/env python3
"""
Polymarket Arbitrage Bot - Main Entry Point

A paper trading prototype that detects arbitrage opportunities
on Polymarket binary markets when YES + NO prices sum to < $1.
"""
import argparse
import logging
import time
import threading
from datetime import datetime

from config import Config
from market_scanner import MarketScanner, MockMarketScanner
from arbitrage_detector import ArbitrageDetector
from paper_trader import PaperTrader
from dashboard import create_dashboard

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


class ArbitrageBot:
    """Main bot orchestrating scanning, detection, and trading."""
    
    def __init__(self, simulate: bool = False, auto_trade: bool = True):
        """
        Initialize the bot.
        
        Args:
            simulate: Use mock data instead of live APIs
            auto_trade: Automatically execute trades on opportunities
        """
        self.simulate = simulate
        self.auto_trade = auto_trade
        
        # Initialize components
        if simulate:
            self.scanner = MockMarketScanner()
            logger.info("Using mock market scanner (simulation mode)")
        else:
            self.scanner = MarketScanner()
            logger.info("Using live Polymarket APIs")
        
        self.detector = ArbitrageDetector()
        self.trader = PaperTrader()
        
        self.running = False
        self.scan_count = 0
        self.last_scan = None
        
        # Dashboard app reference (set when dashboard is started)
        self.app = None
    
    def scan_once(self):
        """Perform a single scan cycle."""
        try:
            # Fetch markets with prices
            markets = self.scanner.scan_all_markets()
            
            # Detect arbitrage opportunities
            opportunities = self.detector.scan_markets(markets)
            
            self.scan_count += 1
            self.last_scan = datetime.now()
            
            # Update dashboard app if running
            if self.app:
                self.app.scan_count = self.scan_count
                self.app.last_scan = self.last_scan
            
            # Process opportunities
            for opp in opportunities:
                logger.info(f"Found: {opp}")
                
                # Update dashboard
                if self.app:
                    self.app.recent_opportunities.append(opp)
                    # Keep only last 100 opportunities
                    self.app.recent_opportunities = self.app.recent_opportunities[-100:]
                
                # Auto-trade if enabled
                if self.auto_trade:
                    position = self.trader.execute_arbitrage(opp)
                    if position:
                        logger.info(f"Opened position: {position.id}")
            
            return opportunities
            
        except Exception as e:
            logger.error(f"Scan error: {e}")
            return []
    
    def run_scanner(self):
        """Run the continuous scanning loop."""
        logger.info(f"Starting scanner (interval: {Config.SCAN_INTERVAL}s)")
        
        self.running = True
        while self.running:
            self.scan_once()
            time.sleep(Config.SCAN_INTERVAL)
    
    def stop(self):
        """Stop the bot."""
        self.running = False
        logger.info("Bot stopped")
    
    def get_status(self) -> dict:
        """Get current bot status."""
        stats = self.trader.get_stats()
        return {
            "running": self.running,
            "simulate": self.simulate,
            "scan_count": self.scan_count,
            "last_scan": self.last_scan.isoformat() if self.last_scan else None,
            "stats": stats.to_dict(),
            "detector": self.detector.get_stats(),
        }


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Polymarket Arbitrage Bot - Paper Trading Prototype"
    )
    parser.add_argument(
        "--simulate", "-s",
        action="store_true",
        help="Use simulated market data with artificial arbitrage"
    )
    parser.add_argument(
        "--dashboard", "-d",
        action="store_true",
        help="Start the web dashboard"
    )
    parser.add_argument(
        "--no-trade",
        action="store_true",
        help="Detect opportunities but don't execute trades"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single scan and exit"
    )
    
    args = parser.parse_args()
    
    # Create bot
    bot = ArbitrageBot(
        simulate=args.simulate,
        auto_trade=not args.no_trade,
    )
    
    # Print config
    print("\n" + "=" * 60)
    print("🎯 Polymarket Arbitrage Bot")
    print("=" * 60)
    print(f"Mode: {'SIMULATION' if args.simulate else 'LIVE'}")
    print(f"Auto-trade: {not args.no_trade}")
    print(f"Initial balance: ${Config.INITIAL_BALANCE:,.2f}")
    print(f"Trade size: ${Config.TRADE_SIZE:,.2f}")
    print(f"Min profit threshold: ${Config.MIN_PROFIT_THRESHOLD:.3f}")
    print(f"Target markets: {', '.join(Config.TARGET_MARKETS)}")
    print("=" * 60 + "\n")
    
    if args.once:
        # Single scan mode
        opportunities = bot.scan_once()
        print(f"\nFound {len(opportunities)} opportunities")
        status = bot.get_status()
        print(f"Balance: ${status['stats']['current_balance']:,.2f}")
        return
    
    if args.dashboard:
        # Start dashboard with scanner in background
        bot.app = create_dashboard(bot.trader, bot.scanner, bot.detector)
        
        # Start scanner in background thread
        scanner_thread = threading.Thread(target=bot.run_scanner, daemon=True)
        scanner_thread.start()
        
        print(f"📊 Dashboard: http://localhost:{Config.DASHBOARD_PORT}")
        print("Press Ctrl+C to stop\n")
        
        try:
            bot.app.run(
                host="0.0.0.0",
                port=Config.DASHBOARD_PORT,
                debug=False,
                threaded=True,
            )
        except KeyboardInterrupt:
            bot.stop()
    else:
        # Console-only mode
        print("Press Ctrl+C to stop\n")
        
        try:
            bot.run_scanner()
        except KeyboardInterrupt:
            bot.stop()


if __name__ == "__main__":
    main()

"""
Async Market Scanner - High-performance market data fetcher using asyncio.

Optimizations:
1. Concurrent API calls using aiohttp
2. Connection pooling with keep-alive
3. Batch price fetching
4. Response caching with TTL
"""
import asyncio
import aiohttp
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import logging
import time

from config import Config
from market_types import Market, Token

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Cached data with expiration."""
    data: Any
    expires_at: float
    
    @property
    def is_valid(self) -> bool:
        return time.time() < self.expires_at


class AsyncMarketScanner:
    """
    High-performance async market scanner.
    
    Uses aiohttp for concurrent requests and implements:
    - Connection pooling
    - Response caching
    - Batch API calls
    """
    
    def __init__(self, cache_ttl: float = 1.0, max_connections: int = 100):
        """
        Initialize async scanner.
        
        Args:
            cache_ttl: Cache time-to-live in seconds
            max_connections: Maximum concurrent connections
        """
        self.gamma_url = Config.GAMMA_API_URL
        self.clob_url = Config.CLOB_API_URL
        self.target_keywords = Config.TARGET_MARKETS
        
        self.cache_ttl = cache_ttl
        self.max_connections = max_connections
        
        # Caches
        self._markets_cache: Optional[CacheEntry] = None
        self._price_cache: Dict[str, CacheEntry] = {}
        
        # Session - created lazily
        self._session: Optional[aiohttp.ClientSession] = None
        self._connector: Optional[aiohttp.TCPConnector] = None
        
        # Stats
        self.api_calls = 0
        self.cache_hits = 0
        self.last_scan_duration = 0.0
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session with connection pooling."""
        if self._session is None or self._session.closed:
            self._connector = aiohttp.TCPConnector(
                limit=self.max_connections,
                limit_per_host=50,
                keepalive_timeout=30,
                enable_cleanup_closed=True,
            )
            self._session = aiohttp.ClientSession(
                connector=self._connector,
                headers={
                    "User-Agent": "PolymarketArbitrageBot/2.0",
                    "Accept": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=10, connect=5),
            )
        return self._session
    
    async def close(self):
        """Close the session and connector."""
        if self._session and not self._session.closed:
            await self._session.close()
        if self._connector:
            await self._connector.close()
    
    async def get_active_markets(self, limit: int = 100) -> List[Market]:
        """
        Fetch active binary markets from Gamma API.
        
        Uses caching to reduce API calls.
        """
        # Check cache
        if self._markets_cache and self._markets_cache.is_valid:
            self.cache_hits += 1
            return self._markets_cache.data
        
        session = await self._get_session()
        
        try:
            self.api_calls += 1
            async with session.get(
                f"{self.gamma_url}/markets",
                params={
                    "active": "true",
                    "closed": "false",
                    "limit": limit,
                },
            ) as response:
                response.raise_for_status()
                data = await response.json()
            
            markets = []
            for item in data:
                market = self._parse_market(item)
                if market and self._matches_filter(market):
                    markets.append(market)
            
            # Cache results
            self._markets_cache = CacheEntry(
                data=markets,
                expires_at=time.time() + self.cache_ttl * 5,  # Markets change slower
            )
            
            logger.debug(f"Fetched {len(markets)} markets")
            return markets
            
        except aiohttp.ClientError as e:
            logger.error(f"Failed to fetch markets: {e}")
            return self._markets_cache.data if self._markets_cache else []
    
    async def get_token_price(self, token_id: str) -> float:
        """
        Fetch price for a single token.
        
        Uses caching to reduce API calls.
        """
        # Check cache
        cache_entry = self._price_cache.get(token_id)
        if cache_entry and cache_entry.is_valid:
            self.cache_hits += 1
            return cache_entry.data
        
        session = await self._get_session()
        
        try:
            self.api_calls += 1
            async with session.get(
                f"{self.clob_url}/price",
                params={
                    "token_id": token_id,
                    "side": "buy",
                },
            ) as response:
                response.raise_for_status()
                data = await response.json()
                price = float(data.get("price", 0))
            
            # Cache result
            self._price_cache[token_id] = CacheEntry(
                data=price,
                expires_at=time.time() + self.cache_ttl,
            )
            
            return price
            
        except aiohttp.ClientError as e:
            logger.warning(f"Failed to get price for {token_id}: {e}")
            return cache_entry.data if cache_entry else 0.0
    
    async def get_prices_batch(self, token_ids: List[str]) -> Dict[str, float]:
        """
        Fetch prices for multiple tokens concurrently.
        
        This is the key optimization - fetching all prices in parallel.
        """
        # Separate cached and uncached tokens
        results = {}
        to_fetch = []
        
        for token_id in token_ids:
            cache_entry = self._price_cache.get(token_id)
            if cache_entry and cache_entry.is_valid:
                results[token_id] = cache_entry.data
                self.cache_hits += 1
            else:
                to_fetch.append(token_id)
        
        if not to_fetch:
            return results
        
        # Fetch all uncached prices concurrently
        session = await self._get_session()
        
        async def fetch_price(token_id: str) -> Tuple[str, float]:
            try:
                self.api_calls += 1
                async with session.get(
                    f"{self.clob_url}/price",
                    params={"token_id": token_id, "side": "buy"},
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        price = float(data.get("price", 0))
                    else:
                        price = 0.0
                
                # Cache result
                self._price_cache[token_id] = CacheEntry(
                    data=price,
                    expires_at=time.time() + self.cache_ttl,
                )
                return token_id, price
                
            except Exception as e:
                logger.warning(f"Price fetch error for {token_id}: {e}")
                return token_id, 0.0
        
        # Execute all fetches concurrently
        tasks = [fetch_price(tid) for tid in to_fetch]
        fetched = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in fetched:
            if isinstance(result, tuple):
                token_id, price = result
                results[token_id] = price
        
        return results
    
    async def scan_all_markets(self) -> List[Market]:
        """
        Fetch all active markets and their prices concurrently.
        
        This is the main optimized scanning method.
        """
        start_time = time.time()
        
        # Fetch markets
        markets = await self.get_active_markets()
        
        if not markets:
            return []
        
        # Collect all token IDs
        token_ids = []
        token_to_market: Dict[str, Tuple[Market, Token]] = {}
        
        for market in markets:
            for token in market.tokens:
                if token.token_id:
                    token_ids.append(token.token_id)
                    token_to_market[token.token_id] = (market, token)
        
        # Fetch all prices concurrently
        prices = await self.get_prices_batch(token_ids)
        
        # Update market tokens with prices
        for token_id, price in prices.items():
            if token_id in token_to_market:
                _, token = token_to_market[token_id]
                token.price = price
        
        # Filter markets with valid prices
        valid_markets = [
            m for m in markets
            if m.yes_price > 0 and m.no_price > 0
        ]
        
        self.last_scan_duration = time.time() - start_time
        logger.info(
            f"Scanned {len(valid_markets)} markets in {self.last_scan_duration*1000:.1f}ms "
            f"({self.api_calls} API calls, {self.cache_hits} cache hits)"
        )
        
        return valid_markets
    
    def _parse_market(self, data: Dict[str, Any]) -> Optional[Market]:
        """Parse market data from Gamma API response."""
        import json as json_module
        
        try:
            tokens = []
            
            # Try to get token IDs from clobTokenIds (JSON string format)
            clob_ids_raw = data.get("clobTokenIds", "")
            outcome_prices_raw = data.get("outcomePrices", "")
            
            # Parse clobTokenIds - it's a JSON array as a string
            clob_ids = []
            if clob_ids_raw:
                try:
                    clob_ids = json_module.loads(clob_ids_raw) if isinstance(clob_ids_raw, str) else clob_ids_raw
                except json_module.JSONDecodeError:
                    clob_ids = []
            
            # Parse outcomePrices - also a JSON array as string
            outcome_prices = []
            if outcome_prices_raw:
                try:
                    outcome_prices = json_module.loads(outcome_prices_raw) if isinstance(outcome_prices_raw, str) else outcome_prices_raw
                except json_module.JSONDecodeError:
                    outcome_prices = []
            
            # Parse outcomes
            outcomes_raw = data.get("outcomes", "[\"Yes\", \"No\"]")
            try:
                outcomes = json_module.loads(outcomes_raw) if isinstance(outcomes_raw, str) else outcomes_raw
            except json_module.JSONDecodeError:
                outcomes = ["Yes", "No"]
            
            # Build tokens from parsed data
            if len(clob_ids) >= 2 and len(outcomes) >= 2:
                for i in range(min(len(clob_ids), len(outcomes))):
                    price = float(outcome_prices[i]) if i < len(outcome_prices) else 0.0
                    tokens.append(Token(
                        token_id=str(clob_ids[i]).strip(),
                        outcome=str(outcomes[i]),
                        price=price,  # Use the price from outcomePrices
                    ))
            
            if len(tokens) < 2:
                return None
            
            end_date = None
            if data.get("endDate"):
                try:
                    end_date = datetime.fromisoformat(
                        data["endDate"].replace("Z", "+00:00")
                    )
                except (ValueError, AttributeError):
                    pass
            
            return Market(
                id=data.get("id", ""),
                condition_id=data.get("conditionId", ""),
                question=data.get("question", ""),
                slug=data.get("slug", ""),
                tokens=tokens,
                volume=float(data.get("volumeNum", 0) or data.get("volume", 0) or 0),
                liquidity=float(data.get("liquidityNum", 0) or data.get("liquidity", 0) or 0),
                end_date=end_date,
                active=data.get("active", True),
            )
            
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"Failed to parse market: {e}")
            return None
    
    def _matches_filter(self, market: Market) -> bool:
        """Check if market matches target keyword filters."""
        # For live mode, accept all binary markets (we want volume)
        if not self.target_keywords:
            return True
        
        # If filter is set, check for matches
        question_upper = market.question.upper()
        return any(kw in question_upper for kw in self.target_keywords)
    
    def get_stats(self) -> dict:
        """Return scanner statistics."""
        return {
            "api_calls": self.api_calls,
            "cache_hits": self.cache_hits,
            "cache_hit_rate": self.cache_hits / max(1, self.api_calls + self.cache_hits),
            "last_scan_ms": round(self.last_scan_duration * 1000, 1),
            "price_cache_size": len(self._price_cache),
        }
    
    def clear_cache(self):
        """Clear all caches."""
        self._markets_cache = None
        self._price_cache.clear()


class AsyncMockScanner(AsyncMarketScanner):
    """
    Mock async scanner for testing.
    
    Simulates fast responses with artificial arbitrage opportunities.
    """
    
    def __init__(self):
        super().__init__()
        self._mock_markets = self._generate_mock_markets()
        self._scan_count = 0
    
    async def get_active_markets(self, limit: int = 100) -> List[Market]:
        """Return mock markets instantly."""
        await asyncio.sleep(0.001)  # Simulate minimal latency
        return self._mock_markets[:limit]
    
    async def get_prices_batch(self, token_ids: List[str]) -> Dict[str, float]:
        """Generate mock prices with occasional arbitrage."""
        import random
        
        await asyncio.sleep(0.005)  # Simulate 5ms latency
        
        self._scan_count += 1
        prices = {}
        
        for token_id in token_ids:
            if "yes" in token_id:
                if self._scan_count % 2 == 0:
                    # Arbitrage opportunity
                    prices[token_id] = round(random.uniform(0.42, 0.50), 3)
                else:
                    prices[token_id] = round(random.uniform(0.48, 0.52), 3)
            else:
                if self._scan_count % 2 == 0:
                    # Arbitrage opportunity
                    prices[token_id] = round(random.uniform(0.42, 0.50), 3)
                else:
                    prices[token_id] = round(random.uniform(0.48, 0.52), 3)
        
        return prices
    
    def _generate_mock_markets(self) -> List[Market]:
        """Generate mock markets."""
        mock_data = [
            ("BTC above $100k at end of day?", "btc-100k"),
            ("ETH above $4000 in next hour?", "eth-4000"),
            ("SOL above $200 by midnight?", "sol-200"),
            ("XRP above $2.50 today?", "xrp-250"),
            ("BTC volatility > 5% today?", "btc-vol-5"),
            ("DOGE above $0.50?", "doge-50"),
            ("ADA above $1.00?", "ada-100"),
            ("DOT above $20?", "dot-20"),
        ]
        
        markets = []
        for i, (question, slug) in enumerate(mock_data):
            markets.append(Market(
                id=f"mock-{i}",
                condition_id=f"mock-condition-{i}",
                question=question,
                slug=slug,
                tokens=[
                    Token(token_id=f"mock-yes-{i}", outcome="Yes"),
                    Token(token_id=f"mock-no-{i}", outcome="No"),
                ],
                volume=100000 + i * 10000,
                liquidity=50000 + i * 5000,
                active=True,
            ))
        
        return markets

"""
Market Scanner - Fetches market data from Polymarket APIs.
"""
import requests
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

from config import Config
from market_types import Market, Token

logger = logging.getLogger(__name__)


class MarketScanner:
    """Scans Polymarket for binary markets and fetches prices."""
    
    def __init__(self):
        self.gamma_url = Config.GAMMA_API_URL
        self.clob_url = Config.CLOB_API_URL
        self.target_keywords = Config.TARGET_MARKETS
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "PolymarketArbitrageBot/1.0",
            "Accept": "application/json",
        })
    
    def get_active_markets(self, limit: int = 100) -> List[Market]:
        """
        Fetch active binary markets from Gamma API.
        
        Returns markets filtered by target keywords if configured.
        """
        try:
            response = self.session.get(
                f"{self.gamma_url}/markets",
                params={
                    "active": "true",
                    "closed": "false",
                    "limit": limit,
                },
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            
            markets = []
            for item in data:
                market = self._parse_market(item)
                if market and self._matches_filter(market):
                    markets.append(market)
            
            logger.info(f"Fetched {len(markets)} markets matching filters")
            return markets
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch markets: {e}")
            return []
    
    def get_market_prices(self, market: Market) -> Market:
        """
        Fetch current YES/NO prices for a market from CLOB API.
        
        Updates the market's token prices in-place and returns it.
        """
        for token in market.tokens:
            try:
                # Get best bid (what we'd pay to buy)
                response = self.session.get(
                    f"{self.clob_url}/price",
                    params={
                        "token_id": token.token_id,
                        "side": "buy",
                    },
                    timeout=5,
                )
                response.raise_for_status()
                price_data = response.json()
                token.price = float(price_data.get("price", 0))
                
            except requests.RequestException as e:
                logger.warning(f"Failed to get price for token {token.token_id}: {e}")
                token.price = 0.0
        
        return market
    
    def get_orderbook(self, token_id: str) -> Dict[str, Any]:
        """
        Fetch the full orderbook for a token.
        
        Returns dict with 'bids' and 'asks' arrays.
        """
        try:
            response = self.session.get(
                f"{self.clob_url}/book",
                params={"token_id": token_id},
                timeout=5,
            )
            response.raise_for_status()
            return response.json()
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch orderbook: {e}")
            return {"bids": [], "asks": []}
    
    def scan_all_markets(self) -> List[Market]:
        """
        Fetch all active markets and their current prices.
        
        This is the main scanning method that combines market discovery
        with price fetching.
        """
        markets = self.get_active_markets()
        
        for market in markets:
            self.get_market_prices(market)
        
        # Filter out markets with missing prices
        valid_markets = [
            m for m in markets 
            if m.yes_price > 0 and m.no_price > 0
        ]
        
        logger.info(f"Scanned {len(valid_markets)} markets with valid prices")
        return valid_markets
    
    def _parse_market(self, data: Dict[str, Any]) -> Optional[Market]:
        """Parse market data from Gamma API response."""
        try:
            # Extract token IDs - Gamma API uses 'tokens' array
            tokens = []
            token_data = data.get("tokens", [])
            
            if len(token_data) >= 2:
                for t in token_data:
                    tokens.append(Token(
                        token_id=t.get("token_id", ""),
                        outcome=t.get("outcome", ""),
                        price=0.0,
                    ))
            else:
                # Alternative format - check for clobTokenIds
                clob_ids = data.get("clobTokenIds", "")
                if clob_ids:
                    ids = clob_ids.split(",") if isinstance(clob_ids, str) else clob_ids
                    if len(ids) >= 2:
                        tokens = [
                            Token(token_id=ids[0].strip(), outcome="Yes"),
                            Token(token_id=ids[1].strip(), outcome="No"),
                        ]
            
            if len(tokens) < 2:
                return None
            
            # Parse end date if available
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
                volume=float(data.get("volume", 0) or 0),
                liquidity=float(data.get("liquidity", 0) or 0),
                end_date=end_date,
                active=data.get("active", True),
            )
            
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"Failed to parse market: {e}")
            return None
    
    def _matches_filter(self, market: Market) -> bool:
        """Check if market matches target keyword filters."""
        if not self.target_keywords:
            return True
        
        question_upper = market.question.upper()
        return any(kw in question_upper for kw in self.target_keywords)


class MockMarketScanner(MarketScanner):
    """
    Mock scanner for testing with simulated data.
    
    Generates fake markets with artificial arbitrage opportunities.
    """
    
    def __init__(self):
        super().__init__()
        self._mock_markets = self._generate_mock_markets()
        self._scan_count = 0
    
    def get_active_markets(self, limit: int = 100) -> List[Market]:
        """Return mock markets."""
        return self._mock_markets[:limit]
    
    def get_market_prices(self, market: Market) -> Market:
        """Simulate price updates with occasional arbitrage."""
        import random
        
        self._scan_count += 1
        
        # Every few scans, create an arbitrage opportunity
        if self._scan_count % 3 == 0:
            # Arbitrage opportunity: YES + NO < 1.0
            yes_price = round(random.uniform(0.40, 0.55), 3)
            no_price = round(random.uniform(0.40, 0.55), 3)
            # Ensure it's a valid arbitrage
            while yes_price + no_price >= 0.99:
                no_price -= 0.02
        else:
            # Normal pricing: YES + NO ≈ 1.0
            yes_price = round(random.uniform(0.45, 0.55), 3)
            no_price = round(1.0 - yes_price + random.uniform(-0.01, 0.01), 3)
        
        for token in market.tokens:
            if token.outcome.lower() == "yes":
                token.price = yes_price
            else:
                token.price = no_price
        
        return market
    
    def _generate_mock_markets(self) -> List[Market]:
        """Generate a set of mock markets for testing."""
        mock_data = [
            ("BTC above $100k at end of day?", "btc-100k"),
            ("ETH above $4000 in next hour?", "eth-4000"),
            ("SOL above $200 by midnight?", "sol-200"),
            ("XRP above $2.50 today?", "xrp-250"),
            ("BTC volatility > 5% today?", "btc-vol-5"),
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

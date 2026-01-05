"""
Arbitrage Detector - Identifies profitable arbitrage opportunities.
"""
from typing import List, Optional
from datetime import datetime
import logging

from config import Config
from market_types import Market, ArbitrageOpportunity

logger = logging.getLogger(__name__)


class ArbitrageDetector:
    """Detects arbitrage opportunities in binary markets."""
    
    def __init__(self, min_profit_threshold: float = None):
        """
        Initialize the detector.
        
        Args:
            min_profit_threshold: Minimum profit per share to consider.
                                  Defaults to config value.
        """
        self.min_profit_threshold = (
            min_profit_threshold 
            if min_profit_threshold is not None 
            else Config.MIN_PROFIT_THRESHOLD
        )
        self.opportunities_found = 0
    
    def detect(self, market: Market) -> Optional[ArbitrageOpportunity]:
        """
        Check a single market for arbitrage opportunity.
        
        Arbitrage exists when:
            YES_price + NO_price < 1.0 - threshold
        
        Buying both sides guarantees profit = 1.0 - (YES + NO)
        
        Args:
            market: Market with current prices
            
        Returns:
            ArbitrageOpportunity if found, None otherwise
        """
        yes_price = market.yes_price
        no_price = market.no_price
        
        # Skip if prices are invalid
        if yes_price <= 0 or no_price <= 0:
            return None
        
        if yes_price >= 1.0 or no_price >= 1.0:
            return None
        
        combined_cost = yes_price + no_price
        
        # Calculate potential profit
        # One side always pays $1, so profit = $1 - cost
        profit_per_share = 1.0 - combined_cost
        
        # Check if profit exceeds threshold
        if profit_per_share >= self.min_profit_threshold:
            profit_percentage = (profit_per_share / combined_cost) * 100
            
            opportunity = ArbitrageOpportunity(
                market=market,
                yes_price=yes_price,
                no_price=no_price,
                combined_cost=combined_cost,
                profit_per_share=profit_per_share,
                profit_percentage=profit_percentage,
                detected_at=datetime.now(),
            )
            
            self.opportunities_found += 1
            logger.info(f"Arbitrage opportunity #{self.opportunities_found}: {opportunity}")
            
            return opportunity
        
        return None
    
    def scan_markets(self, markets: List[Market]) -> List[ArbitrageOpportunity]:
        """
        Scan multiple markets for arbitrage opportunities.
        
        Args:
            markets: List of markets with current prices
            
        Returns:
            List of detected opportunities, sorted by profit
        """
        opportunities = []
        
        for market in markets:
            opp = self.detect(market)
            if opp:
                opportunities.append(opp)
        
        # Sort by profit percentage (highest first)
        opportunities.sort(key=lambda x: x.profit_percentage, reverse=True)
        
        if opportunities:
            logger.info(f"Found {len(opportunities)} arbitrage opportunities")
        
        return opportunities
    
    def get_stats(self) -> dict:
        """Return detector statistics."""
        return {
            "opportunities_found": self.opportunities_found,
            "min_profit_threshold": self.min_profit_threshold,
        }

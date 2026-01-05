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
    
    def __init__(
        self, 
        min_profit_threshold: float = None,
        min_volume: float = 10000,  # Minimum $10k volume
        min_liquidity: float = 1000,  # Minimum $1k liquidity
    ):
        """
        Initialize the detector.
        
        Args:
            min_profit_threshold: Minimum profit per share to consider.
            min_volume: Minimum market volume to consider (filters low-volume markets).
            min_liquidity: Minimum market liquidity to consider.
        """
        self.min_profit_threshold = (
            min_profit_threshold 
            if min_profit_threshold is not None 
            else Config.MIN_PROFIT_THRESHOLD
        )
        self.min_volume = min_volume
        self.min_liquidity = min_liquidity
        self.opportunities_found = 0
        self.filtered_low_volume = 0
    
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
    
    def calculate_score(self, opp: ArbitrageOpportunity) -> float:
        """
        Calculate a composite score for ranking opportunities.
        
        Score = profit_percentage * volume_factor * liquidity_factor
        
        This prioritizes:
        1. Higher profit percentage
        2. Higher volume (more reliable prices)
        3. Higher liquidity (easier execution)
        """
        market = opp.market
        
        # Normalize volume (log scale to avoid extreme outliers)
        import math
        volume_factor = math.log10(max(market.volume, 1) + 1) / 6  # Normalize to ~0-1
        
        # Normalize liquidity
        liquidity_factor = math.log10(max(market.liquidity, 1) + 1) / 5
        
        # Composite score: profit is primary, volume/liquidity are multipliers
        score = opp.profit_percentage * (0.4 + 0.3 * volume_factor + 0.3 * liquidity_factor)
        
        return score
    
    def scan_markets(self, markets: List[Market]) -> List[ArbitrageOpportunity]:
        """
        Scan multiple markets for arbitrage opportunities.
        
        Filters by minimum volume/liquidity and sorts by composite score.
        
        Args:
            markets: List of markets with current prices
            
        Returns:
            List of detected opportunities, sorted by score (best first)
        """
        opportunities = []
        
        for market in markets:
            opp = self.detect(market)
            if opp:
                # Filter low-volume markets
                if market.volume < self.min_volume:
                    self.filtered_low_volume += 1
                    logger.debug(f"Filtered low volume: {market.question[:40]}... (${market.volume:,.0f})")
                    continue
                
                if market.liquidity < self.min_liquidity:
                    self.filtered_low_volume += 1
                    logger.debug(f"Filtered low liquidity: {market.question[:40]}... (${market.liquidity:,.0f})")
                    continue
                
                opportunities.append(opp)
        
        # Sort by composite score (highest first)
        opportunities.sort(key=lambda x: self.calculate_score(x), reverse=True)
        
        if opportunities:
            logger.info(f"Found {len(opportunities)} arbitrage opportunities (filtered {self.filtered_low_volume} low-volume)")
        
        return opportunities
    
    def get_stats(self) -> dict:
        """Return detector statistics."""
        return {
            "opportunities_found": self.opportunities_found,
            "min_profit_threshold": self.min_profit_threshold,
            "min_volume": self.min_volume,
            "min_liquidity": self.min_liquidity,
            "filtered_low_volume": self.filtered_low_volume,
        }

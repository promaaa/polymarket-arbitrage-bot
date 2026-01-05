"""
Arbitrage Detector - Identifies profitable arbitrage opportunities.
"""
from typing import List, Optional
from datetime import datetime, timezone
import logging
import math

from config import Config
from market_types import Market, ArbitrageOpportunity

logger = logging.getLogger(__name__)


class ArbitrageDetector:
    """Detects arbitrage opportunities in binary markets."""
    
    def __init__(
        self, 
        min_profit_threshold: float = None,
        min_volume: float = None,
        min_liquidity: float = None,
        max_days_to_resolution: int = None,
    ):
        """
        Initialize the detector.
        
        Args:
            min_profit_threshold: Minimum profit per share to consider.
            min_volume: Minimum market volume to consider.
            min_liquidity: Minimum market liquidity to consider.
            max_days_to_resolution: Only consider markets resolving within N days.
        """
        self.min_profit_threshold = min_profit_threshold or Config.MIN_PROFIT_THRESHOLD
        self.min_volume = min_volume or Config.MIN_VOLUME
        self.min_liquidity = min_liquidity or Config.MIN_LIQUIDITY
        self.max_days_to_resolution = max_days_to_resolution or Config.MAX_DAYS_TO_RESOLUTION
        
        self.opportunities_found = 0
        self.filtered_low_volume = 0
        self.filtered_long_term = 0
    
    def days_to_resolution(self, market: Market) -> Optional[int]:
        """Calculate days until market resolves."""
        if not market.end_date:
            return None
        
        now = datetime.now(timezone.utc)
        end = market.end_date
        
        # Make end_date timezone aware if needed
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        
        delta = end - now
        return delta.days
    
    def detect(self, market: Market) -> Optional[ArbitrageOpportunity]:
        """
        Check a single market for arbitrage opportunity.
        """
        yes_price = market.yes_price
        no_price = market.no_price
        
        if yes_price <= 0 or no_price <= 0:
            return None
        
        if yes_price >= 1.0 or no_price >= 1.0:
            return None
        
        combined_cost = yes_price + no_price
        profit_per_share = 1.0 - combined_cost
        
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
        Calculate composite score prioritizing profit, volume, and short resolution.
        """
        market = opp.market
        
        # Volume factor (log scale)
        volume_factor = math.log10(max(market.volume, 1) + 1) / 6
        
        # Liquidity factor
        liquidity_factor = math.log10(max(market.liquidity, 1) + 1) / 5
        
        # Time factor - prefer markets resolving sooner
        days = self.days_to_resolution(market)
        if days is not None and days > 0:
            # Boost score for shorter resolution (7 days = 1.0, 1 day = 2.0)
            time_factor = 1.0 + (7 - min(days, 7)) / 7
        else:
            time_factor = 0.5  # Unknown or expired
        
        # Composite: profit × volume × liquidity × time
        score = opp.profit_percentage * (0.3 + 0.2 * volume_factor + 0.2 * liquidity_factor + 0.3 * time_factor)
        
        return score
    
    def scan_markets(self, markets: List[Market]) -> List[ArbitrageOpportunity]:
        """
        Scan markets for arbitrage, filtering by volume and resolution time.
        """
        opportunities = []
        
        for market in markets:
            opp = self.detect(market)
            if opp:
                # Filter low-volume
                if market.volume < self.min_volume:
                    self.filtered_low_volume += 1
                    continue
                
                if market.liquidity < self.min_liquidity:
                    self.filtered_low_volume += 1
                    continue
                
                # Filter long-term markets
                days = self.days_to_resolution(market)
                if days is not None:
                    if days < 0:  # Already expired
                        self.filtered_long_term += 1
                        continue
                    if days > self.max_days_to_resolution:
                        self.filtered_long_term += 1
                        logger.debug(f"Filtered long-term ({days}d): {market.question[:40]}")
                        continue
                
                opportunities.append(opp)
        
        # Sort by composite score
        opportunities.sort(key=lambda x: self.calculate_score(x), reverse=True)
        
        if opportunities:
            logger.info(
                f"Found {len(opportunities)} opportunities "
                f"(filtered: {self.filtered_low_volume} low-vol, {self.filtered_long_term} long-term)"
            )
        
        return opportunities
    
    def get_stats(self) -> dict:
        """Return detector statistics."""
        return {
            "opportunities_found": self.opportunities_found,
            "min_profit_threshold": self.min_profit_threshold,
            "min_volume": self.min_volume,
            "max_days": self.max_days_to_resolution,
            "filtered_low_volume": self.filtered_low_volume,
            "filtered_long_term": self.filtered_long_term,
        }

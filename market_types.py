"""
Data types for Polymarket markets.
"""
from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime


@dataclass
class Token:
    """A YES or NO token in a market."""
    token_id: str
    outcome: str  # "Yes" or "No"
    price: float = 0.0
    

@dataclass
class Market:
    """A binary prediction market on Polymarket."""
    id: str
    condition_id: str
    question: str
    slug: str
    tokens: List[Token] = field(default_factory=list)
    volume: float = 0.0
    liquidity: float = 0.0
    end_date: Optional[datetime] = None
    active: bool = True
    
    @property
    def yes_token(self) -> Optional[Token]:
        """Get the YES token."""
        for token in self.tokens:
            if token.outcome.lower() == "yes":
                return token
        return None
    
    @property
    def no_token(self) -> Optional[Token]:
        """Get the NO token."""
        for token in self.tokens:
            if token.outcome.lower() == "no":
                return token
        return None
    
    @property
    def yes_price(self) -> float:
        """Get YES token price."""
        token = self.yes_token
        return token.price if token else 0.0
    
    @property
    def no_price(self) -> float:
        """Get NO token price."""
        token = self.no_token
        return token.price if token else 0.0
    
    @property
    def combined_price(self) -> float:
        """Total cost to buy both YES and NO."""
        return self.yes_price + self.no_price


@dataclass
class ArbitrageOpportunity:
    """A detected arbitrage opportunity."""
    market: Market
    yes_price: float
    no_price: float
    combined_cost: float
    profit_per_share: float
    profit_percentage: float
    detected_at: datetime = field(default_factory=datetime.now)
    
    def __str__(self) -> str:
        return (
            f"[ARB] {self.market.question[:50]}... | "
            f"YES=${self.yes_price:.3f} + NO=${self.no_price:.3f} = ${self.combined_cost:.3f} | "
            f"Profit: ${self.profit_per_share:.3f} ({self.profit_percentage:.1f}%)"
        )

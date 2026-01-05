"""
Data types for paper trading.
"""
from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class TradeSide(Enum):
    """Side of a trade."""
    BUY = "buy"
    SELL = "sell"


class PositionStatus(Enum):
    """Status of a position."""
    OPEN = "open"
    CLOSED = "closed"
    RESOLVED = "resolved"


@dataclass
class Trade:
    """A single trade execution."""
    id: str
    market_id: str
    market_question: str
    token_id: str
    outcome: str  # "Yes" or "No"
    side: TradeSide
    shares: float
    price: float
    cost: float
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "market_id": self.market_id,
            "market_question": self.market_question,
            "token_id": self.token_id,
            "outcome": self.outcome,
            "side": self.side.value,
            "shares": self.shares,
            "price": self.price,
            "cost": self.cost,
            "timestamp": self.timestamp.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Trade":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            market_id=data["market_id"],
            market_question=data["market_question"],
            token_id=data["token_id"],
            outcome=data["outcome"],
            side=TradeSide(data["side"]),
            shares=data["shares"],
            price=data["price"],
            cost=data["cost"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


@dataclass
class Position:
    """A position in a market (both YES and NO shares from arbitrage)."""
    id: str
    market_id: str
    market_question: str
    yes_shares: float
    no_shares: float
    yes_cost: float
    no_cost: float
    total_cost: float
    expected_profit: float
    status: PositionStatus = PositionStatus.OPEN
    opened_at: datetime = field(default_factory=datetime.now)
    closed_at: Optional[datetime] = None
    realized_profit: Optional[float] = None
    
    @property
    def shares(self) -> float:
        """Number of complete share pairs (min of yes and no)."""
        return min(self.yes_shares, self.no_shares)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "market_id": self.market_id,
            "market_question": self.market_question,
            "yes_shares": self.yes_shares,
            "no_shares": self.no_shares,
            "yes_cost": self.yes_cost,
            "no_cost": self.no_cost,
            "total_cost": self.total_cost,
            "expected_profit": self.expected_profit,
            "status": self.status.value,
            "opened_at": self.opened_at.isoformat(),
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "realized_profit": self.realized_profit,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Position":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            market_id=data["market_id"],
            market_question=data["market_question"],
            yes_shares=data["yes_shares"],
            no_shares=data["no_shares"],
            yes_cost=data["yes_cost"],
            no_cost=data["no_cost"],
            total_cost=data["total_cost"],
            expected_profit=data["expected_profit"],
            status=PositionStatus(data["status"]),
            opened_at=datetime.fromisoformat(data["opened_at"]),
            closed_at=datetime.fromisoformat(data["closed_at"]) if data.get("closed_at") else None,
            realized_profit=data.get("realized_profit"),
        )


@dataclass
class TradingStats:
    """Overall trading statistics."""
    total_trades: int = 0
    total_positions: int = 0
    open_positions: int = 0
    closed_positions: int = 0
    total_invested: float = 0.0
    total_profit: float = 0.0
    win_rate: float = 0.0
    current_balance: float = 0.0
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "total_trades": self.total_trades,
            "total_positions": self.total_positions,
            "open_positions": self.open_positions,
            "closed_positions": self.closed_positions,
            "total_invested": round(self.total_invested, 2),
            "total_profit": round(self.total_profit, 2),
            "win_rate": round(self.win_rate * 100, 1),
            "current_balance": round(self.current_balance, 2),
        }

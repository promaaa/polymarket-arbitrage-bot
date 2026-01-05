"""
Paper Trader - Simulates trades without real money.
"""
import json
import uuid
from typing import List, Optional, Dict
from datetime import datetime
from pathlib import Path
import logging

from config import Config
from market_types import ArbitrageOpportunity
from trade_types import Trade, Position, TradingStats, TradeSide, PositionStatus

logger = logging.getLogger(__name__)


class PaperTrader:
    """
    Simulates trading for arbitrage opportunities.
    
    Maintains a virtual balance and tracks all trades/positions.
    """
    
    def __init__(self, initial_balance: float = None, trade_size: float = None):
        """
        Initialize the paper trader.
        
        Args:
            initial_balance: Starting USDC balance. Defaults to config.
            trade_size: Amount to invest per opportunity. Defaults to config.
        """
        self.initial_balance = initial_balance or Config.INITIAL_BALANCE
        self.trade_size = trade_size or Config.TRADE_SIZE
        self.balance = self.initial_balance
        
        self.trades: List[Trade] = []
        self.positions: Dict[str, Position] = {}  # market_id -> Position
        
        self.trades_file = Path(Config.TRADES_FILE)
        self.positions_file = Path(Config.POSITIONS_FILE)
        
        self._load_state()
    
    def execute_arbitrage(self, opportunity: ArbitrageOpportunity) -> Optional[Position]:
        """
        Execute an arbitrage trade by buying both YES and NO.
        
        Args:
            opportunity: The detected arbitrage opportunity
            
        Returns:
            The created position, or None if trade failed
        """
        market = opportunity.market
        
        # Check if we already have a position in this market
        if market.id in self.positions:
            logger.warning(f"Already have position in market {market.id}")
            return None
        
        # Calculate how many shares we can buy with trade_size
        combined_cost = opportunity.combined_cost
        shares = self.trade_size / combined_cost
        
        yes_cost = shares * opportunity.yes_price
        no_cost = shares * opportunity.no_price
        total_cost = yes_cost + no_cost
        
        # Check balance
        if total_cost > self.balance:
            logger.warning(f"Insufficient balance: {self.balance:.2f} < {total_cost:.2f}")
            return None
        
        # Execute trades
        yes_trade = Trade(
            id=str(uuid.uuid4()),
            market_id=market.id,
            market_question=market.question,
            token_id=market.yes_token.token_id if market.yes_token else "",
            outcome="Yes",
            side=TradeSide.BUY,
            shares=shares,
            price=opportunity.yes_price,
            cost=yes_cost,
        )
        
        no_trade = Trade(
            id=str(uuid.uuid4()),
            market_id=market.id,
            market_question=market.question,
            token_id=market.no_token.token_id if market.no_token else "",
            outcome="No",
            side=TradeSide.BUY,
            shares=shares,
            price=opportunity.no_price,
            cost=no_cost,
        )
        
        self.trades.append(yes_trade)
        self.trades.append(no_trade)
        
        # Create position
        expected_profit = shares * opportunity.profit_per_share
        position = Position(
            id=str(uuid.uuid4()),
            market_id=market.id,
            market_question=market.question,
            yes_shares=shares,
            no_shares=shares,
            yes_cost=yes_cost,
            no_cost=no_cost,
            total_cost=total_cost,
            expected_profit=expected_profit,
        )
        
        self.positions[market.id] = position
        
        # Update balance
        self.balance -= total_cost
        
        logger.info(
            f"Executed arbitrage: {shares:.2f} shares for ${total_cost:.2f} | "
            f"Expected profit: ${expected_profit:.2f}"
        )
        
        self._save_state()
        return position
    
    def resolve_position(self, market_id: str, winning_outcome: str) -> Optional[float]:
        """
        Resolve a position when market closes.
        
        Args:
            market_id: ID of the market
            winning_outcome: "Yes" or "No"
            
        Returns:
            Realized profit, or None if no position
        """
        if market_id not in self.positions:
            return None
        
        position = self.positions[market_id]
        
        # One side pays $1 per share
        shares = position.shares
        payout = shares * 1.0  # $1 per share for winning side
        
        realized_profit = payout - position.total_cost
        
        # Update position
        position.status = PositionStatus.RESOLVED
        position.closed_at = datetime.now()
        position.realized_profit = realized_profit
        
        # Update balance
        self.balance += payout
        
        logger.info(
            f"Resolved position {market_id}: payout=${payout:.2f}, "
            f"profit=${realized_profit:.2f}"
        )
        
        self._save_state()
        return realized_profit
    
    def get_stats(self) -> TradingStats:
        """Calculate current trading statistics."""
        open_positions = [p for p in self.positions.values() if p.status == PositionStatus.OPEN]
        closed_positions = [p for p in self.positions.values() if p.status != PositionStatus.OPEN]
        
        total_invested = sum(p.total_cost for p in self.positions.values())
        total_profit = sum(p.realized_profit or 0 for p in closed_positions)
        
        wins = len([p for p in closed_positions if (p.realized_profit or 0) > 0])
        win_rate = wins / len(closed_positions) if closed_positions else 0
        
        return TradingStats(
            total_trades=len(self.trades),
            total_positions=len(self.positions),
            open_positions=len(open_positions),
            closed_positions=len(closed_positions),
            total_invested=total_invested,
            total_profit=total_profit,
            win_rate=win_rate,
            current_balance=self.balance,
        )
    
    def get_open_positions(self) -> List[Position]:
        """Get all open positions."""
        return [p for p in self.positions.values() if p.status == PositionStatus.OPEN]
    
    def get_recent_trades(self, limit: int = 20) -> List[Trade]:
        """Get most recent trades."""
        return sorted(self.trades, key=lambda t: t.timestamp, reverse=True)[:limit]
    
    def reset(self):
        """Reset all trading state."""
        self.balance = self.initial_balance
        self.trades = []
        self.positions = {}
        self._save_state()
        logger.info("Paper trader reset")
    
    def _save_state(self):
        """Persist state to JSON files."""
        try:
            # Save trades
            trades_data = [t.to_dict() for t in self.trades]
            with open(self.trades_file, "w") as f:
                json.dump({"trades": trades_data, "balance": self.balance}, f, indent=2)
            
            # Save positions
            positions_data = {k: v.to_dict() for k, v in self.positions.items()}
            with open(self.positions_file, "w") as f:
                json.dump(positions_data, f, indent=2)
                
        except IOError as e:
            logger.error(f"Failed to save state: {e}")
    
    def _load_state(self):
        """Load state from JSON files."""
        try:
            # Load trades
            if self.trades_file.exists():
                with open(self.trades_file) as f:
                    data = json.load(f)
                    self.trades = [Trade.from_dict(t) for t in data.get("trades", [])]
                    self.balance = data.get("balance", self.initial_balance)
            
            # Load positions
            if self.positions_file.exists():
                with open(self.positions_file) as f:
                    data = json.load(f)
                    self.positions = {
                        k: Position.from_dict(v) for k, v in data.items()
                    }
                    
            logger.info(
                f"Loaded state: {len(self.trades)} trades, "
                f"{len(self.positions)} positions, ${self.balance:.2f} balance"
            )
            
        except (IOError, json.JSONDecodeError) as e:
            logger.warning(f"Could not load state: {e}")

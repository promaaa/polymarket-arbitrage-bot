"""
Tests for paper trading engine.
"""
import pytest
import tempfile
import os
from datetime import datetime

from market_types import Market, Token, ArbitrageOpportunity
from paper_trader import PaperTrader
from trade_types import PositionStatus


@pytest.fixture
def trader():
    """Create a paper trader with temp files."""
    # Use temp files to avoid polluting project
    with tempfile.TemporaryDirectory() as tmpdir:
        import config
        original_trades = config.Config.TRADES_FILE
        original_positions = config.Config.POSITIONS_FILE
        
        config.Config.TRADES_FILE = os.path.join(tmpdir, "trades.json")
        config.Config.POSITIONS_FILE = os.path.join(tmpdir, "positions.json")
        
        trader = PaperTrader(initial_balance=10000, trade_size=100)
        yield trader
        
        config.Config.TRADES_FILE = original_trades
        config.Config.POSITIONS_FILE = original_positions


@pytest.fixture
def sample_opportunity():
    """Create a sample arbitrage opportunity."""
    market = Market(
        id="test-market",
        condition_id="test-condition",
        question="Test market?",
        slug="test-market",
        tokens=[
            Token(token_id="yes-token", outcome="Yes", price=0.48),
            Token(token_id="no-token", outcome="No", price=0.49),
        ],
    )
    
    return ArbitrageOpportunity(
        market=market,
        yes_price=0.48,
        no_price=0.49,
        combined_cost=0.97,
        profit_per_share=0.03,
        profit_percentage=3.09,
    )


class TestPaperTrader:
    """Test paper trading execution."""
    
    def test_initial_balance(self, trader):
        """Starts with configured balance."""
        assert trader.balance == 10000
    
    def test_execute_arbitrage_creates_position(self, trader, sample_opportunity):
        """Executing arbitrage creates a position."""
        position = trader.execute_arbitrage(sample_opportunity)
        
        assert position is not None
        assert position.market_id == "test-market"
        assert position.status == PositionStatus.OPEN
    
    def test_execute_arbitrage_deducts_balance(self, trader, sample_opportunity):
        """Balance is reduced by trade cost."""
        initial_balance = trader.balance
        
        position = trader.execute_arbitrage(sample_opportunity)
        
        assert trader.balance < initial_balance
        assert trader.balance == initial_balance - position.total_cost
    
    def test_execute_arbitrage_creates_trades(self, trader, sample_opportunity):
        """Creates both YES and NO trades."""
        trader.execute_arbitrage(sample_opportunity)
        
        assert len(trader.trades) == 2
        
        outcomes = [t.outcome for t in trader.trades]
        assert "Yes" in outcomes
        assert "No" in outcomes
    
    def test_cannot_double_position(self, trader, sample_opportunity):
        """Cannot create second position in same market."""
        trader.execute_arbitrage(sample_opportunity)
        
        second = trader.execute_arbitrage(sample_opportunity)
        assert second is None
    
    def test_insufficient_balance(self, trader, sample_opportunity):
        """Cannot trade without sufficient balance."""
        trader.balance = 50  # Less than trade_size (100)
        
        position = trader.execute_arbitrage(sample_opportunity)
        assert position is None
    
    def test_expected_profit_calculation(self, trader, sample_opportunity):
        """Expected profit is calculated correctly."""
        position = trader.execute_arbitrage(sample_opportunity)
        
        # Trade size = 100, combined cost = 0.97
        # Shares = 100 / 0.97 ≈ 103.09
        # Expected profit = shares * 0.03 ≈ 3.09
        assert position.expected_profit > 0
        assert abs(position.expected_profit - 3.09) < 0.5


class TestPositionResolution:
    """Test position resolution."""
    
    def test_resolve_position_adds_payout(self, trader, sample_opportunity):
        """Resolution adds payout to balance."""
        position = trader.execute_arbitrage(sample_opportunity)
        balance_after_trade = trader.balance
        
        profit = trader.resolve_position("test-market", "Yes")
        
        assert profit is not None
        assert profit > 0
        assert trader.balance > balance_after_trade
    
    def test_resolve_updates_position_status(self, trader, sample_opportunity):
        """Position status updates on resolution."""
        trader.execute_arbitrage(sample_opportunity)
        
        trader.resolve_position("test-market", "Yes")
        
        position = trader.positions["test-market"]
        assert position.status == PositionStatus.RESOLVED
        assert position.closed_at is not None
    
    def test_resolve_nonexistent_position(self, trader):
        """Returns None for nonexistent position."""
        result = trader.resolve_position("fake-market", "Yes")
        assert result is None


class TestTradingStats:
    """Test trading statistics."""
    
    def test_stats_after_trades(self, trader, sample_opportunity):
        """Stats reflect trading activity."""
        trader.execute_arbitrage(sample_opportunity)
        
        stats = trader.get_stats()
        
        assert stats.total_trades == 2
        assert stats.total_positions == 1
        assert stats.open_positions == 1
        assert stats.total_invested > 0
    
    def test_reset_clears_all(self, trader, sample_opportunity):
        """Reset clears all state."""
        trader.execute_arbitrage(sample_opportunity)
        trader.reset()
        
        assert trader.balance == 10000
        assert len(trader.trades) == 0
        assert len(trader.positions) == 0

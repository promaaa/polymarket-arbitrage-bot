"""
Tests for arbitrage detection logic.
"""
import pytest
from datetime import datetime

from market_types import Market, Token, ArbitrageOpportunity
from arbitrage_detector import ArbitrageDetector


@pytest.fixture
def detector():
    """Create a detector with 1% threshold."""
    return ArbitrageDetector(min_profit_threshold=0.01)


@pytest.fixture
def sample_market():
    """Create a sample market."""
    return Market(
        id="test-market",
        condition_id="test-condition",
        question="Test market?",
        slug="test-market",
        tokens=[
            Token(token_id="yes-token", outcome="Yes", price=0.50),
            Token(token_id="no-token", outcome="No", price=0.50),
        ],
    )


class TestArbitrageDetection:
    """Test arbitrage opportunity detection."""
    
    def test_no_arbitrage_when_sum_equals_one(self, detector, sample_market):
        """No opportunity when YES + NO = 1.0"""
        sample_market.tokens[0].price = 0.50  # YES
        sample_market.tokens[1].price = 0.50  # NO
        
        result = detector.detect(sample_market)
        assert result is None
    
    def test_no_arbitrage_when_sum_above_one(self, detector, sample_market):
        """No opportunity when YES + NO > 1.0"""
        sample_market.tokens[0].price = 0.55  # YES
        sample_market.tokens[1].price = 0.50  # NO
        
        result = detector.detect(sample_market)
        assert result is None
    
    def test_arbitrage_when_sum_below_threshold(self, detector, sample_market):
        """Opportunity exists when YES + NO < 0.99 (1% threshold)"""
        sample_market.tokens[0].price = 0.48  # YES
        sample_market.tokens[1].price = 0.49  # NO
        # Total = 0.97, profit = 0.03
        
        result = detector.detect(sample_market)
        
        assert result is not None
        assert isinstance(result, ArbitrageOpportunity)
        assert result.yes_price == 0.48
        assert result.no_price == 0.49
        assert result.combined_cost == 0.97
        assert abs(result.profit_per_share - 0.03) < 0.001
    
    def test_no_arbitrage_below_min_threshold(self, detector, sample_market):
        """No opportunity if profit below minimum threshold."""
        sample_market.tokens[0].price = 0.495  # YES
        sample_market.tokens[1].price = 0.500  # NO
        # Total = 0.995, profit = 0.005 (< 0.01 threshold)
        
        result = detector.detect(sample_market)
        assert result is None
    
    def test_handles_zero_prices(self, detector, sample_market):
        """Safely handles zero prices."""
        sample_market.tokens[0].price = 0.0
        sample_market.tokens[1].price = 0.50
        
        result = detector.detect(sample_market)
        assert result is None
    
    def test_handles_invalid_high_prices(self, detector, sample_market):
        """Safely handles prices >= 1.0"""
        sample_market.tokens[0].price = 1.0
        sample_market.tokens[1].price = 0.50
        
        result = detector.detect(sample_market)
        assert result is None
    
    def test_profit_percentage_calculation(self, detector, sample_market):
        """Validates profit percentage calculation."""
        sample_market.tokens[0].price = 0.40  # YES
        sample_market.tokens[1].price = 0.40  # NO
        # Total = 0.80, profit = 0.20 = 25%
        
        result = detector.detect(sample_market)
        
        assert result is not None
        assert abs(result.profit_percentage - 25.0) < 0.1
    
    def test_scan_multiple_markets(self, detector):
        """Tests scanning multiple markets."""
        markets = [
            Market(
                id=f"market-{i}",
                condition_id=f"condition-{i}",
                question=f"Market {i}?",
                slug=f"market-{i}",
                tokens=[
                    Token(token_id=f"yes-{i}", outcome="Yes", price=yes),
                    Token(token_id=f"no-{i}", outcome="No", price=no),
                ],
            )
            for i, (yes, no) in enumerate([
                (0.50, 0.50),  # No arb
                (0.45, 0.45),  # Arb: 10% profit
                (0.48, 0.49),  # Arb: 3% profit
                (0.55, 0.50),  # No arb
            ])
        ]
        
        opportunities = detector.scan_markets(markets)
        
        assert len(opportunities) == 2
        # Should be sorted by profit percentage (highest first)
        assert opportunities[0].profit_percentage > opportunities[1].profit_percentage


class TestArbitrageStats:
    """Test detector statistics."""
    
    def test_opportunities_count(self):
        """Tracks opportunities found."""
        detector = ArbitrageDetector(min_profit_threshold=0.01)
        
        market = Market(
            id="test",
            condition_id="test",
            question="Test?",
            slug="test",
            tokens=[
                Token(token_id="yes", outcome="Yes", price=0.40),
                Token(token_id="no", outcome="No", price=0.40),
            ],
        )
        
        assert detector.opportunities_found == 0
        
        detector.detect(market)
        assert detector.opportunities_found == 1
        
        detector.detect(market)
        assert detector.opportunities_found == 2

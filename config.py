"""
Configuration settings for the Polymarket Arbitrage Bot.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Bot configuration loaded from environment variables."""
    
    # API Endpoints
    GAMMA_API_URL = "https://gamma-api.polymarket.com"
    CLOB_API_URL = "https://clob.polymarket.com"
    
    # Scanning settings
    SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "5"))
    
    # Trading parameters
    MIN_PROFIT_THRESHOLD = float(os.getenv("MIN_PROFIT_THRESHOLD", "0.01"))
    MIN_VOLUME = float(os.getenv("MIN_VOLUME", "10000"))  # Minimum market volume
    MIN_LIQUIDITY = float(os.getenv("MIN_LIQUIDITY", "1000"))  # Minimum liquidity
    INITIAL_BALANCE = float(os.getenv("INITIAL_BALANCE", "10000"))
    
    # Trade sizing - amount to invest per arbitrage opportunity
    TRADE_SIZE = float(os.getenv("TRADE_SIZE", "100"))
    
    # Target markets (filter by keywords)
    TARGET_MARKETS = [
        m.strip().upper() 
        for m in os.getenv("TARGET_MARKETS", "BTC,ETH,SOL,XRP").split(",")
        if m.strip()
    ]
    
    # Dashboard settings
    DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8080"))
    
    # Data persistence
    TRADES_FILE = os.getenv("TRADES_FILE", "trades.json")
    POSITIONS_FILE = os.getenv("POSITIONS_FILE", "positions.json")
    
    @classmethod
    def to_dict(cls) -> dict:
        """Return configuration as dictionary."""
        return {
            "scan_interval": cls.SCAN_INTERVAL,
            "min_profit_threshold": cls.MIN_PROFIT_THRESHOLD,
            "initial_balance": cls.INITIAL_BALANCE,
            "trade_size": cls.TRADE_SIZE,
            "target_markets": cls.TARGET_MARKETS,
            "dashboard_port": cls.DASHBOARD_PORT,
        }

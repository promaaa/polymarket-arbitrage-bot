"""
Web Dashboard - Real-time monitoring of arbitrage bot.
"""
from flask import Flask, render_template, jsonify
from datetime import datetime
import threading
import logging

from config import Config
from paper_trader import PaperTrader
from market_scanner import MarketScanner, MockMarketScanner
from arbitrage_detector import ArbitrageDetector

logger = logging.getLogger(__name__)


def create_dashboard(trader: PaperTrader, scanner: MarketScanner, detector: ArbitrageDetector):
    """
    Create and configure the Flask dashboard app.
    
    Args:
        trader: PaperTrader instance
        scanner: MarketScanner instance
        detector: ArbitrageDetector instance
        
    Returns:
        Configured Flask app
    """
    app = Flask(__name__)
    
    # Store references for route access
    app.trader = trader
    app.scanner = scanner
    app.detector = detector
    app.recent_opportunities = []
    app.last_scan = None
    app.scan_count = 0
    
    @app.route("/")
    def index():
        """Main dashboard page."""
        return render_template("index.html", config=Config.to_dict())
    
    @app.route("/api/stats")
    def api_stats():
        """Get current trading statistics."""
        stats = app.trader.get_stats()
        return jsonify({
            "stats": stats.to_dict(),
            "scan_count": app.scan_count,
            "last_scan": app.last_scan.isoformat() if app.last_scan else None,
            "detector_stats": app.detector.get_stats(),
        })
    
    @app.route("/api/positions")
    def api_positions():
        """Get open positions."""
        positions = app.trader.get_open_positions()
        return jsonify({
            "positions": [p.to_dict() for p in positions],
        })
    
    @app.route("/api/trades")
    def api_trades():
        """Get recent trades."""
        trades = app.trader.get_recent_trades(limit=50)
        return jsonify({
            "trades": [t.to_dict() for t in trades],
        })
    
    @app.route("/api/opportunities")
    def api_opportunities():
        """Get recent arbitrage opportunities."""
        return jsonify({
            "opportunities": [
                {
                    "market_question": opp.market.question,
                    "yes_price": opp.yes_price,
                    "no_price": opp.no_price,
                    "combined_cost": opp.combined_cost,
                    "profit_per_share": opp.profit_per_share,
                    "profit_percentage": opp.profit_percentage,
                    "detected_at": opp.detected_at.isoformat(),
                }
                for opp in app.recent_opportunities[-20:]
            ],
        })
    
    @app.route("/api/reset", methods=["POST"])
    def api_reset():
        """Reset paper trader."""
        app.trader.reset()
        app.recent_opportunities = []
        return jsonify({"status": "ok"})
    
    return app


def run_dashboard(trader: PaperTrader, scanner: MarketScanner, detector: ArbitrageDetector):
    """
    Run the dashboard server.
    
    Args:
        trader: PaperTrader instance
        scanner: MarketScanner instance  
        detector: ArbitrageDetector instance
    """
    app = create_dashboard(trader, scanner, detector)
    
    logger.info(f"Starting dashboard on http://localhost:{Config.DASHBOARD_PORT}")
    app.run(
        host="0.0.0.0",
        port=Config.DASHBOARD_PORT,
        debug=False,
        threaded=True,
    )

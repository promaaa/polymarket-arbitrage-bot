#!/usr/bin/env python3
"""
Async Dashboard - High-performance Flask dashboard with async bot integration.
"""
import asyncio
import threading
from flask import Flask, render_template, jsonify
from datetime import datetime
import logging

from config import Config
from paper_trader import PaperTrader
from async_scanner import AsyncMarketScanner, AsyncMockScanner
from arbitrage_detector import ArbitrageDetector

logger = logging.getLogger(__name__)


class AsyncDashboard:
    """
    Dashboard that runs alongside the async bot.
    
    Flask runs in a separate thread while the async bot
    runs in the main event loop.
    """
    
    def __init__(self, bot):
        """
        Initialize dashboard with bot reference.
        
        Args:
            bot: AsyncArbitrageBot instance
        """
        self.bot = bot
        self.app = self._create_app()
    
    def _create_app(self) -> Flask:
        """Create Flask application."""
        app = Flask(__name__, 
                    template_folder='templates',
                    static_folder='static')
        
        @app.route("/")
        def index():
            return render_template("index.html", config=Config.to_dict())
        
        @app.route("/api/stats")
        def api_stats():
            stats = self.bot.trader.get_stats()
            scanner_stats = self.bot.scanner.get_stats()
            
            return jsonify({
                "stats": stats.to_dict(),
                "scan_count": self.bot.scan_count,
                "last_scan": self.bot.last_scan.isoformat() if self.bot.last_scan else None,
                "detector_stats": self.bot.detector.get_stats(),
                "scanner_stats": scanner_stats,
                "performance": {
                    "avg_scan_ms": round(self.bot.total_scan_time / max(1, self.bot.scan_count) * 1000, 1),
                    "min_scan_ms": round(self.bot.min_scan_time * 1000, 1) if self.bot.min_scan_time != float('inf') else 0,
                    "max_scan_ms": round(self.bot.max_scan_time * 1000, 1),
                },
            })
        
        @app.route("/api/positions")
        def api_positions():
            positions = self.bot.trader.get_open_positions()
            return jsonify({
                "positions": [p.to_dict() for p in positions],
            })
        
        @app.route("/api/trades")
        def api_trades():
            trades = self.bot.trader.get_recent_trades(limit=50)
            return jsonify({
                "trades": [t.to_dict() for t in trades],
            })
        
        @app.route("/api/opportunities")
        def api_opportunities():
            return jsonify({
                "opportunities": [
                    {
                        "market_question": opp.market.question if hasattr(opp, "market") else opp.get("market_question", ""),
                        "yes_price": opp.yes_price if hasattr(opp, "yes_price") else opp.get("yes_price", 0.0),
                        "no_price": opp.no_price if hasattr(opp, "no_price") else opp.get("no_price", 0.0),
                        "combined_cost": opp.combined_cost if hasattr(opp, "combined_cost") else opp.get("combined_cost", 0.0),
                        "profit_per_share": opp.profit_per_share if hasattr(opp, "profit_per_share") else opp.get("profit_per_share", 0.0),
                        "profit_percentage": opp.profit_percentage if hasattr(opp, "profit_percentage") else opp.get("profit_percentage", 0.0),
                        "detected_at": opp.detected_at.isoformat() if hasattr(opp, "detected_at") and hasattr(opp.detected_at, "isoformat") else opp.get("detected_at", ""),
                    }
                    for opp in self.bot.recent_opportunities[-20:]
                ],
            })
        
        @app.route("/api/reset", methods=["POST"])
        def api_reset():
            self.bot.trader.reset()
            self.bot.recent_opportunities = []
            return jsonify({"status": "ok"})
        
        return app
    
    def run_in_thread(self):
        """Run Flask in a background thread."""
        def run():
            # Disable Flask's default logging for cleaner output
            import logging
            log = logging.getLogger('werkzeug')
            log.setLevel(logging.WARNING)
            
            self.app.run(
                host="0.0.0.0",
                port=Config.DASHBOARD_PORT,
                debug=False,
                threaded=True,
                use_reloader=False,
            )
        
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        logger.info(f"Dashboard started at http://localhost:{Config.DASHBOARD_PORT}")
        return thread

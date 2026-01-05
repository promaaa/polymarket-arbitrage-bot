# Polymarket Arbitrage Bot

A paper trading prototype that detects arbitrage opportunities on Polymarket binary markets.

## Strategy

When YES + NO prices sum to less than $1.00, buying both sides guarantees profit:
- Example: YES=$0.48, NO=$0.49 → Total=$0.97 → Profit=$0.03

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run with web dashboard
python main.py --dashboard

# Run in simulation mode (uses mock data)
python main.py --simulate

# Run against live Polymarket APIs
python main.py
```

## Dashboard

Open http://localhost:8080 to view:
- Real-time arbitrage opportunities
- Paper trading positions & P&L
- Trade history

## Project Structure

```
├── main.py              # Entry point
├── config.py            # Configuration settings
├── market_scanner.py    # Fetches market data from Polymarket
├── market_types.py      # Data classes for markets
├── arbitrage_detector.py # Arbitrage detection logic
├── paper_trader.py      # Simulated trading engine
├── trade_types.py       # Data classes for trades
├── dashboard.py         # Flask web dashboard
├── templates/           # HTML templates
└── static/              # CSS/JS assets
```

## Configuration

Copy `.env.example` to `.env` and adjust:

```env
SCAN_INTERVAL=5          # Seconds between scans
MIN_PROFIT_THRESHOLD=0.01 # Minimum profit to trigger trade
INITIAL_BALANCE=10000    # Starting paper balance (USDC)
```

## High-Performance Async Version

For maximum speed, use `main_async.py`:

```bash
# Run async version with benchmark
python3 main_async.py --simulate --benchmark

# Run with WebSocket + polling hybrid
python3 main_async.py --simulate
```

### Performance

| Version | Avg Scan Time | Notes |
|---------|--------------|-------|
| Sync (`main.py`) | ~500ms | Sequential API calls |
| Async (`main_async.py`) | **~7ms** | Concurrent + caching |

**Optimizations:**
- Concurrent API calls with `aiohttp`
- Connection pooling (100 connections)
- Response caching with TTL
- WebSocket for real-time price updates
- Hybrid mode: WebSocket + periodic polling

## Disclaimer

This is a **paper trading prototype only**. No real money is used.

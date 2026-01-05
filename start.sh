#!/bin/bash
echo "🚀 Starting Polymarket Bot Container..."

# Ensure log directory exists or use local
touch scanner.log

# Start Rust Scanner (Background)
echo "Starting Rust WebSocket Scanner..."
./polymarket_scanner > scanner.log 2>&1 &
SCANNER_PID=$!

# Wait for scanner to init
sleep 2

# Start Python Dashboard
echo "Starting Python Dashboard..."
# Listen on 0.0.0.0 is handled by Flask (host='0.0.0.0' in async_dashboard.py?)
# Check async_dashboard.py
python3 main_async.py --dashboard --rust

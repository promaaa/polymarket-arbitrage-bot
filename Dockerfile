# Build Stage for Rust Scanner
FROM rust:1.75-slim-bookworm as builder

WORKDIR /usr/src/app
COPY rust-scanner .

# Install build dependencies (OpenSSL used by reqwest/tungstenite)
RUN apt-get update && apt-get install -y pkg-config libssl-dev

# Build with optimizations
RUN cargo build --release

# Final Stage (Runtime)
FROM python:3.9-slim-bookworm

WORKDIR /app

# Install Runtime dependencies
RUN apt-get update && apt-get install -y \
    libssl3 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy Python requirements & Install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Python bot & Dashboard code
COPY main_async.py .
COPY async_dashboard.py .
COPY config.py .
COPY static static/
COPY templates templates/

# Copy Compiled Rust Binary from Builder
COPY --from=builder /usr/src/app/target/release/polymarket_scanner /app/polymarket_scanner

# Script to run both
COPY start.sh .
RUN chmod +x start.sh

# Expose Dashboard Port
EXPOSE 8080

# Run the optimized stack
CMD ["./start.sh"]

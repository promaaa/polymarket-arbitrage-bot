"""
WebSocket Client for real-time Polymarket price updates.

Uses WebSocket for instant price updates instead of polling.
"""
import asyncio
import aiohttp
import json
from typing import Dict, Callable, Optional, Set
from datetime import datetime
import logging

from config import Config

logger = logging.getLogger(__name__)


class PriceWebSocket:
    """
    WebSocket client for real-time Polymarket prices.
    
    Subscribes to price updates for specific tokens and
    calls a callback when prices change.
    """
    
    # Polymarket WebSocket endpoint
    WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    
    def __init__(self, on_price_update: Callable[[str, float], None]):
        """
        Initialize WebSocket client.
        
        Args:
            on_price_update: Callback(token_id, price) called on updates
        """
        self.on_price_update = on_price_update
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._subscribed_tokens: Set[str] = set()
        self._running = False
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 60.0
        
        # Price cache for fast lookups
        self.prices: Dict[str, float] = {}
        self.last_update: Dict[str, datetime] = {}
        
        # Stats
        self.messages_received = 0
        self.reconnect_count = 0
    
    async def connect(self):
        """Establish WebSocket connection."""
        if self._session is None:
            self._session = aiohttp.ClientSession()
        
        try:
            self._ws = await self._session.ws_connect(
                self.WS_URL,
                heartbeat=30,
                receive_timeout=60,
            )
            self._running = True
            self._reconnect_delay = 1.0  # Reset on successful connect
            logger.info("WebSocket connected")
            
            # Resubscribe to tokens
            if self._subscribed_tokens:
                await self._subscribe(list(self._subscribed_tokens))
            
        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")
            raise
    
    async def subscribe(self, token_ids: list):
        """Subscribe to price updates for tokens."""
        new_tokens = set(token_ids) - self._subscribed_tokens
        if new_tokens:
            self._subscribed_tokens.update(new_tokens)
            if self._ws and not self._ws.closed:
                await self._subscribe(list(new_tokens))
    
    async def _subscribe(self, token_ids: list):
        """Send subscription message."""
        if not self._ws or self._ws.closed:
            return
        
        for token_id in token_ids:
            msg = {
                "type": "subscribe",
                "channel": "price",
                "token_id": token_id,
            }
            await self._ws.send_json(msg)
            logger.debug(f"Subscribed to {token_id}")
    
    async def unsubscribe(self, token_ids: list):
        """Unsubscribe from tokens."""
        for token_id in token_ids:
            self._subscribed_tokens.discard(token_id)
            if self._ws and not self._ws.closed:
                msg = {
                    "type": "unsubscribe",
                    "channel": "price",
                    "token_id": token_id,
                }
                await self._ws.send_json(msg)
    
    async def listen(self):
        """Listen for WebSocket messages."""
        while self._running:
            try:
                if self._ws is None or self._ws.closed:
                    await self.connect()
                
                async for msg in self._ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        await self._handle_message(msg.data)
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        logger.error(f"WebSocket error: {self._ws.exception()}")
                        break
                    elif msg.type == aiohttp.WSMsgType.CLOSED:
                        logger.info("WebSocket closed")
                        break
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                
                if self._running:
                    self.reconnect_count += 1
                    logger.info(f"Reconnecting in {self._reconnect_delay}s...")
                    await asyncio.sleep(self._reconnect_delay)
                    self._reconnect_delay = min(
                        self._reconnect_delay * 2,
                        self._max_reconnect_delay
                    )
    
    async def _handle_message(self, data: str):
        """Process incoming WebSocket message."""
        try:
            msg = json.loads(data)
            self.messages_received += 1
            
            # Handle price update
            if msg.get("type") == "price":
                token_id = msg.get("token_id")
                price = float(msg.get("price", 0))
                
                if token_id:
                    old_price = self.prices.get(token_id)
                    self.prices[token_id] = price
                    self.last_update[token_id] = datetime.now()
                    
                    # Call callback if price changed
                    if old_price != price:
                        self.on_price_update(token_id, price)
            
            # Handle other message types
            elif msg.get("type") == "subscribed":
                logger.debug(f"Confirmed subscription: {msg.get('token_id')}")
            
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON: {data[:100]}")
        except Exception as e:
            logger.error(f"Message handling error: {e}")
    
    async def close(self):
        """Close WebSocket connection."""
        self._running = False
        
        if self._ws and not self._ws.closed:
            await self._ws.close()
        
        if self._session and not self._session.closed:
            await self._session.close()
        
        logger.info("WebSocket closed")
    
    def get_price(self, token_id: str) -> float:
        """Get cached price for token."""
        return self.prices.get(token_id, 0.0)
    
    def get_stats(self) -> dict:
        """Return WebSocket statistics."""
        return {
            "connected": self._ws is not None and not self._ws.closed,
            "subscribed_tokens": len(self._subscribed_tokens),
            "messages_received": self.messages_received,
            "reconnect_count": self.reconnect_count,
            "cached_prices": len(self.prices),
        }


class MockPriceWebSocket(PriceWebSocket):
    """
    Mock WebSocket for testing.
    
    Simulates price updates at configurable intervals.
    """
    
    def __init__(self, on_price_update: Callable[[str, float], None], update_interval: float = 0.5):
        super().__init__(on_price_update)
        self.update_interval = update_interval
        self._mock_task: Optional[asyncio.Task] = None
    
    async def connect(self):
        """Simulate connection."""
        self._running = True
        logger.info("Mock WebSocket connected")
    
    async def listen(self):
        """Generate mock price updates."""
        import random
        
        while self._running:
            await asyncio.sleep(self.update_interval)
            
            for token_id in self._subscribed_tokens:
                # Generate random price with occasional arbitrage
                if "yes" in token_id:
                    if random.random() < 0.3:  # 30% chance of arbitrage
                        price = round(random.uniform(0.42, 0.48), 3)
                    else:
                        price = round(random.uniform(0.48, 0.52), 3)
                else:
                    if random.random() < 0.3:
                        price = round(random.uniform(0.42, 0.48), 3)
                    else:
                        price = round(random.uniform(0.48, 0.52), 3)
                
                old_price = self.prices.get(token_id)
                self.prices[token_id] = price
                self.last_update[token_id] = datetime.now()
                self.messages_received += 1
                
                if old_price != price:
                    self.on_price_update(token_id, price)
    
    async def close(self):
        """Close mock connection."""
        self._running = False
        logger.info("Mock WebSocket closed")

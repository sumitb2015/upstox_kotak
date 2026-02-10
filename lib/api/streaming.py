import upstox_client
from typing import Dict, List, Optional, Any
from upstox_client.feeder.market_data_feeder_v3 import MarketDataFeederV3
from upstox_client.feeder.market_data_streamer_v3 import MarketDataStreamerV3
from upstox_client.feeder import PortfolioDataStreamer
import threading
import logging
import os
import websocket
import ssl
from dotenv import load_dotenv
from lib.core.config import Config

# Load environment variables for client_id
load_dotenv("lib/core/.env")

# Configure logging for streaming updates
# logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('UpstoxStreamer')

class CustomMarketDataFeederV3(MarketDataFeederV3):
    """
    Custom Feeder that fetches the authorized WebSocket URL before connecting.
    Fixes the 403 Forbidden error caused by using the hardcoded URL.
    """
    def connect(self):
        if self.ws and self.ws.sock:
            return

        sslopt = {}
        
        headers = {}
        
        # FIX: Try to get authorized URL, fallback to standard URL with headers
        try:
            # First attempt: Get authorized URL
            api_instance = upstox_client.WebsocketApi(self.api_client)
            api_response = api_instance.get_market_data_feed_authorize_v3()
            ws_url = api_response.data.authorized_redirect_uri
            if Config.is_verbose():
                print(f"✅ Retrieved Authorized Market Data URL: {ws_url[:50]}...")
            
            # For authorized URL, we usually don't need additional headers, 
            # but some environments require them. We'll use them here as well.
            headers['Authorization'] = f"Bearer {self.api_client.configuration.access_token}"
            headers['x-api-key'] = self.api_client.configuration.api_key.get('x-api-key', os.getenv('client_id'))
        except Exception as e:
            print(f"⚠️  Failed to authorize via REST API: {e}. Falling back to standard URL.")
            ws_url = "wss://api.upstox.com/v3/feed/market-data-feed"
            headers['Authorization'] = f"Bearer {self.api_client.configuration.access_token}"
            headers['x-api-key'] = self.api_client.configuration.api_key.get('x-api-key', os.getenv('client_id'))
            
        if Config.is_streaming_debug():
            print(f"DEBUG [WS Handshake] Connecting to: {ws_url[:60]}...")
            # Mask token for security
            safe_headers = {k: "********" if k.lower() in ['authorization', 'x-api-key'] else v for k, v in headers.items()}
            print(f"DEBUG [WS Handshake] Headers: {safe_headers}")

        self.ws_url = ws_url
        self.headers = headers
        
        # Connect with retry logic in on_error if 403 occurs
        self.ws = websocket.WebSocketApp(ws_url,
                                         header=headers,
                                         on_open=self.on_open,
                                         on_message=self.on_message,
                                         on_error=self.handle_ws_error,
                                         on_close=self.on_close)

        t = threading.Thread(target=self.ws.run_forever,
                         kwargs={"sslopt": sslopt})
        t.daemon = True
        t.start()

    def handle_ws_error(self, ws, error):
        """Custom error handler to deal with 403 Forbidden retries without headers"""
        error_msg = str(error)
        if "403" in error_msg and hasattr(self, 'headers') and self.headers:
            print("⚠️  Handshake 403 Forbidden. Retrying without headers...")
            # Retry without headers
            self.headers = {}
            # Re-initialize WebSocketApp without headers
            self.ws = websocket.WebSocketApp(self.ws_url,
                                             header=self.headers,
                                             on_open=self.on_open,
                                             on_message=self.on_message,
                                             on_error=self.on_error, # Use default error handler for final retry
                                             on_close=self.on_close)
            t = threading.Thread(target=self.ws.run_forever,
                             kwargs={"sslopt": {}})
            t.daemon = True
            t.start()
        else:
            # Pass to default handler
            try:
                self.on_error(error)
            except TypeError:
                # Fallback if signature mismatch (e.g. self missing or extra args)
                try:
                    self.on_error(ws, error)
                except:
                    print(f"⚠️ Could not call on_error handler: {error}")

class CustomMarketDataStreamerV3(MarketDataStreamerV3):
    """
    Custom Streamer that uses CustomMarketDataFeederV3.
    """
    def connect(self):
        self.feeder = CustomMarketDataFeederV3(
            api_client=self.api_client, 
            instrumentKeys=self.instrumentKeys, 
            mode=self.mode, 
            on_open=self.handle_open, 
            on_message=self.handle_message, 
            on_error=self.handle_error, 
            on_close=self.handle_close
        )
        self.feeder.connect()

class UpstoxStreamer:
    """
    Advanced Helper class for real-time streaming of Market Data and Portfolio updates.
    Wraps Upstox SDK's Streamer classes for easier integration and event handling.
    """
    
    def __init__(self, access_token):
        self.access_token = access_token
        
        # Configure Upstox API Client
        self.configuration = upstox_client.Configuration()
        self.configuration.access_token = self.access_token
        self.configuration.timeout = 10
        
        # Debug: Verify configuration
        if self.access_token:
            print(f"🔑 Access Token configured: {self.access_token[:20]}... (length: {len(self.access_token)})")
            auth_settings = self.configuration.auth_settings()
            print(f"🔑 Auth Settings OAUTH2 value: {auth_settings['OAUTH2']['value'][:30]}...")
        else:
            print("⚠️ Access Token is None")
        
        
        self.api_client = upstox_client.ApiClient(self.configuration)
        
        # Streamer instances
        self.market_streamer = None
        self.portfolio_streamer = None
        
        # State tracking
        self.market_data_connected = False
        self.market_connecting = False
        self.portfolio_connected = False
        self.portfolio_connecting = False
        self.debug = False # Debug mode for raw data
        self.latest_feeds = {} # Cache for latest market data feeds
        
        # Callbacks
        self.market_callbacks = []
        self.order_callbacks = []
        self.trade_callbacks = []
        self.position_callbacks = []

    # --- Market Data Stream Methods ---
    def connect_market_data(self, instrument_keys=None, mode="ltpc", on_message=None):
        """
        Connect to market data stream.
        """
        if on_message:
            self.add_market_callback(on_message)

        if self.market_data_connected or self.market_connecting:
            if Config.is_verbose():
                print("Market data streamer already connected or connecting.")
            if instrument_keys:
                self.subscribe_market_data(instrument_keys, mode)
            return

        self.market_connecting = True
        keys = instrument_keys if instrument_keys else []
        
        # Initialize CustomMarketDataStreamerV3 (Handles Auth URL fetching)
        self.market_streamer = CustomMarketDataStreamerV3(
            api_client=self.api_client,
            instrumentKeys=keys,
            mode=mode
        )
        
        # Register default handlers
        self.market_streamer.on("open", self._on_market_open)
        self.market_streamer.on("message", self._on_market_message)
        self.market_streamer.on("error", self._on_market_error)
        self.market_streamer.on("close", self._on_market_close)
        
        # Connect in a separate thread
        if Config.is_verbose():
            print(f"Connecting to Market Data Stream (Mode: {mode})...")
        self.market_streamer.connect()

    def subscribe_market_data(self, instrument_keys, mode="ltpc"):
        """Subscribe to new instruments or change mode"""
        if self.market_streamer:
            self.market_streamer.subscribe(instrument_keys, mode)
            if Config.is_verbose():
                print(f"Subscribed to {len(instrument_keys)} instruments in {mode} mode.")
        else:
            print("Market streamer not initialized. Call connect_market_data first.")

    def unsubscribe_market_data(self, instrument_keys):
        """Unsubscribe from instruments"""
        if self.market_streamer:
            self.market_streamer.unsubscribe(instrument_keys)
            print(f"Unsubscribed from {len(instrument_keys)} instruments.")

    def change_market_mode(self, instrument_keys, mode):
        """Change streaming mode for specific instruments"""
        if self.market_streamer:
            self.market_streamer.change_mode(instrument_keys, mode)
            print(f"Changed mode to {mode} for {len(instrument_keys)} instruments.")

    def add_market_callback(self, callback):
        """Add a listener for market data updates"""
        if callback not in self.market_callbacks:
            self.market_callbacks.append(callback)

    # --- Portfolio Stream Methods ---

    def connect_portfolio(self, order_update=True, position_update=True, holding_update=False, gtt_update=False, on_order=None, on_position=None, on_holding=None):
        """
        Connect to portfolio stream for orders, trades, and positions.
        """
        if on_order:
            self.add_order_callback(on_order)
        if on_position:
            self.add_position_callback(on_position)
        if on_holding:
            self.add_holding_callback(on_holding)

        if self.portfolio_connected:
            print("Portfolio streamer already connected.")
            return
            
        if self.portfolio_connecting:
            if Config.is_verbose():
                print("Portfolio connection already in progress...")
            return

        self.portfolio_connecting = True
        self.portfolio_streamer = PortfolioDataStreamer(
            api_client=self.api_client,
            order_update=order_update,
            position_update=position_update,
            holding_update=holding_update,
            gtt_update=gtt_update
        )
        
        self.portfolio_streamer.on("open", self._on_portfolio_open)
        self.portfolio_streamer.on("message", self._on_portfolio_message)
        self.portfolio_streamer.on("error", self._on_portfolio_error)
        self.portfolio_streamer.on("close", self._on_portfolio_close)
        
        if Config.is_verbose():
            print("Connecting to Portfolio Stream...")
        self.portfolio_streamer.connect()

    def add_order_callback(self, callback):
        """Add a listener for order updates"""
        if callback not in self.order_callbacks:
            self.order_callbacks.append(callback)

    def add_trade_callback(self, callback):
        """Add a listener for trade updates"""
        if callback not in self.trade_callbacks:
            self.trade_callbacks.append(callback)
    
    def add_position_callback(self, callback):
        """Add a listener for position updates"""
        if callback not in self.position_callbacks:
            self.position_callbacks.append(callback)
    
    def add_holding_callback(self, callback):
        """Add a listener for holding updates"""
        if not hasattr(self, 'holding_callbacks'):
            self.holding_callbacks = []
        if callback not in self.holding_callbacks:
            self.holding_callbacks.append(callback)

    # --- Internal Event Handlers ---

    def enable_debug(self, enable=True):
        """Enable or disable debug mode for raw websocket data"""
        self.debug = enable
        Config.set_streaming_debug(enable)
        print(f"📡 Debug mode {'ENABLED' if enable else 'DISABLED'} for UpstoxStreamer")

    def _on_market_open(self):
        self.market_data_connected = True
        self.market_connecting = False
        logger.info("✅ Market Data Stream Connected")

    def _on_market_message(self, data):
        # Handle 'feeds' structure from V3 API
        if 'feeds' in data:
            feeds = data['feeds']
            for raw_key, feed_data in feeds.items():
                # Normalize key: Upstox often returns 'NSE_FO:58689' instead of 'NSE_FO|58689'
                instrument_key = raw_key.replace(':', '|')
                
                # Inject normalized instrument key
                feed_data['instrument_key'] = instrument_key
                
                # Unwrap fullFeed if present
                if 'fullFeed' in feed_data:
                    ff = feed_data['fullFeed']
                    # 0. Always unwrap everything from fullFeed first (to catch marketOHLC/indexOHLC)
                    feed_data.update(ff)
                    
                    # 1. Specifically unwrap Options/Futures (marketFF) if present
                    mff = ff.get('marketFF') or ff.get('market_ff')
                    if mff:
                        feed_data.update(mff)
                        ltpc = mff.get('ltpc') or mff.get('ltpC')
                        if ltpc: feed_data.update(ltpc)
                    
                    # 2. Specifically unwrap Indices (indexFF) if present
                    iff = ff.get('indexFF') or ff.get('index_ff')
                    if iff:
                        feed_data.update(iff)
                        ltpc = iff.get('ltpc') or iff.get('ltpC')
                        if ltpc: feed_data.update(ltpc)
                
                # Unwrap common top-level containers
                for wrapper in ['marketFF', 'indexFF', 'marketOHLC', 'indexOHLC']:
                    if wrapper in feed_data:
                        sub = feed_data[wrapper]
                        if isinstance(sub, dict):
                            feed_data.update(sub)
                            if 'ltpc' in sub: feed_data.update(sub['ltpc'])
                
                # Unwrap ltpc if present at top level
                ltpc = feed_data.get('ltpc') or feed_data.get('ltpC')
                if ltpc:
                    feed_data.update(ltpc)
                
                # --- Unwrap OHLC for low-latency candles ---
                # Indices use 'indexOHLC', Options use 'marketOHLC'
                mohlc = (feed_data.get('marketOHLC') or 
                         feed_data.get('indexOHLC') or 
                         feed_data.get('market_ohlc') or 
                         feed_data.get('ohlc'))
                
                if mohlc and isinstance(mohlc, dict) and 'ohlc' in mohlc:
                    for entry in mohlc['ohlc']:
                        interval = entry.get('interval')
                        if interval == 'I1':
                            # Store finalized minute candle info
                            feed_data['ohlc_1m'] = {
                                'open': float(entry.get('open', 0)),
                                'high': float(entry.get('high', 0)),
                                'low': float(entry.get('low', 0)),
                                'close': float(entry.get('close', 0)),
                                'timestamp': entry.get('ts') # ms string
                            }
                        elif interval == '1d':
                            feed_data['ohlc_day'] = entry
                
                # Ensure consistency
                if 'ltp' not in feed_data:
                    # Try to find it in nested structures if update failed
                    if 'last_price' in feed_data:
                        feed_data['ltp'] = feed_data['last_price']
                
                if 'last_price' not in feed_data and 'ltp' in feed_data:
                    feed_data['last_price'] = feed_data['ltp']

                # Update internal cache
                self.latest_feeds[instrument_key] = feed_data
                
                # Notify callbacks with normalized individual feed
                for cb in self.market_callbacks:
                    try:
                        cb(feed_data)
                    except Exception as e:
                        logger.error(f"Error in market callback: {e}")
        else:
            # Legacy or direct format check
            for cb in self.market_callbacks:
                try:
                    cb(data)
                except Exception as e:
                    logger.error(f"Error in market callback: {e}")

    def _on_market_error(self, error):
        self.market_connecting = False
        logger.error(f"❌ Market Data Stream Error: {error}")

    def _on_market_close(self, code=None, reason=None):
        self.market_data_connected = False
        self.market_connecting = False
        logger.warning(f"🔌 Market Data Stream Closed: Code={code}, Reason={reason}")
        # Auto-reconnect logic
        if not hasattr(self, '_terminating') or not self._terminating:
            logger.info("🔄 Attempting to reconnect Market Data Stream in 5 seconds...")
            threading.Timer(5.0, self.connect_market_data).start()

    def _on_portfolio_open(self):
        self.portfolio_connected = True
        self.portfolio_connecting = False
        logger.info("✅ Portfolio Stream Connected")

    def _on_portfolio_error(self, error):
        self.portfolio_connecting = False
        logger.error(f"❌ Portfolio Stream Error: {error}")

    def _on_portfolio_close(self, *args, **kwargs):
        self.portfolio_connected = False
        logger.warning(f"🔌 Portfolio Stream Closed: {args}")

    # --- Utility Methods ---

    def disconnect_all(self):
        """Disconnect all active streams with safety checks"""
        if self.market_streamer:
            try:
                # Try multiple possible method names for SDK streamer
                if hasattr(self.market_streamer, 'disconnect'):
                    self.market_streamer.disconnect()
                elif hasattr(self.market_streamer, 'stop'):
                    self.market_streamer.stop()
                elif hasattr(self.market_streamer, 'close'):
                    self.market_streamer.close()
            except Exception as e:
                print(f"⚠️ Error disconnecting market streamer: {e}")
                
        if self.portfolio_streamer:
            try:
                if hasattr(self.portfolio_streamer, 'disconnect'):
                    self.portfolio_streamer.disconnect()
                elif hasattr(self.portfolio_streamer, 'stop'):
                    self.portfolio_streamer.stop()
            except Exception as e:
                print(f"⚠️ Error disconnecting portfolio streamer: {e}")
                
        print("All streams disconnected.")

    def get_latest_data(self, instrument_key: str) -> Optional[Dict]:
        """Get the latest cached feed for a specific instrument from the internal cache."""
        return self.latest_feeds.get(instrument_key)

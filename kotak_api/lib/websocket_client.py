"""
WebSocketClient: Manages WebSocket connection and routes data to DataStore.

This module provides:
- WebSocket connection management
- Automatic message routing to DataStore
- Subscription handling
- Error and reconnection handling
"""

import json


class WebSocketClient:
    """
    WebSocket client that routes tick data to DataStore.
    
    Attributes:
        client (NeoAPI): Broker API client with WebSocket  
        data_store (DataStore): Data store for caching ticks
        subscriptions (list): List of subscribed tokens
    
    Example:
        >>> from lib.broker import BrokerClient
        >>> from lib.data_store import DataStore
        >>> 
        >>> broker = BrokerClient()
        >>> broker.authenticate()
        >>> data_store = DataStore()
        >>> 
        >>> ws_client = WebSocketClient(broker.client, data_store)
        >>> ws_client.subscribe(["26000", "26009"])  # Subscribe to Nifty, Bank Nifty
        >>> broker.client.on_message = ws_client.on_message
        >>> broker.client.on_error = ws_client.on_error
        >>> broker.client.on_open = ws_client.on_open
    """
    
    def __init__(self, client, data_store):
        """
        Initialize WebSocket client.
        
        Args:
            client (NeoAPI): Authenticated broker client
            data_store (DataStore): Data store instance
        """
        self.client = client
        self.data_store = data_store
        self.subscriptions = []
    
    def subscribe(self, tokens, is_index=False, is_depth=False, segment="nse_cm"):
        """
        Subscribe to instrument tokens.
        
        Args:
            tokens (list): List of instrument tokens (str or int)
            is_index (bool, optional): Whether tokens are indices. Defaults to False.
            is_depth (bool, optional): Subscribe to market depth. Defaults to False.
            segment (str, optional): Exchange segment. Defaults to "nse_cm".
        """
        # Format tokens as list of dicts (required by Kotak Neo API)
        instrument_list = [
            {"instrument_token": str(token), "exchange_segment": segment}
            for token in tokens
        ]
        
        # Store tokens for re-subscription
        self.subscriptions.extend([str(t) for t in tokens])
        
        print(f"  📡 Subscribing to {len(tokens)} instruments...")
        try:
            self.client.subscribe(
                instrument_tokens=instrument_list,
                isIndex=is_index,
                isDepth=is_depth
            )
            print(f"  ✅ Subscribed successfully")
        except Exception as e:
            print(f"  ❌ Subscription error: {e}")
    
    def unsubscribe(self, tokens, is_index=False, segment="nse_fo"):
        """
        Unsubscribe from instrument tokens.
        
        Args:
            tokens (list): List of instrument tokens to unsubscribe
            is_index (bool): Whether tokens are indices
            segment (str): Exchange segment
        """
        # Format tokens as list of dicts (required by Kotak Neo API)
        instrument_list = [
            {"instrument_token": str(token), "exchange_segment": segment}
            for token in tokens
        ]
        
        try:
            self.client.un_subscribe(
                instrument_tokens=instrument_list,
                isIndex=is_index
            )
            self.subscriptions = [s for s in self.subscriptions if s not in [str(t) for t in tokens]]
            print(f"  ✅ Unsubscribed from {len(tokens)} instruments")
        except Exception as e:
            print(f"  ❌ Unsubscribe error: {e}")
    
    def on_message(self, message, ws=None):
        """
        WebSocket message callback - routes data to DataStore.
        
        Args:
            message (str|dict): WebSocket message (JSON string or dict)
            ws: WebSocket instance (optional, provided by API)
        """
        try:
            # Parse message if it's a string
            if isinstance(message, str):
                message = json.loads(message)
            
            # Kotak Neo API sends ticks in 'data' array
            ticks = message.get('data', []) if isinstance(message, dict) else message
            
            # Process each tick
            for tick in ticks:
                # Get token (try both formats)
                token = str(tick.get('instrument_token', tick.get('tk', '')))
                if not token:
                    continue
                
                # Get LTP
                ltp = float(tick.get('ltp', 0) or 0)
                if ltp <= 0:
                    continue
                
                # Get percentage change
                pc = float(tick.get('nc', 0) or 0)  # 'nc' = Net Change %
                
                # Get Open Interest (optional)
                oi = int(tick.get('oi', 0) or 0) if 'oi' in tick else 0
                
                # Update DataStore
                self.data_store.update(
                    token=token,
                    ltp=ltp,
                    pc=pc,
                    oi=oi
                )
        except Exception as e:
            # Silent fail for parsing errors to avoid spam
            pass
    
    def on_error(self, error, ws=None):
        """
        WebSocket error callback.
        
        Args:
            error: Error object or message
            ws: WebSocket instance (optional, provided by API)
        """
        print(f"  🚨 [WebSocket] Error: {error}")
    
    def on_open(self, ws=None):
        """
        WebSocket connection opened callback.
        
        Args:
            ws: WebSocket instance (optional, provided by API)
        """
        print("  ✅ [WebSocket] Connection opened")
        # Note: Re-subscription removed to prevent conflicts during initial connection
        # The strategy handles subscription explicitly after connection
    
    def on_close(self, ws=None):
        """WebSocket connection closed callback."""
        print("  ⚠️ [WebSocket] Connection closed")

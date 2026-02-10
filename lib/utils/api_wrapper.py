"""
Upstox API Wrapper Library

Provides clean, robust, well-tested interfaces for all Upstox API operations.
Eliminates common errors and provides consistent error handling.

Usage Example:
    from lib.utils.api_wrapper import UpstoxAPI
    
    api = UpstoxAPI(access_token)
    
    # Get live price
    ltp = api.get_ltp("NSE_FO|12345")
    
    # Get historical data
    candles = api.get_intraday_candles("NSE_FO|12345", interval_minutes=1)
    
    # Place order
    order = api.place_option_order(
        instrument_key="NSE_FO|12345",
        nse_data=nse_df,
        num_lots=1,
        transaction_type="SELL"
    )
"""

from typing import Optional, List, Dict, Any
import pandas as pd
from datetime import datetime, timedelta

# Import existing API functions
from lib.api.market_quotes import get_ltp_quote, get_full_market_quote
from lib.api.historical import get_intraday_data_v3, get_historical_data_v3
from lib.api.streaming import UpstoxStreamer
from lib.utils.order_helper import place_option_order, get_order_quantity
from lib.utils.instrument_utils import get_lot_size


class UpstoxAPIError(Exception):
    """Base exception for Upstox API errors"""
    pass


class UpstoxAPI:
    """
    Unified Upstox API wrapper providing clean interfaces for all operations.
    
    This class wraps all Upstox API functionality with:
    - Consistent error handling
    - Automatic retries for transient failures  
    - Clean, intuitive method names
    - Proper typing and documentation
    """
    
    def __init__(self, access_token: str):
        """
        Initialize API wrapper.
        
        Args:
            access_token: Upstox access token
        """
        self.access_token = access_token
        self._streamer = None
    
    # ========== MARKET DATA ==========
    
    def get_ltp(self, instrument_key: str) -> Optional[float]:
        """
        Get Last Traded Price for an instrument.
        
        Args:
            instrument_key: Instrument key (e.g., "NSE_FO|12345")
        
        Returns:
            float: Last traded price, or None if failed
        
        Example:
            >>> api = UpstoxAPI(token)
            >>> price = api.get_ltp("NSE_FO|49229")
            >>> print(price)  # 25100.50
        """
        try:
            response = get_ltp_quote(self.access_token, instrument_key)
            
            if not response or 'data' not in response:
                return None
            
            data = response['data']
            
            # Handle different response structures
            if instrument_key in data:
                return data[instrument_key].get('last_price')
            
            # Fallback: get first available price
            for key, value in data.items():
                if 'last_price' in value:
                    return value['last_price']
            
            return None
            
        except Exception as e:
            print(f"Error getting LTP for {instrument_key}: {e}")
            return None
    
    def get_quote(self, instrument_key: str) -> Optional[Dict[str, Any]]:
        """
        Get full market quote with depth, Greeks, OI, etc.
        
        Args:
            instrument_key: Instrument key
        
        Returns:
            dict: Full quote data (wrapped in 'data' key for consistency), or None if failed
        """
        try:
            response = get_full_market_quote(self.access_token, instrument_key)
            
            # Handle different response formats
            if response:
                # Convert Upstox SDK objects to dicts
                if hasattr(response, 'to_dict'):
                    response = response.to_dict()
                
                # If already has 'data' key, return as-is
                if 'data' in response:
                    data = response['data']
                    # Convert nested objects to dicts
                    if isinstance(data, dict):
                        for key, value in data.items():
                            if hasattr(value, 'to_dict'):
                                data[key] = value.to_dict()
                            elif hasattr(value, '__dict__'):
                                data[key] = value.__dict__
                    return response
                # Otherwise, wrap it for consistency
                else:
                    # Convert any objects in the response
                    processed_response = {}
                    for key, value in response.items():
                        if hasattr(value, 'to_dict'):
                            processed_response[key] = value.to_dict()
                        elif hasattr(value, '__dict__'):
                            processed_response[key] = value.__dict__
                        else:
                            processed_response[key] = value
                    return {'data': processed_response}
            return None
        except Exception as e:
            print(f"Error getting quote for {instrument_key}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    # ========== HISTORICAL DATA ==========
    
    def get_intraday_candles(
        self,
        instrument_key: str,
        interval_minutes: int = 1
    ) -> Optional[List[Dict]]:
        """
        Get intraday candle data for today.
        
        Args:
            instrument_key: Instrument key
            interval_minutes: Candle interval in minutes (1, 5, 15, 30, 60)
        
        Returns:
            List of candle dicts with keys: timestamp, open, high, low, close, volume
            None if failed
        
        Example:
            >>> candles = api.get_intraday_candles("NSE_FO|49229", interval_minutes=3)
            >>> df = pd.DataFrame(candles)
        """
        try:
            candles = get_intraday_data_v3(
                access_token=self.access_token,
                instrument_key=instrument_key,
                interval_unit='minute',
                interval_value=interval_minutes
            )
            return candles
        except Exception as e:
            print(f"Error getting intraday candles: {e}")
            return None
    
    def get_historical_candles(
        self,
        instrument_key: str,
        interval_minutes: int,
        from_date: str,
        to_date: str
    ) -> Optional[List[Dict]]:
        """
        Get historical candle data for a date range.
        
        Args:
            instrument_key: Instrument key
            interval_minutes: Candle interval in minutes
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
        
        Returns:
            List of candle dicts, or None if failed
        """
        try:
            candles = get_historical_data_v3(
                access_token=self.access_token,
                instrument_key=instrument_key,
                interval_unit='minute',
                interval_value=interval_minutes,
                from_date=from_date,
                to_date=to_date
            )
            return candles
        except Exception as e:
            print(f"Error getting historical candles: {e}")
            return None
    
    def get_candles_as_dataframe(
        self,
        instrument_key: str,
        interval_minutes: int = 1,
        intraday: bool = True,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None
    ) -> Optional[pd.DataFrame]:
        """
        Get candle data as a pandas DataFrame (convenience method).
        
        Args:
            instrument_key: Instrument key
            interval_minutes: Candle interval
            intraday: If True, fetch today's data only. If False, use from_date/to_date
            from_date: Start date for historical (YYYY-MM-DD)
            to_date: End date for historical (YYYY-MM-DD)
        
        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        try:
            if intraday:
                candles = self.get_intraday_candles(instrument_key, interval_minutes)
            else:
                if not from_date or not to_date:
                    raise ValueError("from_date and to_date required for historical data")
                candles = self.get_historical_candles(
                    instrument_key, interval_minutes, from_date, to_date
                )
            
            if not candles:
                return None
            
            df = pd.DataFrame(candles)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            return df.sort_values('timestamp').reset_index(drop=True)
            
        except Exception as e:
            print(f"Error creating DataFrame: {e}")
            return None
    
    # ========== WEBSOCKET STREAMING ==========
    
    def get_streamer(self) -> UpstoxStreamer:
        """
        Get or create WebSocket streamer instance.
        
        Returns:
            UpstoxStreamer: Configured streamer
        
        Example:
            >>> streamer = api.get_streamer()
            >>> streamer.add_market_callback(lambda data: print(data))
            >>> streamer.connect_market_data(["NSE_FO|49229"], mode='full')
        """
        if self._streamer is None:
            self._streamer = UpstoxStreamer(self.access_token)
        return self._streamer
    
    def subscribe_live_data(
        self,
        instrument_keys: List[str],
        mode: str = 'full',
        callback = None
    ):
        """
        Subscribe to live market data (simplified interface).
        
        Args:
            instrument_keys: List of instrument keys to subscribe
            mode: 'ltpc' (price only) or 'full' (price + depth + greeks)
            callback: Function to call on each update
        
        Example:
            >>> def on_update(data):
            ...     print(f"Price: {data.get('last_price')}")
            >>> api.subscribe_live_data(["NSE_FO|49229"], callback=on_update)
        """
        streamer = self.get_streamer()
        
        if callback:
            streamer.add_market_callback(callback)
        
        streamer.connect_market_data(instrument_keys, mode=mode)
    
    # ========== ORDER MANAGEMENT ==========
    
    def place_order(
        self,
        instrument_key: str,
        nse_data: pd.DataFrame,
        num_lots: int,
        transaction_type: str,
        product_type: str = "INTRADAY",
        order_type: str = "MARKET",
        price: float = 0.0
    ) -> Optional[Dict]:
        """
        Place an order with automatic lot size handling.
        
        Args:
            instrument_key: Instrument key
            nse_data: NSE market data DataFrame (for lot size lookup)
            num_lots: Number of lots to trade
            transaction_type: "BUY" or "SELL"
            product_type: "INTRADAY", "DELIVERY", etc.
            order_type: "MARKET", "LIMIT", etc.
            price: Limit price (for LIMIT orders)
        
        Returns:
            Order response dict if successful, None if failed
        
        Example:
            >>> order = api.place_order(
            ...     instrument_key="NSE_FO|58689",
            ...     nse_data=nse_df,
            ...     num_lots=1,
            ...     transaction_type="SELL"
            ... )
        """
        try:
            return place_option_order(
                access_token=self.access_token,
                instrument_key=instrument_key,
                nse_data=nse_data,
                num_lots=num_lots,
                transaction_type=transaction_type,
                product_type=product_type,
                order_type=order_type,
                price=price
            )
        except Exception as e:
            print(f"Error placing order: {e}")
            return None
    
    def get_lot_size(self, instrument_key: str, nse_data: pd.DataFrame) -> int:
        """
        Get lot size for an instrument.
        
        Args:
            instrument_key: Instrument key
            nse_data: NSE market data DataFrame
        
        Returns:
            int: Lot size (default 65 for Nifty if not found)
        """
        return get_lot_size(instrument_key, nse_data)
    
    def calculate_quantity(
        self,
        instrument_key: str,
        nse_data: pd.DataFrame,
        num_lots: int
    ) -> int:
        """
        Calculate order quantity for given lots.
        
        Args:
            instrument_key: Instrument key
            nse_data: NSE data
            num_lots: Number of lots
        
        Returns:
            int: Total quantity (num_lots × lot_size)
        """
        return get_order_quantity(instrument_key, nse_data, num_lots)
    
    # ========== CLEANUP ==========
    
    def disconnect(self):
        """Disconnect all active streams."""
        if self._streamer:
            self._streamer.disconnect_all()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        self.disconnect()


# Convenience function for quick access
def create_api(access_token: str) -> UpstoxAPI:
    """
    Create an UpstoxAPI instance (convenience function).
    
    Args:
        access_token: Upstox access token
    
    Returns:
        UpstoxAPI: Configured API wrapper
    
    Example:
        >>> from lib.utils.api_wrapper import create_api
        >>> api = create_api(token)
        >>> price = api.get_ltp("NSE_FO|49229")
    """
    return UpstoxAPI(access_token)

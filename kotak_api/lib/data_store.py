"""
DataStore: Thread-safe cache for real-time market data from WebSocket.

This module provides a centralized data store that:
- Caches tick data (LTP, price change %, OI) from WebSocket
- Provides thread-safe access using locks
- Tracks last activity for connection monitoring
"""

import threading
import time


class DataStore:
    """
    Thread-safe cache for real-time market data.
    
    Attributes:
        tick_data (dict): {token: {'ltp': float, 'pc': float, 'oi': int, 'timestamp': float}}
        lock (threading.Lock): Thread synchronization
        last_activity (float): Timestamp of last data update
    
    Example:
        >>> data_store = DataStore()
        >>> data_store.update(token="12345", ltp=100.50, pc=2.5, oi=50000)
        >>> ltp = data_store.get_ltp("12345")
        100.5
    """
    
    def __init__(self):
        """Initialize empty data store with thread lock."""
        self.tick_data = {}
        self.lock = threading.Lock()
        self.last_activity = time.time()
    
    def update(self, token, ltp, pc=0.0, oi=0):
        """
        Update market data for a token.
        
        Args:
            token (str|int): Instrument token
            ltp (float): Last traded price
            pc (float, optional): Price change percentage. Defaults to 0.0.
            oi (int, optional): Open interest. Defaults to 0.
        """
        with self.lock:
            self.tick_data[str(token)] = {
                'ltp': float(ltp),
                'pc': float(pc),
                'oi': int(oi),
                'timestamp': time.time()
            }
            self.last_activity = time.time()
    
    def get_ltp(self, token):
        """
        Get last traded price for a token.
        
        Args:
            token (str|int): Instrument token
            
        Returns:
            float: LTP or 0.0 if not found
        """
        with self.lock:
            data = self.tick_data.get(str(token))
            return data['ltp'] if data else 0.0
    
    def get_change(self, token):
        """
        Get price change percentage for a token.
        
        Args:
            token (str|int): Instrument token
            
        Returns:
            float: Price change % or 0.0 if not found
        """
        with self.lock:
            data = self.tick_data.get(str(token))
            return data['pc'] if data else 0.0
    
    def get_oi(self, token):
        """
        Get open interest for a token.
        
        Args:
            token (str|int): Instrument token
            
        Returns:
            int: Open interest or 0 if not found
        """
        with self.lock:
            data = self.tick_data.get(str(token))
            return int(data['oi']) if data and 'oi' in data else 0
    
    def clear(self):
        """Clear all cached data."""
        with self.lock:
            self.tick_data.clear()
            self.last_activity = time.time()
    
    def get_all_tokens(self):
        """
        Get list of all cached tokens.
        
        Returns:
            list: List of token strings
        """
        with self.lock:
            return list(self.tick_data.keys())
    
    def is_stale(self, timeout=15):
        """
        Check if data is stale (no updates within timeout).
        
        Args:
            timeout (int, optional): Timeout in seconds. Defaults to 15.
            
        Returns:
            bool: True if stale, False otherwise
        """
        return (time.time() - self.last_activity) > timeout

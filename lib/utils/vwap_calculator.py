"""
Real-Time VWAP Calculator using Tick-Level Data

This module provides a tick-based VWAP calculator that:
1. Accumulates tick data from WebSocket feeds
2. Calculates VWAP in real-time without API calls
3. Automatically resets at session start (9:15 AM)
4. Provides accurate intraday VWAP matching broker charts
"""

import pandas as pd
from datetime import datetime, time as dt_time
from typing import Dict, Tuple
import logging

logger = logging.getLogger("VWAPCalculator")


class VWAPCalculator:
    """
    Calculate real-time VWAP from tick-level data.
    
    VWAP Formula: sum(price * volume) / sum(volume)
    
    Session Reset: Automatically resets at market open (9:15 AM)
    """
    
    def __init__(self, session_start_time: dt_time = dt_time(9, 15)):
        """
        Initialize VWAP calculator.
        
        Args:
            session_start_time: Time to reset VWAP (default 9:15 AM)
        """
        self.session_start_time = session_start_time
        self.data: Dict[str, Dict] = {}  # {symbol: {'pv_sum': float, 'v_sum': float, 'last_reset': datetime}}
        
    def _should_reset(self, symbol: str, current_time: datetime) -> bool:
        """Check if VWAP should be reset for new session."""
        if symbol not in self.data:
            return True
            
        last_reset = self.data[symbol]['last_reset']
        
        # Reset if:
        # 1. Current time is past session start
        # 2. Last reset was before today's session start
        today_session_start = datetime.combine(current_time.date(), self.session_start_time)
        
        if current_time >= today_session_start and last_reset < today_session_start:
            return True
            
        return False
    
    def add_tick(self, symbol: str, price: float, volume: int = 1, timestamp: datetime = None):
        """
        Add a tick to VWAP calculation.
        
        Args:
            symbol: Instrument symbol/key
            price: Tick price
            volume: Tick volume (default 1 if not available)
            timestamp: Tick timestamp (default: now)
        """
        if timestamp is None:
            timestamp = datetime.now()
            
        # Remove timezone if present
        if timestamp.tzinfo is not None:
            timestamp = timestamp.replace(tzinfo=None)
        
        # Check if reset needed
        if self._should_reset(symbol, timestamp):
            self.data[symbol] = {
                'pv_sum': 0.0,
                'v_sum': 0,
                'last_reset': timestamp
            }
            logger.info(f"🔄 VWAP reset for {symbol} at {timestamp.strftime('%H:%M:%S')}")
        
        # Accumulate price * volume and volume
        self.data[symbol]['pv_sum'] += price * volume
        self.data[symbol]['v_sum'] += volume
    
    def get_vwap(self, symbol: str) -> float:
        """
        Get current VWAP for symbol.
        
        Args:
            symbol: Instrument symbol/key
            
        Returns:
            Current VWAP value, or 0.0 if no data
        """
        if symbol not in self.data:
            return 0.0
            
        v_sum = self.data[symbol]['v_sum']
        if v_sum == 0:
            return 0.0
            
        return self.data[symbol]['pv_sum'] / v_sum
    
    def get_stats(self, symbol: str) -> Tuple[float, int, datetime]:
        """
        Get VWAP statistics for symbol.
        
        Args:
            symbol: Instrument symbol/key
            
        Returns:
            (vwap, total_volume, last_reset_time)
        """
        if symbol not in self.data:
            return (0.0, 0, datetime.now())
            
        data = self.data[symbol]
        vwap = self.get_vwap(symbol)
        
        return (vwap, data['v_sum'], data['last_reset'])
    
    def reset(self, symbol: str):
        """Manually reset VWAP for a symbol."""
        if symbol in self.data:
            del self.data[symbol]
            logger.info(f"🔄 Manual VWAP reset for {symbol}")
    
    def clear_all(self):
        """Clear all VWAP data."""
        self.data.clear()
        logger.info("🔄 Cleared all VWAP data")

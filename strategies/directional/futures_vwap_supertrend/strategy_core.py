"""
Futures VWAP Supertrend Strategy - Core Logic
"""

from abc import ABC, abstractmethod
import pandas as pd
import numpy as np
from typing import Tuple, Optional, List, Dict
from datetime import datetime
import threading
import logging

logger = logging.getLogger("VWAPSupertrendCore")

class Position:
    """Represents a single option position with tracking."""
    
    def __init__(self, direction: str, strike: int, entry_price: float, 
                 lot_size: int, pyramid_level: int, instrument_key: str,
                 pnl_multiplier: float = 50.0):
        self.direction = direction  # 'CE' or 'PE'
        self.strike = strike
        self.entry_price = entry_price
        self.current_price = entry_price
        self.lot_size = lot_size
        self.pyramid_level = pyramid_level
        self.instrument_key = instrument_key
        self.entry_time = datetime.now()
        self.lowest_price = entry_price  # For short positions, lower is better
        self.pnl_multiplier = pnl_multiplier
        
    def update_price(self, new_price: float):
        """Update current price and track lowest."""
        self.current_price = new_price
        if new_price < self.lowest_price:
            self.lowest_price = new_price
    
    def get_profit_pct(self) -> float:
        if self.entry_price == 0: return 0.0
        return (self.entry_price - self.current_price) / self.entry_price
    
    def get_pnl(self) -> float:
        return (self.entry_price - self.current_price) * self.lot_size * self.pnl_multiplier


class FuturesVWAPSupertrendCore(ABC):
    def __init__(self, config: dict):
        self.config = config
        self.positions: List[Position] = []
        self.current_direction = None
        self.current_vwap = 0.0
        self.current_st_direction = 0
        self.current_st_value = 0.0
        self.futures_price = 0.0
        self.lock = threading.RLock()
    
    def update_indicators(self, candles_df: pd.DataFrame):
        """
        Update Supertrend indicator using full historical + intraday data.
        Note: VWAP is NOT calculated here - it's handled separately in live.py
        using intraday-only data to ensure proper session reset.
        """
        from lib.utils.indicators import calculate_supertrend
        try:
            st_dir, st_val = calculate_supertrend(
                candles_df, 
                period=self.config.get('st_period', 10), 
                multiplier=self.config.get('st_multiplier', 3.0)
            )
            self.current_st_direction = st_dir
            self.current_st_value = st_val
            # Note: VWAP calculation moved to live.py to use intraday-only data
            # Note: futures_price is updated via WebSocket LTP, not from candle close
        except Exception as e:
            logger.error(f"Error updating indicators: {e}")

    def check_entry_signal(self, pcr: float = None) -> Tuple[bool, Optional[str], str]:
        if len(self.positions) > 0: return False, None, "Busy"
        
        # Safety Check: Ensure VWAP is initialized (not 0.0)
        # VWAP = 0.0 means VWAPCalculator hasn't accumulated ticks yet
        if self.current_vwap == 0.0:
            return False, None, "VWAP not initialized"
        
        # Trend Extension Check (Distance from VWAP)
        if self.current_vwap > 0:
            dist_pct = abs(self.futures_price - self.current_vwap) / self.current_vwap
            max_dist = self.config.get('max_vwap_distance_pct', 0.003)
            if dist_pct > max_dist:
                return False, None, f"Trend Extended: {dist_pct*100:.2f}% > {max_dist*100:.2f}% from VWAP"
        
        # CE Entry: Bearish (Price < VWAP AND Price < Supertrend Band)
        if self.futures_price < self.current_vwap and self.current_st_direction == -1 and self.futures_price < self.current_st_value:
            if self.config.get('oi_check_enabled') and pcr and pcr >= self.config['pcr_lower_threshold']:
                return False, None, f"PCR High: {pcr}"
            return True, 'CE', "VWAP + ST Bearish"
        
        # PE Entry: Bullish (Price > VWAP AND Price > Supertrend Band)
        if self.futures_price > self.current_vwap and self.current_st_direction == 1 and self.futures_price > self.current_st_value:
            if self.config.get('oi_check_enabled') and pcr and pcr <= self.config['pcr_upper_threshold']:
                return False, None, f"PCR Low: {pcr}"
            return True, 'PE', "VWAP + ST Bullish"
            
        return False, None, "Neutral"

    def check_exit_signal(self) -> Tuple[bool, Optional[str], str]:
        """Check for TSL (Tick-by-tick)"""
        if not self.positions: return False, None, ""
        
        # 1. TSL Check (Always Live)
        overall_lowest = min(pos.lowest_price for pos in self.positions)
        max_level = max(pos.pyramid_level for pos in self.positions)
        from strategies.directional.futures_vwap_supertrend.config import get_tsl_percentage
        tsl_pct = get_tsl_percentage(max_level)
        
        for pos in self.positions:
            if pos.current_price > overall_lowest * (1 + tsl_pct):
                return True, "TSL", f"Price {pos.current_price} hit TSL"

        return False, None, ""

    def check_exit_signal_candle(self) -> Tuple[bool, Optional[str], str]:
        """Check for Trend Reversal (Only on Candle Close)"""
        if not self.positions: return False, None, ""
        
        # 2. Trend Reversal
        if self.current_direction == 'CE' and (self.futures_price > self.current_vwap or self.current_st_direction == 1):
            return True, "REVERSAL", "Trend turned Bullish (Candle Close)"
        if self.current_direction == 'PE' and (self.futures_price < self.current_vwap or self.current_st_direction == -1):
            return True, "REVERSAL", "Trend turned Bearish (Candle Close)"

        return False, None, ""

    def update_position_prices(self, instrument_key: str, price: float):
        for pos in self.positions:
            if pos.instrument_key == instrument_key:
                pos.update_price(price)

    def clear_positions(self):
        self.positions.clear()
        self.current_direction = None

    def can_add_pyramid(self) -> Tuple[bool, str]:
        if len(self.positions) == 0 or len(self.positions) > self.config['max_pyramid_levels']:
            return False, "Not eligible"
        p_thresh = self.config['pyramid_profit_pct']
        if any(p.get_profit_pct() >= p_thresh for p in self.positions):
            return True, "Profit threshold hit"
        return False, "Waiting for profit"

    def get_trade_status(self) -> Dict:
        with self.lock:
            if not self.positions:
                return {}
            
            total_pnl = sum(p.get_pnl() for p in self.positions)
            total_lots = sum(p.lot_size for p in self.positions)
            overall_lowest = min(p.lowest_price for p in self.positions)
            max_level = max(p.pyramid_level for p in self.positions)
            
            from strategies.directional.futures_vwap_supertrend.config import get_tsl_percentage
            tsl_pct = get_tsl_percentage(max_level)
            tsl_price = overall_lowest * (1 + tsl_pct)
            
            # Use most recent position for 'current' display
            latest_pos = self.positions[-1]
            
            return {
                'count': len(self.positions),
                'lots': total_lots,
                'pnl': total_pnl,
                'ltp': latest_pos.current_price,
                'entry': latest_pos.entry_price,
                'lowest': overall_lowest,
                'tsl': tsl_price,
                'symbol': latest_pos.instrument_key.split('|')[-1] if '|' in latest_pos.instrument_key else latest_pos.instrument_key
            }

    @abstractmethod
    def execute_trade(self, *args, **kwargs): pass

"""
Futures VWAP EMA Strategy - Core Logic (Shared between Live and Backtest)

This core module contains all business logic for the strategy:
- VWAP and EMA indicator calculations
- Entry signal detection (CE and PE)
- Pyramiding logic with per-position profit tracking
- Trailing stop loss with dynamic tightening
- Exit signal detection

Reuses existing helper functions to avoid code duplication.
"""

from abc import ABC, abstractmethod
import pandas as pd
from typing import Tuple, Optional, List, Dict
from datetime import datetime
import threading


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
        """
        Calculate profit percentage for this position.
        For short positions: Profit when price decreases.
        """
        if self.entry_price == 0:
            return 0.0
        return (self.entry_price - self.current_price) / self.entry_price
    
    def get_profit_points(self) -> float:
        """Calculate profit in points."""
        return self.entry_price - self.current_price
    
    def get_pnl(self) -> float:
        """Calculate P&L for this position."""
        return (self.entry_price - self.current_price) * self.lot_size * self.pnl_multiplier


class FuturesVWAPEMACore(ABC):
    """
    Core strategy logic for Futures VWAP EMA Options Selling Strategy.
    
    Entry Logic:
    - CE: Sell when Futures < VWAP AND < EMA(20)
    - PE: Sell when Futures > VWAP AND > EMA(20)
    
    Pyramiding:
    - Add position when existing position profit >= 10%
    - Track per-position profit independently
    - Maximum 2 pyramid levels
    
    Exit Logic:
    - TSL hit (dynamic tightening: 20% -> 15% -> 10%)
    - Futures crosses back above/below VWAP
    """
    
    def __init__(self, config: dict):
        """Initialize with configuration parameters."""
        self.config = config
        
        # Position tracking
        self.positions: List[Position] = []
        self.current_direction = None  # 'CE' or 'PE'
        
        # Indicator values
        self.current_vwap = 0.0
        self.current_ema = 0.0
        self.futures_price = 0.0
        
        # State tracking
        self.total_pnl = 0.0
        self.daily_pnl = 0.0
        
        # Synchronization
        self.lock = threading.Lock()
    
    # ========== INDICATOR CALCULATIONS ==========
    
    def calculate_vwap(self, df: pd.DataFrame) -> float:
        """
        Calculate VWAP using library function.
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            Current VWAP value
        """
        from lib.utils.indicators import calculate_vwap
        try:
            return calculate_vwap(df)
        except Exception as e:
            print(f"Error calculating VWAP: {e}")
            return 0.0
    
    def calculate_ema(self, df: pd.DataFrame, period: int = 20) -> float:
        """
        Calculate EMA directly using TA-Lib.
        """
        import talib
        try:
            if df is None or df.empty:
                return 0.0
            ema_series = talib.EMA(df['close'].values, timeperiod=period)
            return float(ema_series[-1])
        except Exception as e:
            print(f"Error calculating EMA: {e}")
            return 0.0
    
    def update_indicators(self, candles_df: pd.DataFrame):
        """
        Update all indicator values from candle data.
        
        Args:
            candles_df: DataFrame with futures candle data
        """
        self.current_vwap = self.calculate_vwap(candles_df)
        self.current_ema = self.calculate_ema(candles_df, self.config['ema_period'])
        
        if not candles_df.empty:
            self.futures_price = candles_df['close'].iloc[-1]
    
    # ========== ENTRY LOGIC ==========
    
    def check_entry_signal(self, futures_price: float, vwap: float, ema: float, 
                          prev_price: float = None, prev_ema: float = None,
                          pcr: float = None) -> Tuple[bool, Optional[str], str]:
        """
        Check if entry conditions are met for CE or PE.
        
        Args:
            futures_price: Current futures price
            vwap: Current VWAP value
            ema: Current EMA value
            prev_price: Previous candle close (for crossover check)
            prev_ema: Previous candle EMA (for crossover check)
            
        Returns:
            (should_enter, direction, reason)
            direction: 'CE' or 'PE' or None
        """
        # Don't enter if we already have positions
        if len(self.positions) > 0:
            return False, None, "Already in position"
        
        # Require previous data for crossover check
        if prev_price is None or prev_ema is None:
            return False, None, "Waiting for previous candle data for crossover check"
        
        # CE Entry: Bearish Signal (Selling Calls)
        if futures_price < vwap:
            # 1. Standard Trigger: Crossover Below EMA
            is_crossover = prev_price >= prev_ema and futures_price < prev_ema
            
            # 2. Trend Trigger: Already below EMA
            is_trend_entry = self.config.get('allow_trend_entry', False) and futures_price < prev_ema

            if is_crossover or is_trend_entry:
                # Standard PCR check
                if self.config.get('oi_check_enabled', False) and pcr is not None:
                    lower_thresh = self.config.get('pcr_lower_threshold', 0.9)
                    if pcr >= lower_thresh:
                        return False, None, f"CE Entry skipped: PCR {pcr:.2f} >= {lower_thresh}"
                
                type_str = "Crossover" if is_crossover else "Trend Continuation"
                pcr_str = f", PCR={pcr:.2f}" if pcr is not None else ""
                reason = (f"CE Entry ({type_str}): LivePrice={futures_price:.2f} < PrevEMA={prev_ema:.2f}, VWAP={vwap:.2f}{pcr_str}")
                return True, 'CE', reason
        
        # PE Entry: Bullish Signal (Selling Puts)
        if futures_price > vwap:
            # 1. Standard Trigger: Crossover Above EMA
            is_crossover = prev_price <= prev_ema and futures_price > prev_ema
            
            # 2. Trend Trigger: Already above EMA
            is_trend_entry = self.config.get('allow_trend_entry', False) and futures_price > prev_ema

            if is_crossover or is_trend_entry:
                # Standard PCR check
                if self.config.get('oi_check_enabled', False) and pcr is not None:
                    upper_thresh = self.config.get('pcr_upper_threshold', 1.1)
                    if pcr <= upper_thresh:
                        return False, None, f"PE Entry skipped: PCR {pcr:.2f} <= {upper_thresh}"

                type_str = "Crossover" if is_crossover else "Trend Continuation"
                pcr_str = f", PCR={pcr:.2f}" if pcr is not None else ""
                reason = (f"PE Entry ({type_str}): LivePrice={futures_price:.2f} > PrevEMA={prev_ema:.2f}, VWAP={vwap:.2f}{pcr_str}")
                return True, 'PE', reason
        
        return False, None, f"No signal: Price={futures_price:.2f}, VWAP={vwap:.2f}, EMA={ema:.2f}, PCR={pcr if pcr else 'N/A'}"
    
    def can_add_pyramid(self) -> Tuple[bool, str]:
        """
        Check if we can add a pyramid position.
        
        Logic:
        - Check each existing position
        - If any position has profit >= 10%, can pyramid
        - Maximum 2 pyramid levels total
        
        Returns:
            (can_pyramid, reason)
        """
        if len(self.positions) == 0:
            return False, "No existing positions"
        
        # Check maximum pyramid levels
        max_levels = self.config['max_pyramid_levels']
        if len(self.positions) > max_levels:
            return False, f"Maximum pyramid levels ({max_levels}) reached"
            
        # Check maximum total lots
        max_lots = self.config.get('max_total_lots', 100) # Default high
        total_lots = sum(pos.lot_size for pos in self.positions)
        if total_lots + self.config['lot_size'] > max_lots:
            return False, f"Maximum total lots ({max_lots}) would be exceeded"
        
        # Check if any position has reached profit threshold
        profit_threshold = self.config['pyramid_profit_pct']
        
        for pos in self.positions:
            profit_pct = pos.get_profit_pct()
            if profit_pct >= profit_threshold:
                reason = f"Position at level {pos.pyramid_level} has {profit_pct*100:.1f}% profit (>= {profit_threshold*100:.0f}%)"
                return True, reason
        
        return False, f"No position has reached {profit_threshold*100:.0f}% profit yet"
    
    # ========== EXIT LOGIC ==========
    
    def calculate_tsl_price(self, pyramid_level: int, lowest_price: float) -> float:
        """
        Calculate trailing stop loss price for given pyramid level.
        
        Args:
            pyramid_level: Current pyramid level (0, 1, 2)
            lowest_price: Lowest price reached since entry
            
        Returns:
            TSL trigger price
        """
        base_pct = self.config['base_trailing_sl_pct']
        tightening_pct = self.config['tsl_tightening_pct']
        
        # Calculate TSL percentage for this level
        tsl_pct = base_pct - (pyramid_level * tightening_pct)
        tsl_pct = max(tsl_pct, 0.05)  # Minimum 5%
        
        # For short positions: TSL is ABOVE the lowest price
        # Exit when price rises more than TSL% from lowest
        tsl_price = lowest_price * (1 + tsl_pct)
        
        return tsl_price
    
    def check_exit_signal(self, futures_price: float, vwap: float) -> Tuple[bool, Optional[str], str]:
        """
        Check if any exit condition is met.
        
        Exit Conditions:
        1. TSL Hit: Any position's current price > TSL price
        2. VWAP Cross: Futures price crosses back (CE: above VWAP, PE: below VWAP)
        
        Args:
            futures_price: Current futures price
            vwap: Current VWAP value
            
        Returns:
            (should_exit, exit_type, reason)
        """
        if len(self.positions) == 0:
            return False, None, "No positions to exit"
        
        # Get overall lowest price across all positions
        overall_lowest = min(pos.lowest_price for pos in self.positions)
        
        # Get highest pyramid level
        max_level = max(pos.pyramid_level for pos in self.positions)
        
        # Calculate TSL for the highest pyramid level (tightest)
        tsl_price = self.calculate_tsl_price(max_level, overall_lowest)
        
        # Check each position's current price against TSL
        for pos in self.positions:
            if pos.current_price > tsl_price:
                reason = f"TSL Hit: Price {pos.current_price:.2f} > TSL {tsl_price:.2f} (Level {max_level}, Lowest: {overall_lowest:.2f})"
                return True, "TSL", reason
        
        # Check VWAP crossover based on direction
        if self.current_direction == 'CE':
            # CE: Exit if futures crosses above VWAP (bearish trend ending)
            if futures_price > vwap:
                reason = f"VWAP Cross: Futures {futures_price:.2f} > VWAP {vwap:.2f} (CE exit)"
                return True, "VWAP_CROSS", reason
        
        elif self.current_direction == 'PE':
            # PE: Exit if futures crosses below VWAP (bullish trend ending)
            if futures_price < vwap:
                reason = f"VWAP Cross: Futures {futures_price:.2f} < VWAP {vwap:.2f} (PE exit)"
                return True, "VWAP_CROSS", reason
        
        return False, None, "No exit conditions met"
    
    # ========== POSITION MANAGEMENT ==========
    
    def update_position_prices(self, option_price: float):
        """
        Update all positions with new option price.
        
        Args:
            option_price: Current option LTP
        """
        for pos in self.positions:
            pos.update_price(option_price)
    
    def get_total_pnl(self) -> float:
        """Calculate total P&L across all positions."""
        return sum(pos.get_pnl() for pos in self.positions)
    
    def get_position_summary(self) -> Dict:
        """Get summary of all positions."""
        if not self.positions:
            return {
                'num_positions': 0,
                'direction': None,
                'total_pnl': 0.0,
                'total_lots': 0
            }
        
        return {
            'num_positions': len(self.positions),
            'direction': self.current_direction,
            'total_pnl': self.get_total_pnl(),
            'total_lots': sum(pos.lot_size for pos in self.positions),
            'positions': [
                {
                    'level': pos.pyramid_level,
                    'entry': pos.entry_price,
                    'current': pos.current_price,
                    'lowest': pos.lowest_price,
                    'profit_pct': pos.get_profit_pct() * 100,
                    'pnl': pos.get_pnl()
                }
                for pos in self.positions
            ]
        }
    
    def clear_positions(self):
        """Clear all positions after exit."""
        self.positions.clear()
        self.current_direction = None
    
    # ========== ABSTRACT METHODS (Implementation-specific) ==========
    
    @abstractmethod
    def fetch_futures_data(self, *args, **kwargs):
        """
        Fetch futures candle data.
        
        Implementation varies:
        - Live: Fetch intraday data from API
        - Backtest: Fetch historical data from cache
        """
        pass
    
    @abstractmethod
    def fetch_option_price(self, *args, **kwargs):
        """
        Fetch current option price.
        
        Implementation varies:
        - Live: WebSocket or quote API
        - Backtest: Historical option data
        """
        pass
    
    @abstractmethod
    def execute_trade(self, *args, **kwargs):
        """
        Execute trade order.
        
        Implementation varies:
        - Live: Place order via broker API
        - Backtest: Record paper trade
        """
        pass

"""
Aggressive Renko Dip Core Logic
Removed Mega Trend filter for more frequent entries.
"""

import os
import sys
import json
import logging
from datetime import datetime
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Any

import pandas as pd
import numpy as np

# Adjust Paths to import library
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from lib.utils.indicators import calculate_renko_ema

# Reuse Renko components from dual_renko_dip if possible, but for simplicity, 
# I'll include the necessary logic here since this is a new standalone strategy.

logger = logging.getLogger("AggressiveRenkoCore")

class RenkoBrick:
    """Represents a single brick in the Renko chart."""
    def __init__(self, index, open, close, color, timestamp, low=None, high=None):
        self.index = index
        self.open = float(open)
        self.close = float(close)
        self.color = color 
        self.timestamp = timestamp
        self.high = float(high) if high is not None else max(self.open, self.close)
        self.low = float(low) if low is not None else min(self.open, self.close)

    def to_dict(self):
        return {
            'index': self.index,
            'open': self.open,
            'close': self.close,
            'color': self.color,
            'timestamp': self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else self.timestamp,
            'high': self.high,
            'low': self.low
        }

    @classmethod
    def from_dict(cls, d):
        ts = d['timestamp']
        if isinstance(ts, str):
            try: ts = datetime.fromisoformat(ts)
            except: pass
        return cls(d['index'], d['open'], d['close'], d['color'], ts, low=d['low'], high=d['high'])

class RenkoCalculator:
    """
    Manages Renko chart construction. 
    Maintains a list of bricks and calculates new bricks based on price updates.
    """
    def __init__(self, brick_size=10, reversal_brick_count=2, max_bricks=1000, max_bricks_per_update=100):
        self.brick_size = float(brick_size)
        self.reversal_brick_count = int(reversal_brick_count)
        self.max_bricks = max_bricks
        self.max_bricks_per_update = max_bricks_per_update
        
        # Validation
        if self.brick_size <= 0:
            raise ValueError(f"Brick size must be positive, got {brick_size}")
        if self.brick_size < 1:
            logger.warning(f"⚠️ Brick size {self.brick_size} is very small for Nifty")
        
        self.bricks: List[RenkoBrick] = [] 
        self.current_high = None 
        self.current_low = None  
        self.direction = 0

    def initialize(self, start_price):
        self.current_high = float(start_price)
        self.current_low = float(start_price)
        logger.info(f"🧱 Renko Initialized @ {start_price} (Brick: {self.brick_size})")

    def update(self, price, timestamp) -> int:
        price = float(price)
        
        # Lazy Initialization: If not initialized, start at first tick price
        if self.current_high is None or self.current_low is None:
            self.current_high = price
            self.current_low = price
            logger.info(f"🧱 Renko Lazy-Initialized @ {price}")
            return 0

        if not self.bricks and self.current_high == self.current_low:
            if price >= self.current_high + self.brick_size:
                self._add_brick('GREEN', self.current_high, self.current_high + self.brick_size, timestamp)
                self.direction = 1
                return 1
            elif price <= self.current_low - self.brick_size:
                self._add_brick('RED', self.current_low, self.current_low - self.brick_size, timestamp)
                self.direction = -1
                return 1
            return 0

        new_bricks_count = 0
        while True:
            added_this_loop = False
            if self.direction == 1: # Uptrend
                if price >= self.current_high + self.brick_size:
                    num_bricks = int((price - self.current_high) // self.brick_size)
                    num_bricks = min(num_bricks, 100) # Safety
                    for _ in range(num_bricks):
                        self._add_brick('GREEN', self.current_high, self.current_high + self.brick_size, timestamp)
                        new_bricks_count += 1
                    added_this_loop = True
            
            elif self.direction == -1: # Downtrend
                if price <= self.current_low - self.brick_size:
                    num_bricks = int((self.current_low - price) // self.brick_size)
                    num_bricks = min(num_bricks, 100) # Safety
                    for _ in range(num_bricks):
                        self._add_brick('RED', self.current_low, self.current_low - self.brick_size, timestamp)
                        new_bricks_count += 1
                    added_this_loop = True

            # Reversal Logic - Requires NX brick size movement
            if not added_this_loop:
                if self.direction == 1:  # In uptrend, check for reversal down
                     if price <= self.current_low - (self.reversal_brick_count * self.brick_size):  # ✅ Configurable reversal
                        num_bricks = int((self.current_low - price) // self.brick_size)
                        num_bricks = min(num_bricks, 100)
                        for _ in range(num_bricks):
                            self._add_brick('RED', self.current_low, self.current_low - self.brick_size, timestamp)
                            self.direction = -1 
                            new_bricks_count += 1
                        added_this_loop = True
                        
                elif self.direction == -1:  # In downtrend, check for reversal up
                    if price >= self.current_high + (self.reversal_brick_count * self.brick_size):  # ✅ Configurable reversal
                        num_bricks = int((price - self.current_high) // self.brick_size)
                        num_bricks = min(num_bricks, 100)
                        for _ in range(num_bricks):
                            self._add_brick('GREEN', self.current_high, self.current_high + self.brick_size, timestamp)
                            self.direction = 1
                            new_bricks_count += 1
                        added_this_loop = True
            
            if not added_this_loop:
                break
            
            if new_bricks_count >= self.max_bricks_per_update:
                logger.warning(f"⚠️ Renko safety cap reached: {new_bricks_count} bricks. Skipping remaining.")
                break
                
        return new_bricks_count

    def update_from_candle(self, high: float, low: float, timestamp) -> int:
        total_new = 0
        if self.direction == 1: 
            total_new += self.update(high, timestamp)
            total_new += self.update(low, timestamp)
        elif self.direction == -1: 
            total_new += self.update(low, timestamp)
            total_new += self.update(high, timestamp)
        else:
            total_new += self.update(high, timestamp)
            total_new += self.update(low, timestamp)
        return total_new

    def _add_brick(self, color, start, end, timestamp):
        idx = len(self.bricks) + 1
        brick = RenkoBrick(idx, start, end, color, timestamp, low=min(start, end), high=max(start, end))
        self.bricks.append(brick)
        self.current_high = brick.high
        self.current_low = brick.low
        
        # Trim old bricks to prevent memory issues
        if len(self.bricks) > self.max_bricks:
            self.bricks.pop(0)
            # Reindex remaining bricks
            for i, b in enumerate(self.bricks, start=1):
                b.index = i

    def to_dict(self):
        return {
            'brick_size': self.brick_size,
            'reversal_brick_count': self.reversal_brick_count,
            'bricks': [b.to_dict() for b in self.bricks],
            'current_high': self.current_high,
            'current_low': self.current_low,
            'direction': self.direction
        }

    def from_dict(self, d):
        self.brick_size = float(d.get('brick_size', self.brick_size))
        self.reversal_brick_count = int(d.get('reversal_brick_count', self.reversal_brick_count))
        self.bricks = [RenkoBrick.from_dict(b) for b in d.get('bricks', [])]
        self.current_high = float(d.get('current_high')) if d.get('current_high') is not None else None
        self.current_low = float(d.get('current_low')) if d.get('current_low') is not None else None
        self.direction = int(d.get('direction', 0))
    
    def get_brick_momentum(self, lookback: int = 10, max_time_window_minutes: int = 5) -> float:
        """
        Calculate bricks per minute over recent bricks within a time window.
        Only analyzes bricks formed in the last N minutes to avoid stale data.
        
        Args:
            lookback: Maximum number of bricks to analyze
            max_time_window_minutes: Only consider bricks from last N minutes
        
        Returns:
            Bricks per minute, or 0 if insufficient data
        """
        if len(self.bricks) < 2:
            return 0.0
        
        # Get current time
        now = datetime.now()
        
        # Filter bricks to only include recent ones (last N minutes)
        recent_bricks = []
        for brick in reversed(self.bricks):
            brick_ts = brick.timestamp
            
            # Handle both datetime objects and ISO strings
            if isinstance(brick_ts, str):
                brick_ts = datetime.fromisoformat(brick_ts)
            
            # Remove timezone info
            if hasattr(brick_ts, 'tzinfo') and brick_ts.tzinfo is not None:
                brick_ts = brick_ts.replace(tzinfo=None)
            
            # Check if brick is within time window
            time_diff_minutes = (now - brick_ts).total_seconds() / 60.0
            if time_diff_minutes <= max_time_window_minutes:
                recent_bricks.insert(0, brick)  # Insert at beginning to maintain order
            else:
                break  # Stop once we hit old bricks
        
        # Need at least 2 bricks to calculate momentum
        if len(recent_bricks) < 2:
            return 0.0
        
        # Limit to lookback count
        recent_bricks = recent_bricks[-lookback:]
        
        # Get timestamps
        first_ts = recent_bricks[0].timestamp
        last_ts = recent_bricks[-1].timestamp
        
        if isinstance(first_ts, str):
            first_ts = datetime.fromisoformat(first_ts)
        if isinstance(last_ts, str):
            last_ts = datetime.fromisoformat(last_ts)
        
        # Remove timezone info
        if hasattr(first_ts, 'tzinfo') and first_ts.tzinfo is not None:
            first_ts = first_ts.replace(tzinfo=None)
        if hasattr(last_ts, 'tzinfo') and last_ts.tzinfo is not None:
            last_ts = last_ts.replace(tzinfo=None)
        
        time_span = (last_ts - first_ts).total_seconds() / 60.0
        if time_span <= 0:
            # If multiple bricks form in the same tick/second, assume high momentum (10/min cap)
            return min(10.0, float(len(recent_bricks)))
        
        return len(recent_bricks) / time_span
    
    def is_market_trending(self, lookback: int = 20, max_reversal_pct: float = 0.40) -> bool:
        """
        Detect if market is trending vs. ranging.
        
        Args:
            lookback: Number of recent bricks to analyze
            max_reversal_pct: Maximum percentage of color changes allowed (0.40 = 40%)
        
        Returns:
            True if trending, False if ranging/choppy
        """
        if len(self.bricks) < lookback:
            return False  # Not enough data
        
        recent = self.bricks[-lookback:]
        color_changes = 0
        
        for i in range(1, len(recent)):
            if recent[i].color != recent[i-1].color:
                color_changes += 1
        
        reversal_pct = color_changes / (lookback - 1)
        
        if reversal_pct > max_reversal_pct:
            logger.warning(f"⚠️ Market is RANGING: {color_changes} reversals in {lookback} bricks ({reversal_pct*100:.1f}%)")
            return False
        
        logger.info(f"✅ Market is TRENDING: {color_changes} reversals in {lookback} bricks ({reversal_pct*100:.1f}%)")
        return True

class AggressiveRenkoCore(ABC):
    """
    Abstract Base Class defining the core business logic.
    Decoupled from API/Live execution details.
    """
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.nifty_brick_size = config.get('nifty_brick_size', 10)
        self.option_brick_pct = config.get('option_brick_pct', 0.08)
        self.min_option_brick = config.get('min_option_brick', 1.0)
        self.trend_streak = config.get('trend_streak', 3)
        self.trading_lots = config.get('trading_lots', 1)
        self.max_pyramid_lots = config.get('max_pyramid_lots', 3)
        
        self.nifty_ema_period = config.get('nifty_renko_ema_period', 20)
        self.rsi_period = config.get('rsi_period', 14)
        self.rsi_pivot = config.get('rsi_pivot', 50)

        # Calculators
        max_b = config.get('max_bricks_per_update', 100)
        rev_b = config.get('nifty_reversal_brick_count', 2)
        self.nifty_renko = RenkoCalculator(brick_size=self.nifty_brick_size, reversal_brick_count=rev_b, max_bricks_per_update=max_b)
        self.option_renko: Optional[RenkoCalculator] = None

        # State Variables
        self.entry_state = "WAITING" 
        self.active_positions = {}
        self.current_option_token = None 
        self.best_option_low = 999999.0
        self.rsi = 50.0                 
        self.pyramid_count = 0        
        self.bricks_since_last_lot = 0 
        self.avg_price = 0.0
        self.total_qty = 0
        self.active_symbols = {}
        self.is_warming_up = True

    def calculate_option_brick_size(self, price: float) -> float:
        raw_size = price * self.option_brick_pct
        return max(self.min_option_brick, round(raw_size, 1))

    def on_signal_brick(self, timestamp: datetime):
        if self.is_warming_up: return
        last_brick = self.nifty_renko.bricks[-1]
        logger.info(f"⚡ SIGNAL Brick #{last_brick.index}: {last_brick.color} @ {last_brick.close}")
        
        # Show progress toward entry signal
        if self.entry_state == "WAITING" and len(self.nifty_renko.bricks) >= self.trend_streak:
            last_n = self.nifty_renko.bricks[-self.trend_streak:]
            
            # Count consecutive same-color bricks
            consecutive_green = 0
            consecutive_red = 0
            
            for brick in reversed(self.nifty_renko.bricks):
                if brick.color == 'GREEN':
                    consecutive_green += 1
                    if consecutive_green > 0 and brick != self.nifty_renko.bricks[-consecutive_green]:
                        break
                else:
                    break
            
            for brick in reversed(self.nifty_renko.bricks):
                if brick.color == 'RED':
                    consecutive_red += 1
                    if consecutive_red > 0 and brick != self.nifty_renko.bricks[-consecutive_red]:
                        break
                else:
                    break
            
            # Show progress
            if consecutive_green > 0 and consecutive_green < self.trend_streak:
                remaining = self.trend_streak - consecutive_green
                next_target = last_brick.close + (self.nifty_brick_size * remaining)
                logger.info(f"📊 BULLISH PROGRESS: {consecutive_green}/{self.trend_streak} GREEN bricks | Need {remaining} more | Target: {next_target:.2f} | RSI: {self.rsi:.1f} (need > 50)")
            
            elif consecutive_red > 0 and consecutive_red < self.trend_streak:
                remaining = self.trend_streak - consecutive_red
                next_target = last_brick.close - (self.nifty_brick_size * remaining)
                logger.info(f"📊 BEARISH PROGRESS: {consecutive_red}/{self.trend_streak} RED bricks | Need {remaining} more | Target: {next_target:.2f} | RSI: {self.rsi:.1f} (need < 50)")
        
        self.check_trend_signal(timestamp)

    def check_trend_signal(self, timestamp: datetime):
        # Entry Time Filter - Don't enter before configured start time
        if 'entry_start_time' in self.config:
            entry_h, entry_m = map(int, self.config['entry_start_time'].split(':'))
            from datetime import time as dt_time
            if timestamp.time() < dt_time(entry_h, entry_m):
                return  # Too early to enter
        
        # Market Regime Filter - Only trade in trending markets
        if self.config.get('enable_regime_filter', True):
            lookback = self.config.get('regime_lookback_bricks', 20)
            max_reversal = self.config.get('max_reversal_pct', 0.40)
            
            if not self.nifty_renko.is_market_trending(lookback, max_reversal):
                if self.entry_state == "WAITING":
                    logger.debug(f"🔍 [FILTER] Regime Filter: Market ranging/choppy (Lookback: {lookback}, Reversals > {max_reversal*100}%)")
                return  # Market is ranging/choppy - skip entry
            
            # Check brick momentum (optional)
            if self.config.get('enable_momentum_filter', False):
                momentum = self.nifty_renko.get_brick_momentum(lookback=10)
                min_momentum = self.config.get('min_brick_momentum', 0.3)
                max_momentum = self.config.get('max_brick_momentum', 10.0)
                
                if momentum < min_momentum:
                    logger.warning(f"⚠️ Brick momentum too low ({momentum:.2f}/min < {min_momentum})")
                    return
                
                if momentum > max_momentum:
                    logger.warning(f"⚠️ Brick momentum too high ({momentum:.2f}/min > {max_momentum})")
                    return
        
        if len(self.nifty_renko.bricks) < self.trend_streak:
            if self.entry_state == "WAITING":
                logger.debug(f"🔍 [FILTER] Insufficient Bricks: {len(self.nifty_renko.bricks)} < {self.trend_streak}")
            return
        
        last_brick = self.nifty_renko.bricks[-1]
        last_n = self.nifty_renko.bricks[-self.trend_streak:]
        all_green = all(b.color == 'GREEN' for b in last_n)
        all_red = all(b.color == 'RED' for b in last_n)
        
        # Calculate Renko EMA
        try:
            brick_closes = [b.close for b in self.nifty_renko.bricks]
            renko_ema = calculate_renko_ema(brick_closes, self.nifty_ema_period)
        except Exception as e:
            # Not enough bricks yet or error
            if self.entry_state == "WAITING":
                logger.debug(f"EMA Calc pending: {e}")
            return

        # State: WAITING → Aggressive Entry
        if self.entry_state == "WAITING":
            if all_green:
                if self.rsi > self.rsi_pivot:
                    # EMA Filter: Close > EMA
                    if last_brick.close > renko_ema:
                        if 'PE' not in self.active_positions:
                            logger.info(f"🚀 AGGRESSIVE BULLISH ENTRY: Streak {self.trend_streak} + RSI {self.rsi:.1f} + Close {last_brick.close} > EMA {renko_ema:.2f} → SELL PE")
                            self.execute_entry("PE", timestamp)
                            self.entry_state = "IN_GREEN_TREND"
                            self.bricks_since_last_lot = 0
                    else:
                        logger.info(f"🛑 [FILTER] Bullish Signal but Pivot < EMA ({last_brick.close} < {renko_ema:.2f})")
                else:
                    logger.info(f"⏳ [WAITING] Bullish Streak {self.trend_streak} OK | But RSI {self.rsi:.1f} <= {self.rsi_pivot} (Wait for RSI)")
            
            elif all_red:
                if self.rsi < self.rsi_pivot:
                    # EMA Filter: Close < EMA
                    if last_brick.close < renko_ema:
                        if 'CE' not in self.active_positions:
                            logger.info(f"🚀 AGGRESSIVE BEARISH ENTRY: Streak {self.trend_streak} + RSI {self.rsi:.1f} + Close {last_brick.close} < EMA {renko_ema:.2f} → SELL CE")
                            self.execute_entry("CE", timestamp)
                            self.entry_state = "IN_RED_TREND"
                            self.bricks_since_last_lot = 0
                    else:
                        logger.info(f"🛑 [FILTER] Bearish Signal but Pivot > EMA ({last_brick.close} > {renko_ema:.2f})")
                else:
                    logger.info(f"⏳ [WAITING] Bearish Streak {self.trend_streak} OK | But RSI {self.rsi:.1f} >= {self.rsi_pivot} (Wait for RSI)")
            
            # If colors are mixed, show what we have in debug
            else:
                 mixed_colors = [b.color for b in last_n]
                 # logger.debug(f"🔍 [WAITING] Mixed Colors in Streak: {mixed_colors}")

        # DISABLED: Nifty Signal Reversal Exit (User wants only Option TSL)
        # # Signal Reversal Exit (for Aggressive strategy)
        # elif self.entry_state == "IN_GREEN_TREND" and all_red:
        #      logger.warning("🚨 SIGNAL REVERSAL: Trend turned RED → EXIT PE")
        #      self.execute_exit("PE", "Trend Reversal", timestamp)
        #      self.entry_state = "WAITING"
        #
        # elif self.entry_state == "IN_RED_TREND" and all_green:
        #      logger.warning("🚨 SIGNAL REVERSAL: Trend turned GREEN → EXIT CE")
        #      self.execute_exit("CE", "Trend Reversal", timestamp)
        #      self.entry_state = "WAITING"

        # DEPRECATED: Pyramiding now handled by Option Renko (see on_option_brick)
        # # Pyramiding Logic (Simplified - Add on Trend Continuation)
        # elif self.entry_state == "IN_GREEN_TREND":
        #     if last_brick.color == 'GREEN':
        #         self.bricks_since_last_lot += 1
        #         if self.bricks_since_last_lot >= self.config.get('resumption_streak', 2):
        #             if self.pyramid_count < (self.max_pyramid_lots - 1):
        #                 logger.info(f"🔥 PYRAMID: Trend Continuation ({self.bricks_since_last_lot} bricks). Adding PE lot.")
        #                 self.execute_entry("PE", timestamp, is_pyramid=True)
        #                 self.pyramid_count += 1
        #                 self.bricks_since_last_lot = 0 # Reset
        #     else:
        #         self.bricks_since_last_lot = 0 # Reset on counter brick
        #
        # elif self.entry_state == "IN_RED_TREND":
        #     if last_brick.color == 'RED':
        #         self.bricks_since_last_lot += 1
        #         if self.bricks_since_last_lot >= self.config.get('resumption_streak', 2):
        #             if self.pyramid_count < (self.max_pyramid_lots - 1):
        #                 logger.info(f"🔥 PYRAMID: Trend Continuation ({self.bricks_since_last_lot} bricks). Adding CE lot.")
        #                 self.execute_entry("CE", timestamp, is_pyramid=True)
        #                 self.pyramid_count += 1
        #                 self.bricks_since_last_lot = 0 # Reset
        #     else:
        #         self.bricks_since_last_lot = 0 # Reset on counter brick

    def on_option_brick(self, timestamp: datetime):
        """Called when option premium forms a new Renko brick."""
        if not self.option_renko or not self.option_renko.bricks:
            return
        
        # Check if pyramiding is enabled
        if not self.config.get('enable_pyramiding', False):
            return
        
        # Get pyramid interval from config
        pyramid_interval = self.config.get('pyramid_interval', 3)
        
        # Need enough bricks to check for continuation
        if len(self.option_renko.bricks) < pyramid_interval:
            return
        
        # Check if last N bricks are all same color (profit direction)
        last_n = self.option_renko.bricks[-pyramid_interval:]
        all_green = all(b.color == 'GREEN' for b in last_n)
        all_red = all(b.color == 'RED' for b in last_n)
        
        # For selling options, GREEN bricks = profit (premium falling)
        # Pyramid when option premium moves in profit direction
        if self.entry_state == "IN_GREEN_TREND" and all_green:
            # Selling PE, premium falling (GREEN bricks) = profit
            if self.pyramid_count < (self.max_pyramid_lots - 1):
                logger.info(f"🔥 PYRAMID: Option moved {pyramid_interval} GREEN bricks (profit). Adding PE lot.")
                self.execute_entry("PE", timestamp, is_pyramid=True)
                self.pyramid_count += 1
        
        elif self.entry_state == "IN_RED_TREND" and all_green:
            # Selling CE, premium falling (GREEN bricks) = profit
            if self.pyramid_count < (self.max_pyramid_lots - 1):
                logger.info(f"🔥 PYRAMID: Option moved {pyramid_interval} GREEN bricks (profit). Adding CE lot.")
                self.execute_entry("CE", timestamp, is_pyramid=True)
                self.pyramid_count += 1

    @abstractmethod
    def execute_entry(self, option_type: str, timestamp: datetime, is_pyramid: bool = False):
        pass

    @abstractmethod
    def execute_exit(self, option_type: str, reason: str, timestamp: Optional[datetime] = None):
        pass

    def save_state(self, state_file: str):
        try:
            # Optimize: Only save last 100 bricks to keep state file small
            nifty_renko_dict = self.nifty_renko.to_dict()
            nifty_renko_dict['bricks'] = [b.to_dict() for b in self.nifty_renko.bricks[-100:]]
            
            option_renko_dict = None
            if self.option_renko:
                option_renko_dict = self.option_renko.to_dict()
                option_renko_dict['bricks'] = [b.to_dict() for b in self.option_renko.bricks[-100:]]
            
            state = {
                'entry_state': self.entry_state,
                'best_option_low': self.best_option_low,
                'current_option_token': self.current_option_token,
                'nifty_renko': nifty_renko_dict,
                'option_renko': option_renko_dict,
                'pyramid_count': self.pyramid_count,
                'bricks_since_last_lot': self.bricks_since_last_lot,
                'active_positions': self.active_positions,
                'active_symbols': self.active_symbols,
                'avg_price': self.avg_price,
                'total_qty': self.total_qty,
                'last_update': datetime.now().isoformat()
            }
            with open(state_file, 'w') as f:
                json.dump(state, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving state: {e}")

    def load_state(self, state_file: str) -> bool:
        if not os.path.exists(state_file): return False
        try:
            with open(state_file, 'r') as f:
                state = json.load(f)
            last_upd = datetime.fromisoformat(state['last_update'])
            if last_upd.date() != datetime.now().date(): return False
            self.entry_state = state.get('entry_state', "WAITING")
            self.best_option_low = state.get('best_option_low', 999999.0)
            self.current_option_token = state.get('current_option_token')
            self.pyramid_count = state.get('pyramid_count', 0)
            self.bricks_since_last_lot = state.get('bricks_since_last_lot', 0)
            self.active_positions = state.get('active_positions', {})
            self.active_symbols = state.get('active_symbols', {})
            self.avg_price = state.get('avg_price', 0.0)
            self.total_qty = state.get('total_qty', 0)
            self.nifty_renko.from_dict(state['nifty_renko'])
            if state.get('option_renko'):
                # Initialize with current config values, then overwrite with stored state
                b_size = state['option_renko'].get('brick_size', 1.0)
                rev_b = self.config.get('tsl_brick_count', 2)
                self.option_renko = RenkoCalculator(brick_size=b_size, reversal_brick_count=rev_b)
                self.option_renko.from_dict(state['option_renko'])
            logger.info("✅ Aggressive Strategy state RESTORED.")
            return True
        except Exception as e:
            logger.error(f"Error loading state: {e}")
            return False

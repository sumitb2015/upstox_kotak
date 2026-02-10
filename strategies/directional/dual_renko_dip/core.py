"""
Dual-Renko (Mega Trend) Core Logic
Shared between Live and Backtest implementations.
"""

import os
import json
import logging
from datetime import datetime
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Any

import pandas as pd
import numpy as np

# Configure Logger for Core
logger = logging.getLogger("DualRenkoCore")

class RenkoBrick:
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

    def __repr__(self):
        return f"Brick({self.index}, {self.color}, {self.open}-{self.close})"

class RenkoCalculator:
    def __init__(self, brick_size=15):
        self.brick_size = float(brick_size)
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
                    diff = price - self.current_high
                    num_bricks = int(diff // self.brick_size)
                    
                    if num_bricks > 500:
                        logger.warning(f"⚠️ DATA SPIKE: Attempted to create {num_bricks} bricks. Clamping to 500.")
                        num_bricks = 500
                        
                    for _ in range(num_bricks):
                        self._add_brick('GREEN', self.current_high, self.current_high + self.brick_size, timestamp)
                        new_bricks_count += 1
                    added_this_loop = True
            
            elif self.direction == -1: # Downtrend
                if price <= self.current_low - self.brick_size:
                    diff = self.current_low - price
                    num_bricks = int(diff // self.brick_size)
                    
                    if num_bricks > 500:
                        logger.warning(f"⚠️ DATA SPIKE: Attempted to create {num_bricks} bricks. Clamping to 500.")
                        num_bricks = 500
                        
                    for _ in range(num_bricks):
                        self._add_brick('RED', self.current_low, self.current_low - self.brick_size, timestamp)
                        new_bricks_count += 1
                    added_this_loop = True

            # Reversal
            if not added_this_loop:
                if self.direction == 1: 
                     if price <= self.current_low - self.brick_size:
                        diff = self.current_low - price
                        num_bricks = int(diff // self.brick_size)
                        
                        # SAFETY CLAMP: Prevent hang on bad data spikes
                        if num_bricks > 500:
                            logger.warning(f"⚠️ DATA SPIKE: Attempted to create {num_bricks} bricks. Clamping to 500.")
                            num_bricks = 500
                            
                        for _ in range(num_bricks):
                            self._add_brick('RED', self.current_low, self.current_low - self.brick_size, timestamp)
                            self.direction = -1 
                            new_bricks_count += 1
                        added_this_loop = True
                        
                elif self.direction == -1: 
                    if price >= self.current_high + self.brick_size:
                        diff = price - self.current_high
                        num_bricks = int(diff // self.brick_size)
                        
                        # SAFETY CLAMP: Prevent hang on bad data spikes
                        if num_bricks > 500:
                            logger.warning(f"⚠️ DATA SPIKE: Attempted to create {num_bricks} bricks. Clamping to 500.")
                            num_bricks = 500
                            
                        for _ in range(num_bricks):
                            self._add_brick('GREEN', self.current_high, self.current_high + self.brick_size, timestamp)
                            self.direction = 1
                            new_bricks_count += 1
                        added_this_loop = True
            
            if not added_this_loop:
                break
                
        return new_bricks_count

    def update_from_candle(self, high: float, low: float, timestamp) -> int:
        """
        Update Renko state using High and Low of a candle.
        Correctly orders High/Low based on current direction to capture all bricks.
        """
        total_new = 0
        if self.direction == 1: # Uptrend: Check High first, then Low for potential reversal
            total_new += self.update(high, timestamp)
            total_new += self.update(low, timestamp)
        elif self.direction == -1: # Downtrend: Check Low first, then High for potential reversal
            total_new += self.update(low, timestamp)
            total_new += self.update(high, timestamp)
        else: # Neutral: check both, starting with high
            total_new += self.update(high, timestamp)
            total_new += self.update(low, timestamp)
        return total_new

    def _add_brick(self, color, start, end, timestamp):
        idx = len(self.bricks) + 1
        brick = RenkoBrick(idx, start, end, color, timestamp, low=min(start, end), high=max(start, end))
        self.bricks.append(brick)
        self.current_high = brick.high
        self.current_low = brick.low

    def to_dict(self):
        return {
            'brick_size': self.brick_size,
            'bricks': [b.to_dict() for b in self.bricks],
            'current_high': self.current_high,
            'current_low': self.current_low,
            'direction': self.direction
        }

    def from_dict(self, d):
        self.brick_size = float(d.get('brick_size', self.brick_size))
        self.bricks = [RenkoBrick.from_dict(b) for b in d.get('bricks', [])]
        self.current_high = float(d.get('current_high')) if d.get('current_high') is not None else None
        self.current_low = float(d.get('current_low')) if d.get('current_low') is not None else None
        self.direction = int(d.get('direction', 0))

class DualRenkoCore(ABC):
    """
    Core Dual-Renko Strategy logic.
    """
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.nifty_brick_size = config.get('nifty_brick_size', 5)
        self.mega_brick_size = config.get('mega_brick_size', 30)
        self.option_brick_pct = config.get('option_brick_pct', 0.075)
        self.min_option_brick = config.get('min_option_brick', 2.0)
        self.trend_streak = config.get('trend_streak', 3)
        self.mega_min_bricks = config.get('mega_min_bricks', 1)
        self.trading_lots = config.get('trading_lots', 1)
        self.max_pyramid_lots = config.get('max_pyramid_lots', 3)
        
        self.rsi_period = config.get('rsi_period', 14)
        self.rsi_pivot = config.get('rsi_pivot', 50)
        self.rsi_overbought = config.get('rsi_overbought', 80)
        self.rsi_oversold = config.get('rsi_oversold', 20)

        # Calculators
        self.nifty_renko = RenkoCalculator(brick_size=self.nifty_brick_size)
        self.mega_renko = RenkoCalculator(brick_size=self.mega_brick_size)
        self.option_renko: Optional[RenkoCalculator] = None

        # State Variables
        self.entry_state = "WAITING" 
        self.active_positions = {}
        self.current_option_token = None 
        self.best_option_low = 999999.0
        self.rsi = 50.0                 
        self.pyramid_count = 0        
        self.pullback_active = False 

    def calculate_option_brick_size(self, price: float) -> float:
        raw_size = price * self.option_brick_pct
        if price < 50:
            return max(self.min_option_brick, round(raw_size, 1))
        elif price < 200:
            return round(raw_size, 1)
        else:
            return min(50.0, round(raw_size, 1))

    def on_mega_brick(self, timestamp: datetime):
        last_brick = self.mega_renko.bricks[-1]
        logger.info(f"🌌 MEGA TREND Brick #{last_brick.index}: {last_brick.color} @ {last_brick.close}")
        
        # Structural Reversal Exit
        if self.entry_state == "IN_GREEN_TREND" and self.mega_renko.direction == -1:
            logger.warning("🚨 MEGA REVERSAL: Macro Trend turned RED (Downtrend) → EMERGENCY EXIT")
            self.execute_exit("PE", "Mega Reversal", timestamp)
            self.entry_state = "WAITING"
        elif self.entry_state == "IN_RED_TREND" and self.mega_renko.direction == 1:
            logger.warning("🚨 MEGA REVERSAL: Macro Trend turned GREEN (Uptrend) → EMERGENCY EXIT")
            self.execute_exit("CE", "Mega Reversal", timestamp)
            self.entry_state = "WAITING"

    def on_signal_brick(self, timestamp: datetime):
        last_brick = self.nifty_renko.bricks[-1]
        logger.info(f"⚡ SIGNAL Brick #{last_brick.index}: {last_brick.color} @ {last_brick.close}")
        self.check_trend_signal(timestamp)

    def check_trend_signal(self, timestamp: datetime):
        if len(self.nifty_renko.bricks) < self.trend_streak:
            return
        
        last_n = self.nifty_renko.bricks[-self.trend_streak:]
        all_green = all(b.color == 'GREEN' for b in last_n)
        all_red = all(b.color == 'RED' for b in last_n)
        
        # State: WAITING → Check for new trend
        if self.entry_state == "WAITING":
            self.pyramid_count = 0
            self.pullback_active = False

            mega_count = 0
            if self.mega_renko.bricks:
                curr_dir = self.mega_renko.direction
                for b in reversed(self.mega_renko.bricks):
                    if (b.color == 'GREEN' and curr_dir == 1) or (b.color == 'RED' and curr_dir == -1):
                        mega_count += 1
                    else: break

            if all_green:
                if self.mega_renko.direction == 1 and mega_count >= self.mega_min_bricks:
                    if self.rsi_pivot < self.rsi < self.rsi_overbought:
                        if 'PE' not in self.active_positions:
                            logger.info(f"🚀 BULLISH ENTRY: Sig Streak {self.trend_streak} + Mega Streak {mega_count} + RSI {self.rsi:.1f} → SELL PE")
                            self.execute_entry("PE", timestamp)
                            self.entry_state = "IN_GREEN_TREND"
            
            elif all_red:
                if self.mega_renko.direction == -1 and mega_count >= self.mega_min_bricks:
                    if self.rsi_oversold < self.rsi < self.rsi_pivot:
                        if 'CE' not in self.active_positions:
                            logger.info(f"🚀 BEARISH ENTRY: Sig Streak {self.trend_streak} + Mega Streak {mega_count} + RSI {self.rsi:.1f} → SELL CE")
                            self.execute_entry("CE", timestamp)
                            self.entry_state = "IN_RED_TREND"

        # State: IN_GREEN_TREND → Check for Pyramiding
        elif self.entry_state == "IN_GREEN_TREND":
            if self.nifty_renko.direction == -1: 
                if not self.pullback_active:
                    logger.info("🔄 BULLISH PULLBACK Detected: Signal Renko flipped RED.")
                    self.pullback_active = True
            
            elif self.pullback_active:
                bricks_in_streak = 0
                for b in reversed(self.nifty_renko.bricks):
                    if b.color == 'GREEN': bricks_in_streak += 1
                    else: break
                
                if bricks_in_streak >= 2:
                    if self.pyramid_count < (self.max_pyramid_lots - 1):
                        logger.info(f"🔥 PYRAMID: Bullish Resumption detected ({bricks_in_streak} bricks). Adding PE lot.")
                        self.execute_entry("PE", timestamp, is_pyramid=True)
                        self.pyramid_count += 1
                    self.pullback_active = False 

        # State: IN_RED_TREND → Check for Pyramiding
        elif self.entry_state == "IN_RED_TREND":
            if self.nifty_renko.direction == 1: 
                if not self.pullback_active:
                    logger.info("🔄 BEARISH PULLBACK Detected: Signal Renko flipped GREEN.")
                    self.pullback_active = True
            
            elif self.pullback_active:
                bricks_in_streak = 0
                for b in reversed(self.nifty_renko.bricks):
                    if b.color == 'RED': bricks_in_streak += 1
                    else: break
                
                if bricks_in_streak >= 2:
                    if self.pyramid_count < (self.max_pyramid_lots - 1):
                        logger.info(f"🔥 PYRAMID: Bearish Resumption detected ({bricks_in_streak} bricks). Adding CE lot.")
                        self.execute_entry("CE", timestamp, is_pyramid=True)
                        self.pyramid_count += 1
                    self.pullback_active = False 

    def on_option_brick(self, timestamp: datetime):
        if not self.option_renko or not self.option_renko.bricks:
            return

        last_brick = self.option_renko.bricks[-1]
        logger.info(f"🏁 Option Brick #{last_brick.index} Closed: {last_brick.color} @ {last_brick.close}")

        if len(self.option_renko.bricks) >= 3:
            last_3 = self.option_renko.bricks[-3:]
            if all(b.color == 'GREEN' for b in last_3):
                logger.info("🛡️ OPTION REVERSAL: 3 Green Bricks (Premium Rising) → EXIT")
                if self.entry_state == "IN_GREEN_TREND": 
                    self.execute_exit("PE", "Option Reversal", timestamp)
                    self.entry_state = "WAITING"
                elif self.entry_state == "IN_RED_TREND": 
                    self.execute_exit("CE", "Option Reversal", timestamp)
                    self.entry_state = "WAITING"

    @abstractmethod
    def execute_entry(self, option_type: str, timestamp: datetime, is_pyramid: bool = False):
        pass

    @abstractmethod
    def execute_exit(self, option_type: str, reason: str, timestamp: Optional[datetime] = None):
        pass

    def save_state(self, state_file: str):
        try:
            state = {
                'entry_state': self.entry_state,
                'best_option_low': self.best_option_low,
                'current_option_token': self.current_option_token,
                'mega_renko': self.mega_renko.to_dict(),
                'nifty_renko': self.nifty_renko.to_dict(),
                'option_renko': self.option_renko.to_dict() if self.option_renko else None,
                'pyramid_count': self.pyramid_count,
                'pullback_active': self.pullback_active,
                'active_positions': self.active_positions,
                'last_update': datetime.now().isoformat()
            }
            with open(state_file, 'w') as f:
                json.dump(state, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving state: {e}")

    def load_state(self, state_file: str) -> bool:
        if not os.path.exists(state_file):
            return False
        
        try:
            with open(state_file, 'r') as f:
                state = json.load(f)
            
            last_upd = datetime.fromisoformat(state['last_update'])
            if last_upd.date() != datetime.now().date():
                logger.info("🗑️ Persisted state is from a previous day. Ignoring.")
                return False
                
            self.entry_state = state.get('entry_state', "WAITING")
            self.best_option_low = state.get('best_option_low', 999999.0)
            self.current_option_token = state.get('current_option_token')
            self.pyramid_count = state.get('pyramid_count', 0)
            self.pullback_active = state.get('pullback_active', False)
            self.active_positions = state.get('active_positions', {})
            
            self.mega_renko.from_dict(state['mega_renko'])
            self.nifty_renko.from_dict(state['nifty_renko'])
            
            if state.get('option_renko'):
                self.option_renko = RenkoCalculator()
                self.option_renko.from_dict(state['option_renko'])
                
            logger.info(f"✅ Strategy state RESTORED. Bricks: Mega({len(self.mega_renko.bricks)}), Nifty({len(self.nifty_renko.bricks)})")
            return True
        except Exception as e:
            logger.error(f"Error loading state: {e}")
            return False

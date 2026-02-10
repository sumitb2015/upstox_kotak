"""
EMA Directional Hedge Strategy - Core Logic

This module contains all business logic for the strategy:
- EMA calculations and momentum detection
- Entry signal detection (Bull Put Spread / Bear Call Spread)
- Exit signal detection (profit target, SL, momentum reversal)
- Position tracking and P&L management
"""

from abc import ABC
import pandas as pd
from typing import Tuple, Optional, List, Dict
from datetime import datetime, timedelta
import threading


class SpreadPosition:
    """Represents a credit spread position (Bull Put or Bear Call)."""
    
    def __init__(self, spread_type: str, short_strike: int, long_strike: int,
                 short_entry_price: float, long_entry_price: float,
                 lot_size: int, short_instrument_key: str, long_instrument_key: str,
                 pnl_multiplier: float = 50.0):
        """
        Initialize spread position.
        
        Args:
            spread_type: 'BULL_PUT_SPREAD' or 'BEAR_CALL_SPREAD'
            short_strike: Strike of short leg (sold)
            long_strike: Strike of long leg (bought / hedge)
            short_entry_price: Entry price of short leg
            long_entry_price: Entry price of long leg (hedge)
            lot_size: Number of lots
            short_instrument_key: Instrument key for short leg
            long_instrument_key: Instrument key for long leg
            pnl_multiplier: Multiplier for P&L calculation (default 50 for Nifty)
        """
        self.spread_type = spread_type
        self.short_strike = short_strike
        self.long_strike = long_strike
        self.short_entry_price = short_entry_price
        self.long_entry_price = long_entry_price
        self.short_current_price = short_entry_price
        self.long_current_price = long_entry_price
        self.lot_size = lot_size
        self.short_instrument_key = short_instrument_key
        self.long_instrument_key = long_instrument_key
        self.entry_time = datetime.now()
        self.pnl_multiplier = pnl_multiplier
        
        # Net credit collected at entry
        self.net_credit = short_entry_price - long_entry_price
        
        # Max profit = net credit collected
        self.max_profit = self.net_credit * lot_size * pnl_multiplier
        
        # Maximum loss = spread width - net credit
        spread_width = abs(short_strike - long_strike)
        self.max_loss = (spread_width - self.net_credit) * lot_size * pnl_multiplier
        
        # Pyramiding state
        self.next_pyramid_milestone = 0.0  # Will scale up as profit increases
        
    def add_lots(self, added_lots: int, new_short_price: float, new_long_price: float):
        """
        Add lots to position and update weighted average prices.
        
        Args:
            added_lots: Number of lots to add
            new_short_price: Fill price of new short leg
            new_long_price: Fill price of new long leg
        """
        total_lots = self.lot_size + added_lots
        
        # Weighted average for short leg
        self.short_entry_price = (
            (self.short_entry_price * self.lot_size) + (new_short_price * added_lots)
        ) / total_lots
        
        # Weighted average for long leg
        self.long_entry_price = (
            (self.long_entry_price * self.lot_size) + (new_long_price * added_lots)
        ) / total_lots
        
        # Update total size
        self.lot_size = total_lots
        
        # Recalculate metrics
        self.net_credit = self.short_entry_price - self.long_entry_price
        self.max_profit = self.net_credit * self.lot_size * self.pnl_multiplier
        
        spread_width = abs(self.short_strike - self.long_strike)
        self.max_loss = (spread_width - self.net_credit) * self.lot_size * self.pnl_multiplier

        
    def update_prices(self, short_price: float, long_price: float):
        """Update current prices of both legs."""
        self.short_current_price = short_price
        self.long_current_price = long_price
    
    def get_current_pnl(self) -> float:
        """
        Calculate current P&L for the spread.
        
        For credit spreads (short spread):
        - Profit when both options decay (prices decrease)
        - P&L = (Entry Credit - Current Debit) * LotSize * Multiplier
        """
        entry_debit = self.short_entry_price - self.long_entry_price
        current_debit = self.short_current_price - self.long_current_price
        
        # Profit when current debit is less than entry debit
        pnl = (entry_debit - current_debit) * self.lot_size * self.pnl_multiplier
        return pnl
    
    def get_profit_pct(self) -> float:
        """Calculate profit as percentage of max profit."""
        if self.max_profit == 0:
            return 0.0
        return self.get_current_pnl() / self.max_profit
    
    def get_minutes_in_trade(self) -> int:
        """Get number of minutes in trade."""
        return int((datetime.now() - self.entry_time).total_seconds() / 60)


class EMAHedgeCore(ABC):
    """
    Core strategy logic for EMA Directional Hedge (Credit Spread) Strategy.
    
    Entry Logic:
    - Bull Put Spread: Price > EMA9 & EMA20, EMA9 > EMA20, momentum increasing
    - Bear Call Spread: Price < EMA9 & EMA20, EMA9 < EMA20, momentum decreasing
    
    Exit Logic:
    - Profit Target: 50% of max profit
    - Stop Loss: 1.5x of max profit
- Momentum Exit: EMA momentum reverses (2 consecutive candles)
    - Trailing SL: Breakeven after 30 min, lock 20% at 40% profit
    """
    
    def __init__(self, config: dict):
        """Initialize with configuration parameters."""
        self.config = config
        
        # Position tracking
        self.position: Optional[SpreadPosition] = None
        
        # EMA tracking
        self.ema9_history = []
        self.ema20_history = []
        self.price_history = []
        
        # State tracking
        self.trades_today = 0
        self.daily_pnl = 0.0
        self.trailing_sl_price = None
        
        # Synchronization
        self.lock = threading.Lock()
    
    # ========== INDICATOR CALCULATIONS ==========
    
    def calculate_ema(self, df: pd.DataFrame, period: int) -> float:
        """
        Calculate EMA using TA-Lib.
        
        Args:
            df: DataFrame with OHLCV data
            period: EMA period
            
        Returns:
            Current EMA value
        """
        import talib
        try:
            if df is None or df.empty or len(df) < period:
                return 0.0
            ema_series = talib.EMA(df['close'].values, timeperiod=period)
            return float(ema_series[-1])
        except Exception as e:
            print(f"❌ Error calculating EMA: {e}")
            return 0.0
    
    def update_indicators(self, candles_df: pd.DataFrame):
        """
        Update EMA values and history.
        
        Args:
            candles_df: DataFrame with candle data
        """
        if candles_df.empty:
            return
        
        ema9 = self.calculate_ema(candles_df, self.config['ema_fast'])
        ema20 = self.calculate_ema(candles_df, self.config['ema_slow'])
        current_price = candles_df['close'].iloc[-1]
        
        # Update history (keep last 5 candles for momentum calculation)
        self.ema9_history.append(ema9)
        self.ema20_history.append(ema20)
        self.price_history.append(current_price)
        
        # Keep only last 5 values
        if len(self.ema9_history) > 5:
            self.ema9_history.pop(0)
            self.ema20_history.pop(0)
            self.price_history.pop(0)
    
    def get_ema_difference_momentum(self, lookback: int = 2) -> str:
        """
        Determine if EMA difference is increasing or decreasing.
        
        Args:
            lookback: Number of consecutive candles to check
            
        Returns:
            'INCREASING', 'DECREASING', 'NEUTRAL', or 'INSUFFICIENT_DATA'
        """
        if len(self.ema9_history) < lookback + 1:
            return 'INSUFFICIENT_DATA'
        
        # Calculate EMA differences for last N+1 candles
        recent_diffs = []
        for i in range(-(lookback+1), 0):
            diff = self.ema9_history[i] - self.ema20_history[i]
            recent_diffs.append(diff)
        
        # Check if ALL consecutive differences are increasing
        all_increasing = all(recent_diffs[i] > recent_diffs[i-1] for i in range(1, len(recent_diffs)))
        
        # Check if ALL consecutive differences are decreasing
        all_decreasing = all(recent_diffs[i] < recent_diffs[i-1] for i in range(1, len(recent_diffs)))
        
        if all_increasing:
            return 'INCREASING'
        elif all_decreasing:
            return 'DECREASING'
        else:
            return 'NEUTRAL'
    
    # ========== ENTRY LOGIC ==========
    
    def check_entry_signal(self) -> Tuple[bool, Optional[str], str]:
        """
        Check if entry conditions are met for Bull Put or Bear Call Spread.
        
        Returns:
            (should_enter, spread_type, reason)
            spread_type: 'BULL_PUT_SPREAD' or 'BEAR_CALL_SPREAD' or None
        """
        # Don't enter if we already have a position
        if self.position is not None:
            return False, None, "Already in position"
        
        # Check max trades per day
        if self.trades_today >= self.config['max_trades_per_day']:
            return False, None, f"Max trades ({self.config['max_trades_per_day']}) reached for today"
        
        # Need at least 3 candles for momentum (current + 2 previous)
        if len(self.ema9_history) < 3:
            return False, None, "Insufficient data for momentum calculation"
        
        # Get current values
        current_price = self.price_history[-1]
        ema9 = self.ema9_history[-1]
        ema20 = self.ema20_history[-1]
        ema_diff = ema9 - ema20
        
        # Get momentum
        momentum_lookback = self.config['momentum_confirmation_candles']
        momentum = self.get_ema_difference_momentum(momentum_lookback)
        
        # --- BULL PUT SPREAD Entry ---
        # Bullish trend: price > both EMAs, EMA9 > EMA20, momentum increasing
        if self.config.get('enable_price_position_filter', True):
            price_above_emas = current_price > ema9 and current_price > ema20
        else:
            price_above_emas = True  # Skip filter if disabled
        
        if price_above_emas and ema9 > ema20:
            # Check minimum threshold
            if ema_diff >= self.config['min_ema_diff_threshold']:
                # Check momentum
                if momentum == 'INCREASING':
                    reason = (f"🟢 BULL PUT SPREAD: Price={current_price:.2f} > EMA9={ema9:.2f} > EMA20={ema20:.2f}, "
                             f"Diff={ema_diff:.2f}, Momentum=INCREASING")
                    return True, 'BULL_PUT_SPREAD', reason
        
        # --- BEAR CALL SPREAD Entry ---
        # Bearish trend: price < both EMAs, EMA9 < EMA20, momentum decreasing
        if self.config.get('enable_price_position_filter', True):
            price_below_emas = current_price < ema9 and current_price < ema20
        else:
            price_below_emas = True
        
        if price_below_emas and ema9 < ema20:
            # Check minimum threshold (negative difference)
            if ema_diff <= -self.config['min_ema_diff_threshold']:
                # Check momentum
                if momentum == 'DECREASING':
                    reason = (f"🔴 BEAR CALL SPREAD: Price={current_price:.2f} < EMA9={ema9:.2f} < EMA20={ema20:.2f}, "
                             f"Diff={ema_diff:.2f}, Momentum=DECREASING")
                    return True, 'BEAR_CALL_SPREAD', reason
        
        return False, None, f"No signal: Price={current_price:.2f}, EMA9={ema9:.2f}, EMA20={ema20:.2f}, Diff={ema_diff:.2f}, Momentum={momentum}"
    
    def check_pyramid_signal(self) -> Tuple[bool, str]:
        """
        Check if we should add to the position (Pyramid).
        
        Conditions:
        1. Pyramiding enabled in config
        2. Position exists
        3. Current lots < Max lots
        4. Profit threshold reached (e.g., every 15%)
        5. Momentum still strong
        
        Returns:
            (should_pyramid, reason)
        """
        if not self.config.get('enable_pyramiding', False):
            return False, "Pyramiding disabled"
            
        if self.position is None:
            return False, "No position"
            
        if self.position.lot_size >= self.config['max_lots']:
            return False, "Max lots reached"
            
        # Check profit milestone
        # Milestone starts at 0.15 (15%), then 0.30, etc.
        # Initialize next milestone if 0
        step_pct = self.config['pyramid_step_profit_pct']
        if self.position.next_pyramid_milestone == 0.0:
            self.position.next_pyramid_milestone = step_pct
            
        current_profit_pct = self.position.get_profit_pct()
        
        if current_profit_pct >= self.position.next_pyramid_milestone:
            # Check Momentum
            momentum = self.get_ema_difference_momentum(2)
            
            # Confirm momentum matches trade direction
            valid_momentum = False
            if self.position.spread_type == 'BULL_PUT_SPREAD' and momentum == 'INCREASING':
                valid_momentum = True
            elif self.position.spread_type == 'BEAR_CALL_SPREAD' and momentum == 'DECREASING':
                valid_momentum = True
                
            if valid_momentum:
                # Update next milestone for FUTURE checks
                # Only update AFTER successful execution? 
                # Ideally, live.py should call a method to confirm pyramid execution.
                # But here we just signal.
                return True, f"Profit {current_profit_pct*100:.1f}% >= {self.position.next_pyramid_milestone*100:.1f}% & Momentum {momentum}"
                
        return False, "Conditions not met"

    # ========== EXIT LOGIC ==========
    
    def check_exit_signal(self) -> Tuple[bool, Optional[str], str]:
        """
        Check if any exit condition is met.
        
        Exit Conditions:
        1. Profit Target: 50% of max profit
        2. Stop Loss: 1.5x of max profit (as loss)
        3. Momentum Exit: EMA momentum reverses
        4. Trailing SL: Based on time and profit milestones
        
        Returns:
            (should_exit, exit_type, reason)
        """
        if self.position is None:
            return False, None, "No position to exit"
        
        current_pnl = self.position.get_current_pnl()
        profit_pct = self.position.get_profit_pct()
        minutes_in_trade = self.position.get_minutes_in_trade()
        
        # 1. Profit Target
        profit_target_pct = self.config['profit_target_pct']
        if profit_pct >= profit_target_pct:
            reason = f"✅ PROFIT TARGET: {profit_pct*100:.1f}% >= {profit_target_pct*100:.0f}% (₹{current_pnl:.2f})"
            return True, "PROFIT_TARGET", reason
        
        # 2. Stop Loss
        stop_loss_amount = -self.position.max_profit * self.config['stop_loss_multiplier']
        if current_pnl <= stop_loss_amount:
            reason = f"❌ STOP LOSS: ₹{current_pnl:.2f} <= ₹{stop_loss_amount:.2f}"
            return True, "STOP_LOSS", reason
        
        # 3. Momentum Exit
        if self.config.get('use_momentum_exit', True):
            momentum_exit_candles = self.config['momentum_exit_candles']
            momentum = self.get_ema_difference_momentum(momentum_exit_candles)
            
            # Exit Bull Put Spread if momentum turns DECREASING
            if self.position.spread_type == 'BULL_PUT_SPREAD' and momentum == 'DECREASING':
                reason = f"📉 MOMENTUM EXIT: Bull Put Spread - Momentum turned DECREASING"
                return True, "MOMENTUM_EXIT", reason
            
            # Exit Bear Call Spread if momentum turns INCREASING
            if self.position.spread_type == 'BEAR_CALL_SPREAD' and momentum == 'INCREASING':
                reason = f"📈 MOMENTUM EXIT: Bear Call Spread - Momentum turned INCREASING"
                return True, "MOMENTUM_EXIT", reason
        
        # 4. Trailing Stop Loss
        if self.config.get('enable_trailing_sl', True):
            # Trail to breakeven after 30 minutes
            if minutes_in_trade >= self.config['trail_to_breakeven_after_minutes']:
                if current_pnl > 0 and self.trailing_sl_price is None:
                    self.trailing_sl_price = 0  # Breakeven
                    print(f"🔒 TSL: Trailing to breakeven after {minutes_in_trade} minutes")
            
            # Lock profit when 40% reached
            if profit_pct >= self.config['trail_to_lock_profit_at_pct']:
                lock_amount = self.position.max_profit * self.config['lock_profit_amount_pct']
                if self.trailing_sl_price is None or self.trailing_sl_price < lock_amount:
                    self.trailing_sl_price = lock_amount
                    print(f"🔒 TSL: Locking ₹{lock_amount:.2f} profit at {profit_pct*100:.1f}%")
            
            # Check if trailing SL hit
            if self.trailing_sl_price is not None and current_pnl < self.trailing_sl_price:
                reason = f"🛡️ TRAILING SL: ₹{current_pnl:.2f} < ₹{self.trailing_sl_price:.2f}"
                return True, "TRAILING_SL", reason
        
        return False, None, f"No exit: PnL=₹{current_pnl:.2f} ({profit_pct*100:.1f}%), Minutes={minutes_in_trade}"
    
    # ========== POSITION MANAGEMENT ==========
    
    def update_position_prices(self, short_price: float, long_price: float):
        """
        Update position prices.
        
        Args:
            short_price: Current price of short leg
            long_price: Current price of long leg (hedge)
        """
        if self.position:
            self.position.update_prices(short_price, long_price)
    
    def clear_position(self):
        """Clear position after exit."""
        if self.position:
            # Update daily P&L
            self.daily_pnl += self.position.get_current_pnl()
        
        self.position = None
        self.trailing_sl_price = None
    
    def get_position_summary(self) -> Dict:
        """Get summary of current position."""
        if not self.position:
            return {
                'in_position': False,
                'spread_type': None,
                'pnl': 0.0,
                'daily_pnl': self.daily_pnl,
                'trades_today': self.trades_today
            }
        
        return {
            'in_position': True,
            'spread_type': self.position.spread_type,
            'short_strike': self.position.short_strike,
            'long_strike': self.position.long_strike,
            'entry_credit': self.position.net_credit,
            'max_profit': self.position.max_profit,
            'max_loss': self.position.max_loss,
            'current_pnl': self.position.get_current_pnl(),
            'profit_pct': self.position.get_profit_pct() * 100,
            'minutes_in_trade': self.position.get_minutes_in_trade(),
            'trailing_sl': self.trailing_sl_price,
            'daily_pnl': self.daily_pnl,
            'trades_today': self.trades_today
        }

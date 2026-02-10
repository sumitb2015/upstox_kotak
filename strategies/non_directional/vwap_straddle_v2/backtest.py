"""
VWAP Straddle Strategy - Backtest Implementation (Shared Logic Pattern)

This is a THIN WRAPPER that:
1. Inherits core logic from VWAPStraddleCore
2. Implements data fetching for historical data
3. Implements paper trade recording
"""

import sys
import os
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from strategies.non_directional.vwap_straddle_v2.core import VWAPStraddleCore
from lib.core.backtesting.strategy_interface import BacktestableStrategy


class VWAPStraddleBacktest(VWAPStraddleCore, BacktestableStrategy):
    """
    Backtest implementation - only handles data fetching and trade recording.
    All business logic is inherited from VWAPStraddleCore.
    """
    
    def __init__(self, config: Dict[str, Any]):
        # Initialize both parent classes
        VWAPStraddleCore.__init__(self, config)
        BacktestableStrategy.__init__(self, config)
        
        # Backtest-specific config
        self.candle_interval = config.get('candle_interval_minutes', 5)
        self.entry_time = datetime.strptime(config.get('entry_time', "09:20"), "%H:%M").time()
        self.exit_time = datetime.strptime(config.get('exit_time', "15:15"), "%H:%M").time()
        self.max_trades_per_day = config.get('max_trades_per_day', 50)
        
        # State
        self.atm_strike = None
        self.ce_key = None
        self.pe_key = None
        self.data_manager = None
    
    # ========== IMPLEMENTATION-SPECIFIC METHODS ==========
    
    def fetch_data(self, instrument_key: str, date: str):
        """Fetch historical data from backtest engine."""
        return self.data_manager.fetch_data(
            instrument_key, date, date, 'minute', self.candle_interval
        )
    
    def execute_trade(self, action: str, entry_price: float = None, exit_price: float = None, date: str = None):
        """Record paper trade in positions list."""
        pnl = self.calculate_pnl(entry_price, exit_price)  # ← Uses shared logic!
        
        self.positions.append({
            'date': date,
            'symbol': f"{self.atm_strike} STR",
            'type': 'SELL',
            'qty': self.lot_size,
            'entry': entry_price,
            'exit': exit_price,
            'pnl': pnl,
            'reason_in': 'Signal',
            'reason_out': action
        })
    
    # ========== BACKTESTABLE STRATEGY INTERFACE ==========
    
    def initialize(self, data_manager, date: str) -> bool:
        """Initialize strategy for the day."""
        self.data_manager = data_manager
        
        # 1. Fetch index data to determine ATM
        index_key = "NSE_INDEX|Nifty 50"
        index_df = self.fetch_data(index_key, date)
        
        if index_df.empty:
            print(f"  ❌ No Index Data for {date}")
            return False
        
        # 2. Find ATM at entry time
        start_candle = index_df[index_df.index.time >= self.entry_time]
        if start_candle.empty:
            return False
        
        atm_spot = start_candle.iloc[0]['close']
        self.atm_strike = round(atm_spot / 50) * 50
        print(f"  🎯 09:20 Spot: {atm_spot:.2f} | ATM: {self.atm_strike}")
        
        # 3. Resolve instrument keys
        self.ce_key = data_manager.get_instrument_key_for_date("NIFTY", self.atm_strike, "CE", date)
        self.pe_key = data_manager.get_instrument_key_for_date("NIFTY", self.atm_strike, "PE", date)
        
        if not self.ce_key or not self.pe_key:
            print(f"  ⚠️  Could not resolve keys")
            return False
        
        # 4. Calculate previous day low using SHARED logic
        prev_date = self._get_previous_trading_day(date)
        self.prev_day_cp_low = self._calculate_prev_day_low(prev_date, date)
        
        if self.prev_day_cp_low == float('inf'):
            print(f"  ⚠️  No valid prev day data")
            return False
        
        print(f"  📉 Prev Low: {self.prev_day_cp_low:.2f}")
        
        # 5. Run day logic
        self._run_day_logic(date)
        
        return True
    
    def _get_previous_trading_day(self, date_str: str) -> str:
        """Get previous trading day, skipping weekends."""
        date = datetime.strptime(date_str, "%Y-%m-%d")
        prev = date - timedelta(days=1)
        
        while prev.weekday() >= 5:
            prev -= timedelta(days=1)
        
        return prev.strftime("%Y-%m-%d")
    
    def _calculate_prev_day_low(self, prev_date: str, current_date: str) -> float:
        """Calculate previous day low using SHARED calculation logic."""
        ce_prev = self.fetch_data(self.ce_key, prev_date)
        pe_prev = self.fetch_data(self.pe_key, prev_date)
        
        if ce_prev.empty or pe_prev.empty:
            return float('inf')
        
        df = ce_prev.join(pe_prev, lsuffix='_ce', rsuffix='_pe', how='inner')
        prev_day_mask = df.index.date < datetime.strptime(current_date, "%Y-%m-%d").date()
        
        if not prev_day_mask.any():
            return float('inf')
        
        # Use SHARED calculation method
        return self.calculate_prev_day_low(df.loc[prev_day_mask])
    
    def _run_day_logic(self, date: str):
        """Execute backtest logic for the day - uses SHARED validation logic."""
        # Fetch current day data
        ce_df = self.fetch_data(self.ce_key, date)
        pe_df = self.fetch_data(self.pe_key, date)
        
        if ce_df.empty or pe_df.empty:
            return
        
        # Join dataframes
        df = ce_df.join(pe_df, lsuffix='_ce', rsuffix='_pe', how='inner')
        df = df[df.index.date == datetime.strptime(date, "%Y-%m-%d").date()]
        
        if df.empty:
            return
        
        # Calculate VWAP using SHARED logic
        df['vwap'] = self.calculate_vwap(df)
        
        # State tracking
        in_trade = False
        entry_price = 0.0
        trades_today = 0
        
        # Iterate through candles
        for ts, row in df.iterrows():
            if ts.time() < self.entry_time:
                continue
            
            cp = row['close_ce'] + row['close_pe']
            vwap = row['vwap']
            
            if not in_trade:
                # Use SHARED entry validation logic
                should_enter, reason = self.validate_entry_conditions(
                    cp, vwap, self.prev_day_cp_low, row['close_ce'], row['close_pe']
                )
                
                if should_enter:
                    entry_price = cp
                    in_trade = True
                    self.record_entry(entry_price)
            else:
                # Check time exit first
                if ts.time() >= self.exit_time:
                    exit_reason = "Time Exit"
                else:
                    # Use SHARED exit condition logic
                    exit_reason, details = self.check_exit_conditions(
                        cp, vwap, entry_price, row['close_ce'], row['close_pe']
                    )
                
                if exit_reason:
                    self.execute_trade(exit_reason, entry_price, cp, date)
                    in_trade = False
                    trades_today += 1
                    
                    if trades_today >= self.max_trades_per_day:
                        break
        
        print(f"  ✅ {trades_today} trade(s) executed")
    
    def get_completed_trades(self):
        """Return completed trades for this day (required by backtest runner)."""
        return self.positions
    
    # Unused interface methods
    def on_candle(self, timestamp: pd.Timestamp, candle_data: Dict[str, pd.Series]) -> None:
        pass
    
    def should_enter(self) -> bool:
        return False
    
    def should_exit(self) -> str:
        return None
    
    def execute_entry(self):
        pass
    
    def execute_exit(self, reason: str):
        pass

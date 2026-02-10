"""
Backtest Implementation of Dual-Renko Strategy.
Inherits from DualRenkoCore and implements BacktestableStrategy.
"""

import sys
import os
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

import pandas as pd
import numpy as np

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from strategies.dual_renko_dip.core import DualRenkoCore, RenkoCalculator
from lib.core.backtesting.strategy_interface import BacktestableStrategy

# Logger
logger = logging.getLogger("DualRenkoBacktest")

class DualRenkoBacktest(DualRenkoCore, BacktestableStrategy):
    def __init__(self, config: Dict[str, Any]):
        DualRenkoCore.__init__(self, config)
        BacktestableStrategy.__init__(self, config)
        
        self.candle_interval = config.get('candle_interval_minutes', 1)
        self.entry_time = datetime.strptime(config.get('entry_time', "09:20"), "%H:%M").time()
        self.exit_time = datetime.strptime(config.get('exit_time', "15:15"), "%H:%M").time()
        self.trading_lots = config.get('trading_lots', 1)
        
        self.data_manager = None
        self.atm_strike = None
        self.index_key = "NSE_INDEX|Nifty 50"
        
        # State
        self.price_history = []
        self.option_data = {}

    # === BacktestableStrategy Interface ===

    def initialize(self, data_manager, date: str) -> bool:
        """Initialize and run backtest for the day (Runner calls this)."""
        self.data_manager = data_manager
        self.reset()
        
        index_df = data_manager.fetch_data(self.index_key, date, date, 'minute', self.candle_interval)
        if index_df.empty:
            return False
            
        entry_spot = index_df[index_df.index.time >= self.entry_time]
        if entry_spot.empty:
            return False
        
        spot_price = entry_spot.iloc[0]['close']
        self.atm_strike = round(spot_price / 50) * 50
        
        # Seed RSI
        self.price_history = index_df['close'].tolist()[:30]
        self._calculate_rsi()
        
        # Initialize Renko
        self.nifty_renko.initialize(index_df.iloc[0]['close'])
        self.mega_renko.initialize(index_df.iloc[0]['close'])
        
        # Run internal loop
        self._run_day_logic(date, index_df)
        return True

    def on_candle(self, timestamp: pd.Timestamp, candle_data: Dict[str, pd.Series]) -> None:
        """Required by interface but handled internally by _run_day_logic for this strategy."""
        pass

    def should_enter(self) -> bool:
        return False

    def should_exit(self) -> Optional[str]:
        return None

    def get_completed_trades(self) -> List[Dict]:
        """Required by runner."""
        return self.positions

    # === DualRenkoCore Implementation (Core calls these) ===

    def execute_entry(self, option_type: str, timestamp: datetime, is_pyramid: bool = False):
        date_str = timestamp.strftime("%Y-%m-%d")
        strike = self.atm_strike - 150 if option_type == "PE" else self.atm_strike + 150
        
        opt_key = self.data_manager.get_instrument_key_for_date("NIFTY", strike, option_type, date_str)
        if not opt_key: return

        opt_candle = self._get_option_candle(opt_key, timestamp, date_str)
        if opt_candle is None: return
        
        entry_price = opt_candle['close']
        qty = 50 * self.trading_lots
        
        if not is_pyramid:
            self.active_positions[option_type] = {
                'key': opt_key,
                'qty': qty,
                'entry_price': entry_price,
                'timestamp': timestamp,
                'type': option_type
            }
            self.current_option_token = opt_key
            
            brick_size = self.calculate_option_brick_size(entry_price)
            self.option_renko = RenkoCalculator(brick_size=brick_size)
            self.option_renko.initialize(entry_price)
            self.best_option_low = entry_price
        else:
            self.active_positions[option_type]['qty'] += qty

    def execute_exit(self, option_type: str, reason: str, timestamp: datetime = None):
        """Modified to accept timestamp for PnL calculation."""
        if option_type not in self.active_positions: return
            
        pos = self.active_positions.pop(option_type)
        
        # Get exit price from current timestamp
        exit_price = 0.0
        if timestamp and pos['key'] in self.option_data:
            df = self.option_data[pos['key']]
            if timestamp in df.index:
                exit_price = df.loc[timestamp]['close']
        
        # If timestamp wasn't provided (Mega Reversal), it might need fetching at that moment
        if exit_price == 0.0 and timestamp:
             opt_candle = self._get_option_candle(pos['key'], timestamp, timestamp.strftime("%Y-%m-%d"))
             if opt_candle is not None: exit_price = opt_candle['close']

        pnl = (pos['entry_price'] - exit_price) * pos['qty']
        
        self.positions.append({
            'date': timestamp.strftime("%Y-%m-%d") if timestamp else "",
            'symbol': f"NIFTY {self.atm_strike} {option_type}",
            'type': 'SELL',
            'qty': pos['qty'],
            'entry': float(pos['entry_price']),
            'exit': float(exit_price),
            'pnl': float(pnl),
            'reason_in': 'Signal',
            'reason_out': reason,
            'timestamp': str(timestamp)
        })
        
        self.current_option_token = None
        self.option_renko = None

    # === Internal Logic ===

    def _calculate_rsi(self):
        if len(self.price_history) < self.rsi_period + 1:
            self.rsi = 50.0
            return
        try:
            prices = pd.Series(self.price_history)
            delta = prices.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
            rs = gain / loss
            self.rsi = 100 - (100 / (1 + rs.iloc[-1]))
            if np.isnan(self.rsi): self.rsi = 50.0
        except: self.rsi = 50.0

    def _run_day_logic(self, date: str, index_df: pd.DataFrame):
        try:
            for ts, row in index_df.iterrows():
                # RSI Update
                self.price_history.append(row['close'])
                self._calculate_rsi()

                # Market Hours
                if ts.time() < self.entry_time or ts.time() >= self.exit_time:
                    if self.is_position_open() and ts.time() >= self.exit_time:
                         # Exit all
                         for opt_type in list(self.active_positions.keys()):
                             self.execute_exit(opt_type, "Time Exit", ts)
                    continue

                # 1. Update Nifty
                mbricks = self.mega_renko.update_from_candle(row['high'], row['low'], ts)
                if mbricks > 0: self.on_mega_brick(ts)
                
                sbricks = self.nifty_renko.update_from_candle(row['high'], row['low'], ts)
                if sbricks > 0: self.on_signal_brick(ts)

                # 2. Update Options
                if self.current_option_token and self.option_renko:
                    opt_row = self._get_option_candle(self.current_option_token, ts, date)
                    if opt_row is not None:
                        obricks = self.option_renko.update_from_candle(opt_row['high'], opt_row['low'], ts)
                        if obricks > 0: self.on_option_brick(ts)
        except Exception as e:
            print(f"❌ Error in loop: {e}")
            import traceback
            traceback.print_exc()

    def _get_option_candle(self, key, ts, date):
        if key not in self.option_data:
            df = self.data_manager.fetch_data(key, date, date, 'minute', 1)
            self.option_data[key] = df
        df = self.option_data[key]
        return df.loc[ts] if ts in df.index else None

    def reset(self):
        DualRenkoCore.__init__(self, self.config)
        self.positions = []
        self.active_positions = {}
        self.current_option_token = None
        self.option_renko = None
        self.entry_state = "WAITING"
        self.price_history = []
        self.option_data = {}

    def is_position_open(self):
        return len(self.active_positions) > 0

"""
Backtest Testing Strategy - Backtest Implementation
"""

import sys
import os
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any

from strategies.backtest_testing.core import BacktestTestingCore
from lib.core.backtesting.strategy_interface import BacktestableStrategy

class BacktestTestingBacktest(BacktestTestingCore, BacktestableStrategy):
    """
    Backtest wrapper for Backtest Testing strategy.
    """
    
    def __init__(self, config: Dict[str, Any]):
        BacktestTestingCore.__init__(self, config)
        BacktestableStrategy.__init__(self, config)
        
        self.candle_interval = config.get('candle_interval_minutes', 5)
        # Entry 9:30 AM
        self.entry_time = datetime.strptime("09:30", "%H:%M").time()
        # Exit 15:15 PM
        self.exit_time = datetime.strptime("15:15", "%H:%M").time()
        
        self.data_manager = None
        self.atm_strike = None
        self.ce_key = None
        self.pe_key = None
        
    def initialize(self, data_manager, date: str) -> bool:
        self.data_manager = data_manager
        
        # 1. Fetch Index Data for ATM calculation
        index_key = "NSE_INDEX|Nifty 50"
        index_df = self.data_manager.fetch_data(index_key, date, date, 'minute', 5)
        
        if index_df.empty:
            return False
            
        # 2. Find ATM at 9:30 AM
        entry_candle = index_df[index_df.index.time >= self.entry_time]
        if entry_candle.empty:
            return False
            
        atm_spot = entry_candle.iloc[0]['open']
        self.atm_strike = round(atm_spot / 50) * 50
        print(f"  🎯 09:30 Spot: {atm_spot:.2f} | ATM: {self.atm_strike}")
        
        # 3. Resolve Keys
        self.ce_key = data_manager.get_instrument_key_for_date("NIFTY", self.atm_strike, "CE", date)
        self.pe_key = data_manager.get_instrument_key_for_date("NIFTY", self.atm_strike, "PE", date)
        
        if not self.ce_key or not self.pe_key:
            print(f"  ⚠️ Could not resolve keys for ATM {self.atm_strike}")
            return False
            
        # 4. Run Day Logic
        self._run_day_logic(date)
        return True
        
    def _run_day_logic(self, date: str):
        # Fetch data
        ce_df = self.data_manager.fetch_data(self.ce_key, date, date, 'minute', self.candle_interval)
        pe_df = self.data_manager.fetch_data(self.pe_key, date, date, 'minute', self.candle_interval)
        
        if ce_df.empty or pe_df.empty:
            return
            
        # Join
        df = ce_df.join(pe_df, lsuffix='_ce', rsuffix='_pe', how='inner')
        
        entered = False
        
        for ts, row in df.iterrows():
            curr_time = ts.time()
            
            # Entry Condition
            if not entered and curr_time >= self.entry_time:
                ce_price = row['open_ce'] # Enter at Open of the candle
                pe_price = row['open_pe']
                
                self.set_entry_prices(ce_price, pe_price)
                entered = True
                
            if entered:
                if not (self.ce_active or self.pe_active):
                    break # Both legs closed
                
                # Check Time Exit
                if curr_time >= self.exit_time:
                    if self.ce_active:
                        exit_p = row['open_ce']
                        pnl = (self.ce_entry_price - exit_p) * self.lot_size
                        self.positions.append({
                            'date': date,
                            'symbol': f"{self.atm_strike} CE",
                            'type': 'SELL',
                            'qty': self.lot_size,
                            'entry': self.ce_entry_price,
                            'exit': exit_p,
                            'pnl': pnl,
                            'reason_in': 'Time Entry',
                            'reason_out': 'Time Exit'
                        })
                        self.ce_active = False
                        
                    if self.pe_active:
                        exit_p = row['open_pe']
                        pnl = (self.pe_entry_price - exit_p) * self.lot_size
                        self.positions.append({
                            'date': date,
                            'symbol': f"{self.atm_strike} PE",
                            'type': 'SELL',
                            'qty': self.lot_size,
                            'entry': self.pe_entry_price,
                            'exit': exit_p,
                            'pnl': pnl,
                            'reason_in': 'Time Entry',
                            'reason_out': 'Time Exit'
                        })
                        self.pe_active = False
                    break
                
                # Check Exits (SL)
                # For short positions, we check if HIGH reached the SL price for realistic backtest
                ce_high = row['high_ce']
                pe_high = row['high_pe']
                
                exits = self.check_leg_exit(ce_high, pe_high)
                
                for exit_info in exits:
                    self.positions.append({
                        'date': date,
                        'symbol': f"{self.atm_strike} {exit_info['leg']}",
                        'type': 'SELL',
                        'qty': self.lot_size,
                        'entry': self.ce_entry_price if exit_info['leg'] == 'CE' else self.pe_entry_price,
                        'exit': exit_info['price'],
                        'pnl': exit_info['pnl'],
                        'reason_in': 'Time Entry',
                        'reason_out': exit_info['reason']
                    })

        print(f"  ✅ Trades recorded for {date}: {len(self.positions)}")

    def get_completed_trades(self):
        return self.positions

    # Unused interface methods
    def on_candle(self, timestamp, candle_data): pass
    def should_enter(self): return False
    def should_exit(self): return None
    def execute_entry(self): pass
    def execute_exit(self, reason): pass

"""
Backtest Testing Strategy - Core Logic

Strategy Rules:
1. Enter ATM Straddle (Sell CE + Sell PE) at 09:30 AM
2. Stop Loss: 20% per leg
3. Time Exit: 15:15 PM
"""

from abc import ABC, abstractmethod
import pandas as pd
from typing import Tuple, Optional, Dict

class BacktestTestingCore(ABC):
    """
    Core strategy logic for Backtest Testing strategy.
    """
    
    def __init__(self, config: dict):
        self.lot_size = config.get('lot_size', 50)  # Default for NIFTY
        self.sl_pct = config.get('sl_pct', 0.20)
        
        # State
        self.ce_entry_price = 0.0
        self.pe_entry_price = 0.0
        self.ce_sl_price = 0.0
        self.pe_sl_price = 0.0
        self.ce_active = False
        self.pe_active = False
        self.total_pnl = 0.0
        
    def set_entry_prices(self, ce_price: float, pe_price: float):
        """Record entry prices and calculate SLs."""
        self.ce_entry_price = ce_price
        self.pe_entry_price = pe_price
        
        # SL is 20% above entry price (Short position)
        self.ce_sl_price = ce_price * (1 + self.sl_pct)
        self.pe_sl_price = pe_price * (1 + self.sl_pct)
        
        self.ce_active = True
        self.pe_active = True
        self.total_pnl = 0.0 
        
    def check_leg_exit(self, ce_curr_price: float, pe_curr_price: float) -> list:
        """
        Check for SL hits on individual legs.
        Returns list of exits: [{'leg': 'CE', 'reason': 'SL', 'price': price}, ...]
        """
        exits = []
        
        if self.ce_active and ce_curr_price >= self.ce_sl_price:
            exits.append({
                'leg': 'CE',
                'reason': 'SL Hit',
                'price': self.ce_sl_price, # Assuming we exit at SL price (slippage ignored for now)
                'pnl': (self.ce_entry_price - self.ce_sl_price) * self.lot_size
            })
            self.ce_active = False
            self.total_pnl += (self.ce_entry_price - self.ce_sl_price) * self.lot_size

        if self.pe_active and pe_curr_price >= self.pe_sl_price:
            exits.append({
                'leg': 'PE',
                'reason': 'SL Hit',
                'price': self.pe_sl_price,
                'pnl': (self.pe_entry_price - self.pe_sl_price) * self.lot_size
            })
            self.pe_active = False
            self.total_pnl += (self.pe_entry_price - self.pe_sl_price) * self.lot_size
            
        return exits

    def calculate_open_pnl(self, ce_curr_price: float, pe_curr_price: float) -> float:
        """Calculate unrealized PnL for active legs."""
        pnl = 0.0
        if self.ce_active:
            pnl += (self.ce_entry_price - ce_curr_price) * self.lot_size
        if self.pe_active:
            pnl += (self.pe_entry_price - pe_curr_price) * self.lot_size
        return pnl

    # Abstract methods required by shared pattern if we were strictly following it, 
    # but for simplicity we'll just define the specific interface needed.

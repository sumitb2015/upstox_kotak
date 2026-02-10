"""
ATM Short Straddle Strategy - Core Logic

Pure logic without API calls for testability.
"""

from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Position:
    """Represents a straddle position"""
    strike: int
    ce_lots: int
    pe_lots: int
    ce_entry_price: float
    pe_entry_price: float
    ce_current_price: float = 0.0
    pe_current_price: float = 0.0
    ce_instrument_key: str = ""  # Upstox Key
    pe_instrument_key: str = ""  # Upstox Key
    ce_trading_symbol: str = ""  # Kotak Trading Symbol
    pe_trading_symbol: str = ""  # Kotak Trading Symbol
    entry_time: str = ""
    
    def update_prices(self, ce_price: float, pe_price: float):
        """Update current prices"""
        self.ce_current_price = ce_price
        self.pe_current_price = pe_price
    
    def calculate_pnl(self, lot_size: int = 75) -> float:
        """
        Calculate total P&L for the position.
        For short positions: P&L = (entry - current) * lots * lot_size
        
        Args:
            lot_size: Lot size for the instrument (default 75 for NIFTY)
        """
        # CE P&L (short position)
        ce_pnl = (self.ce_entry_price - self.ce_current_price) * self.ce_lots * lot_size
        
        # PE P&L (short position)
        pe_pnl = (self.pe_entry_price - self.pe_current_price) * self.pe_lots * lot_size
        
        return ce_pnl + pe_pnl


class StraddleCore:
    """Core strategy logic"""
    
    @staticmethod
    def calculate_ratio(ce_price: float, pe_price: float) -> float:
        """
        Calculate CE/PE ratio as min/max.
        
        Returns:
            float: Ratio between 0 and 1
        """
        if ce_price <= 0 or pe_price <= 0:
            return 1.0  # Invalid prices, return neutral ratio
        
        min_price = min(ce_price, pe_price)
        max_price = max(ce_price, pe_price)
        
        return min_price / max_price
    
    @staticmethod
    def check_adjustment_needed(ratio: float, threshold: float) -> bool:
        """
        Check if position adjustment is needed.
        
        Args:
            ratio: Current CE/PE ratio
            threshold: Threshold below which adjustment is triggered
            
        Returns:
            bool: True if adjustment needed
        """
        return ratio < threshold
    
    @staticmethod
    def determine_profitable_side(ce_price: float, pe_price: float,
                                  ce_entry: float, pe_entry: float) -> str:
        """
        Determine which side is more profitable.
        
        Returns:
            str: "CE" or "PE"
        """
        ce_profit = ce_entry - ce_price
        pe_profit = pe_entry - pe_price
        
        return "CE" if ce_profit > pe_profit else "PE"
    
    @staticmethod
    def check_exit_conditions(pnl: float, profit_target: float, 
                              stop_loss: float) -> Tuple[bool, str]:
        """
        Check if exit conditions are met.
        
        Returns:
            Tuple[bool, str]: (should_exit, reason)
        """
        if pnl >= profit_target:
            return True, f"Profit target reached: ₹{pnl:,.2f}"
        
        if pnl <= stop_loss:
            return True, f"Stop loss hit: ₹{pnl:,.2f}"
        
        return False, ""
    
    @staticmethod
    def is_new_atm(current_strike: int, new_strike: int) -> bool:
        """
        Check if ATM has changed.
        
        Args:
            current_strike: Current position strike
            new_strike: New ATM strike from market
            
        Returns:
            bool: True if ATM has changed
        """
        return current_strike != new_strike
    
    @staticmethod
    def should_switch_to_new_atm(current_strike: int, spot_price: float,
                                 new_atm_strike: int) -> bool:
        """
        Determine if we should switch to new ATM.
        
        Logic: Switch if spot has moved significantly from current strike
        and new ATM is different.
        """
        if current_strike == new_atm_strike:
            return False
        
        # Check if spot has moved at least 50 points from current strike
        distance = abs(spot_price - current_strike)
        
        return distance >= 50

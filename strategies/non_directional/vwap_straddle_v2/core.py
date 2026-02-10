"""
VWAP Straddle Strategy - Core Logic (Shared between Live and Backtest)

This demonstrates the shared strategy pattern where all business logic
lives in one place and is reused by both live and backtest implementations.
"""

from abc import ABC, abstractmethod
import pandas as pd
from typing import Tuple, Optional


class VWAPStraddleCore(ABC):
    """
    Core strategy logic shared between live trading and backtesting.
    
    Contains all entry/exit rules, calculations, and validations.
    Subclasses only need to implement data fetching and trade execution.
    """
    
    def __init__(self, config: dict):
        """Initialize with configuration parameters."""
        self.lot_size = config.get('lot_size', 65)
        self.stop_loss_points = config.get('stop_loss_points', 30.0)
        self.max_straddle_width_pct = config.get('max_straddle_width_pct', 0.20)
        self.max_skew_exit_pct = config.get('max_skew_exit_pct', 0.60)
        self.trailing_sl_points = config.get('trailing_sl_points', 20.0)
        
        # State variables
        self.entry_price_combined = 0.0
        self.lowest_cp_since_entry = float('inf')
        self.prev_day_cp_low = float('inf')
    
    def record_entry(self, cp: float):
        """Record entry price and initialize trailing tracking."""
        self.entry_price_combined = cp
        self.lowest_cp_since_entry = cp
        
    # ========== SHARED CALCULATIONS ==========
    
    def calculate_vwap(self, df: pd.DataFrame) -> pd.Series:
        """
        Calculate VWAP from combined CE/PE data.
        
        Args:
            df: DataFrame with close_ce, close_pe, volume_ce, volume_pe columns
            
        Returns:
            Series with VWAP values
        """
        df['cp_close'] = df['close_ce'] + df['close_pe']
        df['total_vol'] = df['volume_ce'] + df['volume_pe']
        df['pv'] = df['cp_close'] * df['total_vol']
        
        # Cumulative VWAP calculation
        return df['pv'].cumsum() / df['total_vol'].cumsum()
    
    def calculate_prev_day_low(self, df: pd.DataFrame) -> float:
        """
        Calculate previous day combined premium low.
        
        Args:
            df: DataFrame with close_ce and close_pe columns
            
        Returns:
            Minimum combined premium from previous day
        """
        df['cp_close'] = df['close_ce'] + df['close_pe']
        return df['cp_close'].min()
    
    # ========== SHARED VALIDATION LOGIC ==========
    
    def validate_entry_conditions(
        self, 
        cp: float, 
        vwap: float, 
        prev_low: float, 
        ce_price: float, 
        pe_price: float
    ) -> Tuple[bool, str]:
        """
        Check if all entry conditions are met.
        
        Entry Rules:
        1. CP < Previous Day Low
        2. CP < VWAP
        3. Valid prices (> 0)
        4. Skew within acceptable range
        
        Args:
            cp: Combined premium (CE + PE)
            vwap: Current VWAP value
            prev_low: Previous day combined low
            ce_price: Call option price
            pe_price: Put option price
            
        Returns:
            (should_enter, reason_message)
        """
        # Primary condition: Below both prev low and VWAP
        if not (cp < prev_low and cp < vwap):
            return False, f"CP ({cp:.2f}) not below PrevLow ({prev_low:.2f}) and VWAP ({vwap:.2f})"
        
        # Validate combined premium
        if cp <= 0:
            return False, "Invalid combined premium (≤0)"
        
        # Validate individual leg prices
        if ce_price <= 0 or pe_price <= 0:
            return False, f"Invalid leg prices: CE={ce_price:.2f}, PE={pe_price:.2f}"
        
        # Check skew/width at entry
        width_diff = abs(ce_price - pe_price)
        width_pct = width_diff / cp
        
        if width_pct > self.max_straddle_width_pct:
            return False, f"Skew too high: {width_pct*100:.1f}% > {self.max_straddle_width_pct*100:.0f}%"
        
        return True, f"Entry valid | Skew: {width_pct*100:.1f}%"

    def check_exit_conditions(
        self,
        cp: float,
        vwap: float,
        entry_price: float,
        ce_price: float,
        pe_price: float
    ) -> Tuple[Optional[str], str]:
        """
        Check if any exit condition is met.
        
        Exit Rules (in priority order):
        1. Stop Loss: CP > Entry + SL Points
        2. Trailing SL: CP > Lowest CP + TRL Points
        3. VWAP Cross: CP > VWAP
        4. Runtime Skew: Skew > Max Skew Exit %
        """
        # Update Trailing Low (Short Straddle: Lower CP is better)
        if cp < self.lowest_cp_since_entry:
            self.lowest_cp_since_entry = cp
            
        # 1. Stop Loss Check
        stop_loss = entry_price + self.stop_loss_points
        if cp > stop_loss:
            return "SL Hit", f"CP {cp:.2f} > SL {stop_loss:.2f}"
            
        # 2. Trailing Stop Loss
        trl_price = self.lowest_cp_since_entry + self.trailing_sl_points
        if cp > trl_price:
            return "Trailing SL Hit", f"CP {cp:.2f} > TRL {trl_price:.2f} (Low: {self.lowest_cp_since_entry:.2f})"
        
        # 3. VWAP Crossover
        if cp > vwap:
            return "VWAP Cross", f"CP {cp:.2f} > VWAP {vwap:.2f}"
        
        # 4. Runtime Skew Exit
        if ce_price > 0 and pe_price > 0 and cp > 0:
            skew_diff = abs(ce_price - pe_price)
            skew_pct = skew_diff / cp
            
            if skew_pct > self.max_skew_exit_pct:
                return f"Skew Exit ({skew_pct:.2f})", f"Skew {skew_pct*100:.1f}% > {self.max_skew_exit_pct*100:.0f}%"
        
        return None, "No exit condition met"
    
    def calculate_pnl(self, entry_price: float, exit_price: float) -> float:
        """
        Calculate PnL for short straddle position.
        
        For short straddle: Profit when price decreases
        PnL = (Entry - Exit) * Lot Size
        
        Args:
            entry_price: Entry combined premium
            exit_price: Exit combined premium
            
        Returns:
            PnL in rupees
        """
        return (entry_price - exit_price) * self.lot_size
    
    # ========== ABSTRACT METHODS (Implementation-specific) ==========
    
    @abstractmethod
    def fetch_data(self, *args, **kwargs):
        """
        Fetch market data.
        
        Implementation varies:
        - Live: Fetch real-time candles from API
        - Backtest: Fetch historical data from cache/API
        """
        pass
    
    @abstractmethod
    def execute_trade(self, *args, **kwargs):
        """
        Execute trade action.
        
        Implementation varies:
        - Live: Place real orders via broker
        - Backtest: Record paper trade in positions list
        """
        pass

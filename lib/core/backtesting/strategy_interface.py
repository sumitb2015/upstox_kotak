"""
Strategy Interface for Backtesting

All backtestable strategies must implement this interface.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from datetime import datetime
import pandas as pd


class BacktestableStrategy(ABC):
    """
    Abstract base class for backtestable strategies.
    
    All strategies must implement these methods to work with the unified backtest runner.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize strategy with configuration.
        
        Args:
            config: Dictionary of strategy parameters (from YAML or defaults)
        """
        self.config = config
        self.positions = []
        self.state = {}  # Strategy-specific state
    
    @abstractmethod
    def initialize(self, data_manager, date: str) -> bool:
        """
        Called once per day before market open.
        
        Args:
            data_manager: BacktestDataManager instance for fetching data
            date: Current date in YYYY-MM-DD format
        
        Returns:
            True if initialization successful, False to skip this day
        """
        pass
    
    @abstractmethod
    def on_candle(self, timestamp: pd.Timestamp, candle_data: Dict[str, pd.Series]) -> None:
        """
        Called for each candle during the trading day.
        
        Args:
            timestamp: Candle timestamp
            candle_data: Dictionary with keys like 'index', 'ce', 'pe' containing Series with OHLCV
        """
        pass
    
    @abstractmethod
    def should_enter(self) -> bool:
        """
        Check if entry conditions are met.
        
        Returns:
            True if strategy should enter position
        """
        pass
    
    @abstractmethod
    def should_exit(self) -> Optional[str]:
        """
        Check if exit conditions are met.
        
        Returns:
            Exit reason string if should exit, None otherwise
        """
        pass
    
    @abstractmethod
    def execute_entry(self) -> List[Dict]:
        """
        Execute entry and return trade details.
        
        Returns:
            List of trade dictionaries with keys: symbol, type, qty, entry_price
        """
        pass
    
    @abstractmethod
    def execute_exit(self, reason: str) -> List[Dict]:
        """
        Execute exit and return trade details.
        
        Args:
            reason: Exit reason string
        
        Returns:
            List of completed trade dictionaries with keys:
            date, symbol, type, qty, entry, exit, pnl, reason_in, reason_out
        """
        pass
    
    def get_positions(self) -> List[Dict]:
        """
        Get current open positions.
        
        Returns:
            List of position dictionaries
        """
        return self.positions
    
    def is_position_open(self) -> bool:
        """
        Check if strategy has open positions.
        
        Returns:
            True if positions are open
        """
        return len(self.positions) > 0
    
    def reset(self):
        """Reset strategy state for new day"""
        self.positions = []
        self.state = {}

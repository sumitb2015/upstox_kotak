"""
Unified Backtest Runner

Orchestrates backtesting for any strategy implementing BacktestableStrategy interface.
"""

import pandas as pd
from datetime import datetime, timedelta, time
from typing import Dict, List, Any, Type
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from lib.core.backtesting.strategy_interface import BacktestableStrategy
from lib.core.backtesting.engine import BacktestDataManager


class UnifiedBacktestRunner:
    """
    Generic backtest runner that works with any strategy implementing BacktestableStrategy.
    """
    
    def __init__(
        self,
        strategy_class: Type[BacktestableStrategy],
        from_date: str,
        to_date: str,
        access_token: str,
        config: Dict[str, Any] = None,
        master_path: str = None
    ):
        """
        Initialize backtest runner.
        
        Args:
            strategy_class: Class implementing BacktestableStrategy
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
            access_token: API access token
            config: Strategy configuration dictionary
            master_path: Optional path to master contracts CSV
        """
        self.strategy_class = strategy_class
        self.from_date = from_date
        self.to_date = to_date
        self.access_token = access_token
        self.config = config or {}
        self.master_path = master_path
        
        self.data_manager = BacktestDataManager(access_token, master_path)
        self.trades = []
        self.daily_stats = []
        
    def get_previous_trading_day(self, date_str: str) -> str:
        """
        Get previous trading day, skipping weekends.
        
        Fixes audit issue #2: Previous day calculation doesn't skip weekends
        """
        date = datetime.strptime(date_str, "%Y-%m-%d")
        prev = date - timedelta(days=1)
        
        # Skip weekends
        while prev.weekday() >= 5:  # Saturday=5, Sunday=6
            prev -= timedelta(days=1)
        
        return prev.strftime("%Y-%m-%d")
    
    def run(self):
        """
        Execute backtest across date range.
        """
        print("=" * 70)
        print(f"🚀 UNIFIED BACKTEST: {self.strategy_class.__name__}")
        print("=" * 70)
        print(f"Period: {self.from_date} to {self.to_date}")
        print(f"Config: {self.config}")
        print("=" * 70)
        
        current = datetime.strptime(self.from_date, "%Y-%m-%d")
        end = datetime.strptime(self.to_date, "%Y-%m-%d")
        
        days_tested = 0
        days_skipped = 0
        
        while current <= end:
            # Skip weekends
            if current.weekday() >= 5:
                current += timedelta(days=1)
                continue
            
            date_str = current.strftime("%Y-%m-%d")
            print(f"\n📅 Testing {date_str} ({current.strftime('%A')})...")
            
            success = self.run_day(date_str)
            if success:
                days_tested += 1
            else:
                days_skipped += 1
            
            current += timedelta(days=1)
        
        print("\n" + "=" * 70)
        print(f"✅ Backtest Complete")
        print(f"Days Tested: {days_tested} | Days Skipped: {days_skipped}")
        print("=" * 70)
        
        self.generate_report()
    
    def run_day(self, date: str) -> bool:
        """
        Run backtest for a single day.
        
        Args:
            date: Date string (YYYY-MM-DD)
        
        Returns:
            True if day was successfully tested, False if skipped
        """
        # Initialize strategy for this day
        strategy = self.strategy_class(self.config)
        
        try:
            if not strategy.initialize(self.data_manager, date):
                print(f"  ⏭️  Skipped: Strategy initialization failed")
                return False
        except Exception as e:
            print(f"  ❌ Skipped: Initialization error: {e}")
            return False
        
        # Get trading data for the day
        # This is strategy-specific, but we can provide a generic framework
        # The strategy's on_candle method will be called for each candle
        
        # For now, we'll let the strategy handle the candle iteration
        # in its initialize() method, or we can implement a generic candle loop here
        
        # Check for trades
        day_trades = []
        
        # Strategy should have executed trades during initialize or on_candle calls
        # We need to collect them
        if hasattr(strategy, 'get_completed_trades'):
            day_trades = strategy.get_completed_trades()
            self.trades.extend(day_trades)
        
        if day_trades:
            print(f"  ✅ {len(day_trades)} trade(s) executed")
        else:
            print(f"  ℹ️  No trades")
        
        return True
    
    def generate_report(self):
        """Generate and save backtest report."""
        if not self.trades:
            print("\n❌ No trades executed during backtest period.")
            return
        
        df = pd.DataFrame(self.trades)
        
        # Calculate metrics
        total_pnl = df['pnl'].sum()
        win_trades = df[df['pnl'] > 0]
        loss_trades = df[df['pnl'] <= 0]
        
        print("\n" + "=" * 70)
        print(f"📊 BACKTEST REPORT: {self.strategy_class.__name__}")
        print("=" * 70)
        print(f"Period      : {self.from_date} to {self.to_date}")
        print(f"Total PnL   : ₹{total_pnl:.2f}")
        print(f"Trades      : {len(df)}")
        print(f"Win Rate    : {len(win_trades)/len(df)*100:.1f}% ({len(win_trades)}W / {len(loss_trades)}L)")
        
        if not win_trades.empty:
            print(f"Avg Win     : ₹{win_trades['pnl'].mean():.2f}")
            print(f"Max Win     : ₹{win_trades['pnl'].max():.2f}")
        
        if not loss_trades.empty:
            print(f"Avg Loss    : ₹{loss_trades['pnl'].mean():.2f}")
            print(f"Max Loss    : ₹{loss_trades['pnl'].min():.2f}")
        
        print("=" * 70)
        
        # Save to CSV
        strategy_name = self.strategy_class.__name__.replace('Backtest', '').replace('Strategy', '')
        # Create reports directory if it doesn't exist
        reports_dir = os.path.join(os.getcwd(), 'reports', strategy_name)
        os.makedirs(reports_dir, exist_ok=True)
        
        filename = f"backtest_report_{strategy_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        filepath = os.path.join(reports_dir, filename)
        
        df.to_csv(filepath, index=False)
        print(f"📝 Detailed report saved to {filepath}")
        
        return df

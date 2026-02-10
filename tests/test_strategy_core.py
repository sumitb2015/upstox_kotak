import unittest
from unittest.mock import MagicMock
from datetime import datetime
import sys
import os

# Path Setup
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from strategies.directional.dynamic_straddle_skew.strategy_core import DynamicStraddleSkewCore, LegPosition

# Concrete implementation for testing
class TestableStrategy(DynamicStraddleSkewCore):
    def execute_trade(self, option_type: str, action: str, lots: int, price: float, strike: int = None):
        return True

class TestStrategyCore(unittest.TestCase):
    def setUp(self):
        self.config = {
            'initial_lots': 1,
            'max_pyramid_lots': 3,
            'skew_threshold_pct': 0.15,
            'pyramid_trigger_decay_pct': 0.10,
            'reduction_recovery_pct': 0.10,
            'max_loss_per_day': 5000,
            'target_profit_pct': 0.20,
            'profit_locking': {'enabled': True, 'lock_threshold_pct': 0.05, 'lock_ratio': 0.50}
        }
        self.strategy = TestableStrategy(self.config)
        
        # Setup Initial Legs
        self.strategy.ce_leg = LegPosition('CE', 25000, 100.0, 1, 'key_ce')
        self.strategy.pe_leg = LegPosition('PE', 25000, 100.0, 1, 'key_pe')
        self.strategy.initial_capital = 200000.0 # 2L Capital

    def test_check_skew_signal(self):
        # 1. Neutral (No Skew)
        # CE 100, PE 100
        signal = self.strategy.check_skew_signal(100, 100)
        self.assertIsNone(signal)
        
        # 2. CE Winning (Price drop)
        # CE 80, PE 100. Diff = 20%. Threshold 15%
        # 80 < 100 * (1 - 0.15) -> 80 < 85 -> True
        signal = self.strategy.check_skew_signal(80, 100)
        self.assertEqual(signal, 'CE')
        
        # 3. PE Winning
        signal = self.strategy.check_skew_signal(100, 80)
        self.assertEqual(signal, 'PE')

    def test_check_pyramid_signal(self):
        self.strategy.winning_type = 'CE'
        
        # Initial Prem = 200 (100+100)
        # Trigger Decay = 10% -> 20 pts
        # Target Total < 180
        
        # Case A: Small Decay (190) -> False
        self.strategy.ce_leg.current_price = 90
        self.strategy.pe_leg.current_price = 100
        is_pyramid, msg = self.strategy.check_pyramid_signal()
        self.assertFalse(is_pyramid)
        
        # Case B: Decay Hit (170) -> True
        self.strategy.ce_leg.current_price = 70
        self.strategy.pe_leg.current_price = 100
        is_pyramid, msg = self.strategy.check_pyramid_signal()
        self.assertTrue(is_pyramid, f"Should pyramid: {msg}")

    def test_check_reduction_signal(self):
        self.strategy.winning_type = 'CE'
        self.strategy.ce_leg.lots = 2 # Must have pyramid lots
        
        # Set Lowest Price
        self.strategy.ce_leg.lowest_price = 50.0
        
        # Case A: Small Bounce (52) -> 4% -> False
        self.strategy.ce_leg.current_price = 52.0
        is_reduce, msg = self.strategy.check_reduction_signal()
        self.assertFalse(is_reduce)
        
        # Case B: Large Bounce (56) -> 12% (>10%) -> True
        self.strategy.ce_leg.current_price = 56.0
        is_reduce, msg = self.strategy.check_reduction_signal()
        self.assertTrue(is_reduce, f"Should reduce: {msg}")

    def test_profit_locking(self):
        # Capital 2L. Lock Threshold 5% = 10k. 
        # Lock Ratio 50%
        
        # 1. Profit 5k (Below threshold) -> No Lock
        stop, msg = self.strategy.check_profit_goals(5000)
        self.assertFalse(stop)
        self.assertEqual(self.strategy.max_profit_reached, 5000)
        self.assertEqual(self.strategy.locked_profit, 0)
        
        # 2. Profit 12k (Peak) -> Lock 6k
        stop, msg = self.strategy.check_profit_goals(12000)
        self.assertFalse(stop)
        self.assertEqual(self.strategy.max_profit_reached, 12000)
        self.assertEqual(self.strategy.locked_profit, 6000)
        
        # 3. Drop to 7k (Above Lock 6k) -> Continue
        stop, msg = self.strategy.check_profit_goals(7000)
        self.assertFalse(stop)
        
        # 4. Drop to 5k (Below Lock 6k) -> Exit
        stop, msg = self.strategy.check_profit_goals(5000)
        self.assertTrue(stop)
        self.assertIn("Profit Lock Hit", msg)

if __name__ == '__main__':
    unittest.main()

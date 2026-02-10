
import unittest
from datetime import datetime, timedelta
import logging
import sys
import os

# Add root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

# Mocking config and core
from strategies.directional.supertrend_multitimeframe.core import SupertrendStrategyCore
from strategies.directional.supertrend_multitimeframe.config import CONFIG

# Disable logging for test
logging.basicConfig(level=logging.CRITICAL)

class TestCooldown(unittest.TestCase):
    def setUp(self):
        self.config = CONFIG.copy()
        self.config['cooldown_minutes'] = 5
        self.core = SupertrendStrategyCore(self.config)
        self.core.nifty_trend = -1 # Bearish -> CE Signal Target (Short CE)
        # Wait, if Nifty is Bearish (-1), we SHORT CE. 
        # Logic: target_type = "CE" if self.nifty_trend == -1 else "PE"
        
    def test_cooldown_active(self):
        # 1. Simulate Exit on CE
        self.core.record_exit('CE')
        
        # 2. Check Signals (should fail cooldown)
        # We don't need real API access because cooldown check is BEFORE API calls
        # check_signals returns: (SignalType, Token, Strike, Expiry, Price)
        # If cooldown active, it returns (None, None, None, None, 0.0)
        
        res = self.core.check_signals("dummy_token")
        self.assertEqual(res, (None, None, None, None, 0.0), "Should block signal during cooldown")
        
        print("✅ Test 1 Passed: Cooldown blocked signal.")

    def test_cooldown_expired(self):
        # 1. Simulate Old Exit (6 mins ago)
        self.core.side_cooldowns['CE'] = datetime.now() - timedelta(minutes=6)
        
        # 2. Check Signals
        # Since we don't have real API data, check_signals needs to pass the cooldown check
        # and THEN fail at 'get_target_strike' or return None.
        # But crucially, if it fails at get_target_strike, it means it PASSED the cooldown check.
        # However, checking if it passed cooldown is hard without mocking get_target_strike.
        
        # Let's simple-mock get_target_strike to raise a specific exception or return a mock
        # to prove we got there.
        
        original_method = self.core.get_target_strike
        self.core.get_target_strike = lambda token, type: ("MOCK_TOKEN", "10000", 100, "EXP")
        
        # Also mock calc_option_supertrend to return None so we don't need API
        self.core.calculate_option_supertrend = lambda token, t: (0, 0, 0, 0)
        
        res = self.core.check_signals("dummy_token")
        
        # It should NOT return (None, None, None, None, 0.0) immediately.
        # Because we mocked strike selection, it might try to calculate ST.
        # If ST returns 0, it returns None.
        
        # The key is: Did we clear the cooldown?
        # The logic says: "else: self.side_cooldowns[target_type] = None"
        
        self.assertIsNone(self.core.side_cooldowns['CE'], "Cooldown should be cleared after expiry time check")
        print("✅ Test 2 Passed: Cooldown cleared after expiration.")

if __name__ == '__main__':
    unittest.main()

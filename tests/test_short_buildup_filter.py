import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategies.directional.futures_vwap_supertrend.live import FuturesVWAPSupertrendLive

class TestShortBuildupFilter(unittest.TestCase):
    def setUp(self):
        self.config = {
            'underlying': 'NIFTY',
            'expiry_type': 'current_week',
            'short_buildup_enabled': True,
            'short_buildup_p_dec_threshold': 0.20,
            'short_buildup_oi_inc_threshold': 0.30,
            'oi_strikes_radius': 4
        }
        self.strategy = FuturesVWAPSupertrendLive("dummy_token", self.config)
        self.strategy.oi_analyzer = MagicMock()
        self.strategy.oi_analyzer.underlying_key = "NSE_INDEX|Nifty 50"

    @patch('strategies.directional.futures_vwap_supertrend.live.get_expiry_for_strategy')
    @patch('strategies.directional.futures_vwap_supertrend.live.get_option_chain_atm')
    def test_find_short_buildup_strike_success(self, mock_chain, mock_expiry):
        mock_expiry.return_value = "2026-01-29"
        
        # Mock data where CE 24000 has 25% price drop and 40% OI increase
        # ATM is 23800. Min OTM offset 100 means strike >= 23900.
        data = [
            {'strike_price': 23900, 'instrument_type': 'CE', 'ltp': 100, 'prev_ltp': 110, 'oi': 1000, 'prev_oi': 900}, # No buildup
            {'strike_price': 24000, 'instrument_type': 'CE', 'ltp': 75, 'prev_ltp': 100, 'oi': 1400, 'prev_oi': 1000}, # P-Dec 25%, OI-Inc 40% (Qualifies)
            {'strike_price': 24100, 'instrument_type': 'CE', 'ltp': 50, 'prev_ltp': 60, 'oi': 2000, 'prev_oi': 1800},  # P-Dec 16%, OI-Inc 11% (No)
        ]
        mock_chain.return_value = pd.DataFrame(data)
        
        result = self.strategy.find_short_buildup_strike('CE', 24050, 23800)
        self.assertEqual(result, 24000)

    @patch('strategies.directional.futures_vwap_supertrend.live.get_expiry_for_strategy')
    @patch('strategies.directional.futures_vwap_supertrend.live.get_option_chain_atm')
    def test_find_short_buildup_strike_no_match(self, mock_chain, mock_expiry):
        mock_expiry.return_value = "2026-01-29"
        
        # Mock data where NO strike meets criteria
        data = [
            {'strike_price': 23900, 'instrument_type': 'CE', 'ltp': 100, 'prev_ltp': 110, 'oi': 1000, 'prev_oi': 900},
            {'strike_price': 24000, 'instrument_type': 'CE', 'ltp': 90, 'prev_ltp': 100, 'oi': 1100, 'prev_oi': 1000},
        ]
        mock_chain.return_value = pd.DataFrame(data)
        
        result = self.strategy.find_short_buildup_strike('CE', 24000, 23800)
        self.assertIsNone(result)

    @patch('strategies.directional.futures_vwap_supertrend.live.get_expiry_for_strategy')
    @patch('strategies.directional.futures_vwap_supertrend.live.get_option_chain_atm')
    def test_find_short_buildup_strike_otm_constraint(self, mock_chain, mock_expiry):
        mock_expiry.return_value = "2026-01-29"
        
        # ATM is 24000. Min OTM offset 100 means CE strike >= 24100.
        # 24050 has buildup but fails OTM constraint.
        data = [
            {'strike_price': 24050, 'instrument_type': 'CE', 'ltp': 75, 'prev_ltp': 100, 'oi': 1400, 'prev_oi': 1000}, # Buildup YES, OTM NO
            {'strike_price': 24150, 'instrument_type': 'CE', 'ltp': 75, 'prev_ltp': 100, 'oi': 1400, 'prev_oi': 1000}, # Buildup YES, OTM YES
        ]
        mock_chain.return_value = pd.DataFrame(data)
        
        result = self.strategy.find_short_buildup_strike('CE', 24100, 24000)
        self.assertEqual(result, 24150)

    @patch('strategies.directional.futures_vwap_supertrend.live.get_expiry_for_strategy')
    @patch('strategies.directional.futures_vwap_supertrend.live.get_option_chain_atm')
    def test_find_short_buildup_closest_match(self, mock_chain, mock_expiry):
        mock_expiry.return_value = "2026-01-29"
        
        # Mock data where two strikes qualify, should pick closest to ideal_strike (24050)
        # ATM is 23800.
        data = [
            {'strike_price': 23900, 'instrument_type': 'CE', 'ltp': 70, 'prev_ltp': 100, 'oi': 1500, 'prev_oi': 1000}, # Qualifies, diff 150
            {'strike_price': 24100, 'instrument_type': 'CE', 'ltp': 30, 'prev_ltp': 50, 'oi': 1500, 'prev_oi': 1000},  # Qualifies, diff 50
        ]
        mock_chain.return_value = pd.DataFrame(data)
        
        result = self.strategy.find_short_buildup_strike('CE', 24050, 23800)
        self.assertEqual(result, 24100)

if __name__ == '__main__':
    unittest.main()

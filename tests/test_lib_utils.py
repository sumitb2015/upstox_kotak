import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
from datetime import datetime, date, timedelta

# Import modules to test
# Adjust path if necessary or rely on PYTHONPATH
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from lib.utils import instrument_utils
from lib.utils import expiry_cache

class TestInstrumentUtils(unittest.TestCase):
    def setUp(self):
        # Create a mock NSE data DataFrame
        self.mock_nse_data = pd.DataFrame([
            {
                'instrument_key': 'NSE_FO|12345',
                'underlying_symbol': 'NIFTY',
                'strike_price': 25000,
                'instrument_type': 'CE',
                'expiry': (datetime.now() + timedelta(days=5)).date(), # Future expiry
                'lot_size': 75
            },
            {
                'instrument_key': 'NSE_FO|67890',
                'underlying_symbol': 'NIFTY',
                'strike_price': 25000,
                'instrument_type': 'PE',
                'expiry': (datetime.now() + timedelta(days=5)).date(),
                'lot_size': 75
            },
            {
                'instrument_key': 'NSE_FO|11111',
                'underlying_symbol': 'BANKNIFTY',
                'strike_price': 50000,
                'instrument_type': 'CE',
                'expiry': (datetime.now() + timedelta(days=5)).date(),
                'lot_size': 30
            }
        ])

    def test_get_option_instrument_key(self):
        # Test finding a CE key
        key = instrument_utils.get_option_instrument_key('NIFTY', 25000, 'CE', self.mock_nse_data)
        self.assertEqual(key, 'NSE_FO|12345')

        # Test finding a PE key
        key = instrument_utils.get_option_instrument_key('NIFTY', 25000, 'PE', self.mock_nse_data)
        self.assertEqual(key, 'NSE_FO|67890')

        # Test non-existent strike
        key = instrument_utils.get_option_instrument_key('NIFTY', 99999, 'CE', self.mock_nse_data)
        self.assertIsNone(key)

    def test_get_lot_size(self):
        # Test NIFTY lot size
        lot = instrument_utils.get_lot_size('NSE_FO|12345', self.mock_nse_data)
        self.assertEqual(lot, 75)

        # Test BANKNIFTY lot size
        lot = instrument_utils.get_lot_size('NSE_FO|11111', self.mock_nse_data)
        self.assertEqual(lot, 30)

        # Test default fallback
        lot = instrument_utils.get_lot_size('UNKNOWN', self.mock_nse_data)
        self.assertEqual(lot, 75) # Default 75 

class TestExpiryCache(unittest.TestCase):
    def setUp(self):
        # Mock Expiry DataFrame
        today = datetime.now().date()
        self.mock_expiries = pd.DataFrame([
            {'date': str(today + timedelta(days=2)), 'type': 'weekly', 'month': today.month, 'year': today.year},
            {'date': str(today + timedelta(days=9)), 'type': 'weekly', 'month': today.month, 'year': today.year},
            {'date': str(today + timedelta(days=30)), 'type': 'monthly', 'month': (today + timedelta(days=30)).month, 'year': (today + timedelta(days=30)).year}
        ])

    def test_get_expiry_by_type_current_week(self):
        expected = self.mock_expiries.iloc[0]['date']
        result = expiry_cache.get_expiry_by_type(self.mock_expiries, 'current_week')
        self.assertEqual(result, expected)

    def test_get_expiry_by_type_next_week(self):
        expected = self.mock_expiries.iloc[1]['date']
        result = expiry_cache.get_expiry_by_type(self.mock_expiries, 'next_week')
        self.assertEqual(result, expected)
        
    def test_get_expiry_by_type_monthly(self):
        expected = self.mock_expiries.iloc[2]['date']
        result = expiry_cache.get_expiry_by_type(self.mock_expiries, 'monthly')
        self.assertEqual(result, expected)

if __name__ == '__main__':
    unittest.main()

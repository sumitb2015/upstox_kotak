import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.api.user import get_user_profile, get_funds_summary
from lib.api.portfolio import get_holdings, get_positions
from lib.api.market_data import get_option_expiry_dates, get_market_status
from lib.api.order_management import get_order_details

class TestLibrary(unittest.TestCase):
    def setUp(self):
        self.access_token = "dummy_token"

    @patch('upstox_client.UserApi.get_profile')
    def test_get_user_profile(self, mock_get):
        # Setup mock response
        mock_response = MagicMock()
        mock_response.data = {'user_name': 'Test User'}
        mock_get.return_value = mock_response
        
        result = get_user_profile(self.access_token)
        self.assertIsNotNone(result)
        self.assertEqual(result['user_name'], 'Test User')

    @patch('upstox_client.PortfolioApi.get_holdings')
    def test_get_holdings(self, mock_get):
        mock_response = MagicMock()
        mock_holding = MagicMock()
        mock_holding.trading_symbol = 'RELIANCE'
        mock_response.data = [mock_holding]
        mock_get.return_value = mock_response
        
        df = get_holdings(self.access_token)
        self.assertFalse(df.empty)
        self.assertEqual(df.iloc[0]['trading_symbol'], 'RELIANCE')

    def test_market_status(self):
        status = get_market_status()
        self.assertIn(status, ["OPEN", "CLOSED", "UNKNOWN"])

    @patch('upstox_client.OrderApi.get_order_details')
    def test_get_order_details(self, mock_get):
        mock_response = MagicMock()
        mock_order = MagicMock()
        mock_order.to_dict.return_value = {'order_id': '123'}
        mock_response.data = [mock_order]
        mock_get.return_value = mock_response
        
        result = get_order_details(self.access_token, "123")
        self.assertIsNotNone(result)
        # result is a list of dicts now
        self.assertEqual(result[0]['order_id'], '123')

if __name__ == '__main__':
    unittest.main()

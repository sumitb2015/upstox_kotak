import unittest
from unittest.mock import MagicMock, patch, mock_open
import sys
import os
import datetime
import json

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from lib.core import authentication
from lib.api import market_data

class TestApiIntegration(unittest.TestCase):
    
    # === Authentication Tests ===
    
    @patch('builtins.open', new_callable=mock_open, read_data='dummy_token_123')
    @patch('lib.core.authentication.os.path.exists')
    @patch('lib.core.authentication.os.path.getmtime')
    @patch('lib.core.authentication.datetime')
    @patch('lib.core.authentication.validate_token')
    def test_get_access_token_from_file(self, mock_validate, mock_datetime, mock_getmtime, mock_exists, mock_file):
        """Test authentication token loading from file"""
        # Setup mocks to make check_existing_token return True
        mock_exists.return_value = True
        
        # Mock file time to be "today"
        mock_now = datetime.datetime(2025, 1, 1, 10, 0, 0)
        mock_datetime.now.return_value = mock_now
        mock_datetime.fromtimestamp.return_value = mock_now # File modified "now"
        
        mock_validate.return_value = True  # validation passes
        
        token = authentication.get_access_token()
        self.assertEqual(token, 'dummy_token_123')
        
    @patch.dict(os.environ, {'UPSTOX_ACCESS_TOKEN': 'env_token_456'})
    @patch('lib.core.authentication.os.path.exists')
    @patch('lib.core.authentication.validate_token')
    def test_get_access_token_from_env(self, mock_validate, mock_exists):
        """Test authentication token fallback to environment variable"""
        mock_exists.return_value = False # Simulate file missing
        mock_validate.return_value = True # validation passes
        
        token = authentication.get_access_token()
        self.assertEqual(token, 'env_token_456')

    # === Market Data Tests (Mocked SDK) ===

    @patch('upstox_client.MarketQuoteApi.get_full_market_quote')
    def test_get_market_quotes(self, mock_get_quote):
        """Test fetching quotes via SDK mock"""
        
        # Setup Mock Response
        mock_response = MagicMock()
        mock_response.status = "success"
        
        # Mock quote object
        mock_quote = MagicMock()
        mock_quote.to_dict.return_value = {
            "instrument_token": "NSE_FO|12345",
            "last_price": 25000.0,
            "volume": 1000,
            "ohlc": {"open": 24900.0, "close": 25000.0}
        }
        
        mock_response.data = {
            "NSE_FO|12345": mock_quote
        }
        mock_get_quote.return_value = mock_response
        
        # Call Function
        quotes = market_data.get_market_quotes("dummy_token", ["NSE_FO|12345"])
        
        # Verify
        self.assertIn("NSE_FO|12345", quotes)
        self.assertEqual(quotes["NSE_FO|12345"]["last_price"], 25000.0)

    @patch('upstox_client.MarketQuoteApi.get_full_market_quote')
    def test_get_market_quote_heuristic(self, mock_get_quote):
        """Test the heuristic lookup for mismatched keys (e.g. | vs :)"""
        
        # Scenario: API returns key with ':' instead of '|'
        mock_response = MagicMock()
        mock_response.status = "success"
        
        mock_quote = MagicMock()
        mock_quote.to_dict.return_value = {
            "instrument_token": "NSE_FO|99999", # The actual key is inside
            "last_price": 150.0
        }
        
        # SDK returns a dict keyed by the requested symbols usually, but here we simulate mismatch
        mock_response.data = {
            "NSE_FO:NIFTY23FEB...": mock_quote
        }
        mock_get_quote.return_value = mock_response
        
        # We request with Pipe '|' format
        quote = market_data.get_market_quote_for_instrument("dummy_token", "NSE_FO|99999")
        
        self.assertIsNotNone(quote)
        self.assertEqual(quote['last_price'], 150.0)
        self.assertEqual(quote['instrument_token'], "NSE_FO|99999")

if __name__ == '__main__':
    unittest.main()

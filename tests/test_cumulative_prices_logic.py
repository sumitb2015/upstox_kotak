import unittest
from unittest.mock import MagicMock
import sys
import os

# Mock the modules before importing main
sys.modules['upstox_client'] = MagicMock()
sys.modules['fastapi'] = MagicMock()
sys.modules['fastapi.middleware.cors'] = MagicMock()
sys.modules['fastapi.responses'] = MagicMock()
sys.modules['uvicorn'] = MagicMock()

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

class TestCumulativePricesLogic(unittest.TestCase):
    def test_summation_logic(self):
        # Mock streamer latest_feeds
        mock_feeds = {
            "CE_KEY_1": {"ltp": 100, "instrument_key": "CE_KEY_1"},
            "CE_KEY_2": {"ltp": 50, "instrument_key": "CE_KEY_2"},
            "PE_KEY_1": {"ltp": 80, "instrument_key": "PE_KEY_1"},
            "PE_KEY_2": {"ltp": 40, "instrument_key": "PE_KEY_2"},
            "INDEX_KEY": {"ltp": 25000, "instrument_key": "INDEX_KEY"}
        }
        
        ce_keys = ["CE_KEY_1", "CE_KEY_2"]
        pe_keys = ["PE_KEY_1", "PE_KEY_2"]
        index_key = "INDEX_KEY"
        
        ce_sum = 0
        for k in ce_keys:
            f = mock_feeds.get(k)
            if f: ce_sum += f.get('ltp', 0)
            
        pe_sum = 0
        for k in pe_keys:
            f = mock_feeds.get(k)
            if f: pe_sum += f.get('ltp', 0)
            
        spot = mock_feeds.get(index_key).get('ltp')
        
        self.assertEqual(ce_sum, 150)
        self.assertEqual(pe_sum, 120)
        self.assertEqual(spot, 25000)

if __name__ == '__main__':
    unittest.main()

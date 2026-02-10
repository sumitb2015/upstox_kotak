import unittest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch

# Path Setup
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from lib.utils import indicators

class TestIndicators(unittest.TestCase):
    def setUp(self):
        # Create a sample DataFrame
        self.df = pd.DataFrame({
            'open': np.arange(100, 200, 1),
            'high': np.arange(105, 205, 1),
            'low': np.arange(95, 195, 1),
            'close': np.arange(102, 202, 1),
            'volume': np.full(100, 1000)
        })

    @patch('talib.EMA')
    def test_calculate_ema(self, mock_ema):
        # Mock TA-Lib EMA output
        mock_ema.return_value = np.array([150.0] * 100)
        
        val = indicators.calculate_ema(self.df, 20)
        self.assertEqual(val, 150.0)
        
        # Verify call args
        args, kwargs = mock_ema.call_args
        self.assertEqual(kwargs['timeperiod'], 20)

    @patch('talib.RSI')
    def test_calculate_rsi(self, mock_rsi):
        # Mock TA-Lib RSI output
        mock_rsi.return_value = np.array([60.5] * 100)
        
        val = indicators.calculate_rsi(self.df, 14)
        self.assertEqual(val, 60.5)

    def test_calculate_vwap(self):
        # Manual Calculation for small dataset
        # Typical Price = (H+L+C)/3
        # Weight = Volume
        
        small_df = pd.DataFrame({
            'high': [100, 110],
            'low': [90, 100],
            'close': [95, 105],
            'volume': [100, 200]
        })
        # TP1 = (100+90+95)/3 = 95.0. PV1 = 9500
        # TP2 = (110+100+105)/3 = 105.0. PV2 = 21000
        # CumPV = 30500. CumVol = 300
        # VWAP = 30500 / 300 = 101.666...
        
        vwap = indicators.calculate_vwap(small_df)
        self.assertAlmostEqual(vwap, 101.666666666)

    @patch('talib.ATR')
    def test_calculate_supertrend(self, mock_atr):
        # Mock ATR to return constant volatility
        # If ATR is 2.0, Multiplier 3 -> Band width is 6.0
        mock_atr.return_value = np.full(len(self.df), 2.0)
        
        # Create a specific scenario:
        # We need enough data to skip the warmup loop
        
        trend, st_value = indicators.calculate_supertrend(self.df, period=10, multiplier=3)
        
        # Just ensure it returns valid float tuple
        self.assertIsInstance(trend, float)
        self.assertIsInstance(st_value, float)
        self.assertIn(trend, [1.0, -1.0])

if __name__ == '__main__':
    unittest.main()

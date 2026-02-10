import unittest
import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from lib.core.authentication import get_access_token
from lib.api.historical import get_historical_data
from lib.utils.indicators import calculate_ema_series, calculate_supertrend, calculate_atr, calculate_rsi

class TestIndicatorsLiveVerification(unittest.TestCase):
    """
    Integration tests to verify technical indicators against YFinance.
    Requires active internet connection and valid Upstox token.
    """
    
    @classmethod
    def setUpClass(cls):
        # Check for dependencies
        try:
            import yfinance
            cls.yfinance = yfinance
        except ImportError:
            raise unittest.SkipTest("yfinance not installed")
            
        # Get Token
        cls.token = get_access_token(auto_refresh=False)
        if not cls.token:
            raise unittest.SkipTest("No valid Upstox token found. Skipping live verification.")

    def fetch_yfinance_data(self, symbol, interval, days):
        """Helper to fetch YFinance data"""
        df = self.yfinance.download(symbol, period=f"{days}d", interval=interval, progress=False)
        if df.empty:
            return None
            
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        df = df.reset_index()
        # Rename columns to lowercase for consistency
        df.columns = [c.lower() for c in df.columns]
        
        # Standardize timestamp column name
        if 'datetime' in df.columns:
            df.rename(columns={'datetime': 'timestamp'}, inplace=True)
        elif 'date' in df.columns:
            df.rename(columns={'date': 'timestamp'}, inplace=True)
            
        # Timezone standardization to Asia/Kolkata
        if df['timestamp'].dt.tz is None:
            df['timestamp'] = df['timestamp'].dt.tz_localize('Asia/Kolkata')
        else:
            df['timestamp'] = df['timestamp'].dt.tz_convert('Asia/Kolkata')
            
        # Floor seconds to ensure alignment
        df['timestamp'] = df['timestamp'].dt.floor('min')
        
        print(f"   -> Downloaded YFinance data ({symbol}): {len(df)} rows")
        return df

    def fetch_upstox_data(self, instrument_key, interval_str, lookback_candles):
        """Helper to fetch Upstox data"""
        data = get_historical_data(self.token, instrument_key, interval_str, lookback_candles)
        if not data:
            return None
            
        df = pd.DataFrame(data)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        if df['timestamp'].dt.tz is None:
             df['timestamp'] = df['timestamp'].dt.tz_localize('Asia/Kolkata')
        else:
             df['timestamp'] = df['timestamp'].dt.tz_convert('Asia/Kolkata')
             
        df['timestamp'] = df['timestamp'].dt.floor('min')
        print(f"   -> Downloaded Upstox data ({instrument_key}): {len(df)} rows")
        return df

    def test_verify_nifty_indicators_vs_yfinance(self):
        """Verify 1-minute indicators against YFinance"""
        print("\n[Test] Verifying Nifty 1-min Indicators vs YFinance...")
        
        # 1. Fetch Data
        df_yf = self.fetch_yfinance_data("^NSEI", "1m", 3)
        df_up = self.fetch_upstox_data("NSE_INDEX|Nifty 50", "1minute", 2000)
        
        self.assertIsNotNone(df_yf, "YFinance data fetch failed")
        self.assertIsNotNone(df_up, "Upstox data fetch failed")
        
        # 2. Align Dataframes
        min_date = max(df_yf['timestamp'].min(), df_up['timestamp'].min())
        df_yf = df_yf[df_yf['timestamp'] >= min_date]
        df_up = df_up[df_up['timestamp'] >= min_date]
        
        merged = pd.merge(df_yf, df_up, on='timestamp', suffixes=('_yf', '_up'), how='inner')
        print(f"Matched {len(merged)} candles")
        
        if len(merged) < 50:
            self.skipTest("Not enough matching data for meaningful verification")

        # 3. Prepare Calc DFs
        df_u_calc = pd.DataFrame({
            'open': merged['open_up'], 'high': merged['high_up'],
            'low': merged['low_up'], 'close': merged['close_up'],
            'volume': merged['volume_up'], 'timestamp': merged['timestamp']
        })
        
        df_y_calc = pd.DataFrame({
            'open': merged['open_yf'], 'high': merged['high_yf'],
            'low': merged['low_yf'], 'close': merged['close_yf'],
            'volume': merged['volume_yf'], 'timestamp': merged['timestamp']
        })
        
        # 4. Assertions & Reporting
        print("\n   [Comparison Results - 1 Minute]")
        print(f"   {'Indicator':<15} | {'Upstox':<12} | {'YFinance':<12} | {'Diff':<10} | {'Status'}")
        print("   " + "-"*65)

        # EMA (20)
        ema_u = calculate_ema_series(df_u_calc, 20).iloc[-1]
        ema_y = calculate_ema_series(df_y_calc, 20).iloc[-1]
        diff_ema = abs(ema_u - ema_y)
        status_ema = "✅ PASS" if diff_ema <= 0.5 else "❌ FAIL"
        print(f"   {'EMA (20)':<15} | {ema_u:<12.2f} | {ema_y:<12.2f} | {diff_ema:<10.4f} | {status_ema}")
        self.assertAlmostEqual(ema_u, ema_y, delta=0.5, msg="EMA 20 mismatch > 0.5")

        # ATR (14)
        atr_u = calculate_atr(df_u_calc, 14)
        atr_y = calculate_atr(df_y_calc, 14)
        diff_atr = abs(atr_u - atr_y)
        status_atr = "✅ PASS" if diff_atr <= 0.5 else "❌ FAIL"
        print(f"   {'ATR (14)':<15} | {atr_u:<12.2f} | {atr_y:<12.2f} | {diff_atr:<10.4f} | {status_atr}")
        self.assertAlmostEqual(atr_u, atr_y, delta=0.5, msg="ATR 14 mismatch > 0.5")
        
        # Supertrend
        _, st_val_u = calculate_supertrend(df_u_calc, 10, 3)
        _, st_val_y = calculate_supertrend(df_y_calc, 10, 3)
        diff_st = abs(st_val_u - st_val_y)
        status_st = "✅ PASS" if diff_st <= 2.0 else "❌ FAIL"
        print(f"   {'Supertrend':<15} | {st_val_u:<12.2f} | {st_val_y:<12.2f} | {diff_st:<10.4f} | {status_st}")
        
        # Supertrend can diverge slightly more due to ATR smoothing differences
        self.assertAlmostEqual(st_val_u, st_val_y, delta=2.0, msg="Supertrend mismatch > 2.0")

    def test_verify_5min_resampling(self):
        """Verify resampled 5-minute indicators vs YFinance"""
        print("\n[Test] Verifying 5-min Resampling & Indicators vs YFinance...")
        
        # 1. Fetch Data
        df_yf_5m = self.fetch_yfinance_data("^NSEI", "5m", 5)
        df_up_1m = self.fetch_upstox_data("NSE_INDEX|Nifty 50", "1minute", 3000)

        self.assertIsNotNone(df_yf_5m, "YFinance 5m fetch failed")
        self.assertIsNotNone(df_up_1m, "Upstox 1m fetch failed")

        # 2. Resample Upstox 1m -> 5m
        df_1m = df_up_1m.set_index('timestamp').sort_index()
        resampled = df_1m.resample('5min', label='left', closed='left').agg({
            'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
        }).dropna().reset_index()
        
        # 3. Align
        merged = pd.merge(df_yf_5m, resampled, on='timestamp', suffixes=('_yf', '_up'), how='inner')
        print(f"Matched {len(merged)} resampled candles")
        
        if len(merged) < 20:
            self.skipTest("Not enough matching data for resampling check")

        # 4. Prepare Calc DFs
        df_u_calc = pd.DataFrame({
            'open': merged['open_up'], 'high': merged['high_up'],
            'low': merged['low_up'], 'close': merged['close_up'],
            'volume': merged['volume_up'], 'timestamp': merged['timestamp']
        })
        
        df_y_calc = pd.DataFrame({
            'open': merged['open_yf'], 'high': merged['high_yf'],
            'low': merged['low_yf'], 'close': merged['close_yf'],
            'volume': merged['volume_yf'], 'timestamp': merged['timestamp']
        })
        
        # 5. Assertions & Reporting
        print("\n   [Comparison Results - 5 Minute Resampled]")
        print(f"   {'Indicator':<15} | {'Upstox':<12} | {'YFinance':<12} | {'Diff':<10} | {'Status'}")
        print("   " + "-"*65)

        # Price Integrity Check
        diff_close = abs(merged['close_up'] - merged['close_yf']).max()
        status_price = "✅ PASS" if diff_close < 1.0 else "❌ FAIL"
        print(f"   {'Close Price':<15} | {'(Max Diff)':<12} | {'-':<12} | {diff_close:<10.4f} | {status_price}")
        self.assertLess(diff_close, 1.0, f"Max Close Price diff {diff_close} too high")
        
        # EMA (20)
        ema_u = calculate_ema_series(df_u_calc, 20).iloc[-1]
        ema_y = calculate_ema_series(df_y_calc, 20).iloc[-1]
        diff_ema = abs(ema_u - ema_y)
        status_ema = "✅ PASS" if diff_ema <= 1.0 else "❌ FAIL"
        print(f"   {'EMA (20)':<15} | {ema_u:<12.2f} | {ema_y:<12.2f} | {diff_ema:<10.4f} | {status_ema}")
        self.assertAlmostEqual(ema_u, ema_y, delta=1.0, msg="EMA 20 (Resampled) mismatch > 1.0")

        # Supertrend
        _, st_val_u = calculate_supertrend(df_u_calc, 10, 3)
        _, st_val_y = calculate_supertrend(df_y_calc, 10, 3)
        diff_st = abs(st_val_u - st_val_y)
        status_st = "✅ PASS" if diff_st <= 3.0 else "❌ FAIL"
        print(f"   {'Supertrend':<15} | {st_val_u:<12.2f} | {st_val_y:<12.2f} | {diff_st:<10.4f} | {status_st}")
        self.assertAlmostEqual(st_val_u, st_val_y, delta=3.0, msg="Supertrend (Resampled) mismatch > 3.0")

if __name__ == '__main__':
    unittest.main()

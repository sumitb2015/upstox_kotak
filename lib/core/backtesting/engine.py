import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time
import os
import sys

# Add root to sys path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from lib.api.historical import get_historical_data_v3, get_intraday_data_v3
from lib.api.expired_data import get_expired_option_contracts, get_expired_historical_candles, get_expired_expiry_dates
from lib.utils.instrument_utils import get_instrument_key
from lib.core.config import Config

class BacktestDataManager:
    """Manages data fetching and storage for backtesting"""
    
    def __init__(self, access_token, historical_master_path=None, local_cache_path="data/historical/options"):
        self.access_token = access_token
        self.cache = {} # key -> DataFrame
        self.master_df = None
        self.expired_contract_cache = {} # (symbol, strike, type, expiry) -> key
        self.expiry_dates_cache = {} # underlying_key -> sorted list of dates
        self.local_cache_path = local_cache_path
        
        # Cache statistics
        self.cache_stats = {
            'hits': 0,
            'misses': 0,
            'api_calls': 0
        }
        
        if historical_master_path and os.path.exists(historical_master_path):
            print(f"Loading Historical Master Data from {historical_master_path}...")
            self.master_df = pd.read_csv(historical_master_path)
            # Ensure expiry is datetime
            if 'expiry' in self.master_df.columns:
                self.master_df['expiry'] = pd.to_datetime(self.master_df['expiry']).dt.date
            print(f"Loaded {len(self.master_df)} instruments.")
        else:
            print("⚠️ No Historical Master Data provided. Will use API for Expired Contract Lookup.")

    def _resolve_next_expiry(self, underlying_key, current_date):
        """Find the next valid expiry date from the API list."""
        if underlying_key not in self.expiry_dates_cache:
            print(f"  🔄 Fetching Expiry Dates for {underlying_key}...")
            dates = get_expired_expiry_dates(self.access_token, underlying_key)
            if dates:
                dates.sort()
                self.expiry_dates_cache[underlying_key] = dates
            else:
                self.expiry_dates_cache[underlying_key] = []
        
        valid_dates = self.expiry_dates_cache[underlying_key]
        target_date_str = str(current_date)
        
        # Find first date >= target_date
        for d in valid_dates:
            if d >= target_date_str:
                return d
                
        return None

    def get_expiry_for_date(self, current_date):
        """Legacy helper - kept for compatibility but not recommended."""
        d = pd.to_datetime(current_date)
        days_ahead = 3 - d.weekday() 
        if days_ahead < 0: days_ahead += 7
        return (d + timedelta(days=days_ahead)).date()

    def get_instrument_key_for_date(self, symbol, strike, option_type, date):
        """Find the correct instrument key for a specific date (handling expiry)"""
        # 1. Try Master DF (Fastest)
        if self.master_df is not None:
            # Logic: Find contract that expires ON or AFTER 'date', but closest to 'date'
            mask = (self.master_df['name'] == symbol) | (self.master_df['underlying_symbol'] == symbol)
            if strike: mask &= (self.master_df['strike_price'] == strike)
            if option_type: mask &= (self.master_df['instrument_type'] == option_type)
            
            filtered = self.master_df[mask].copy()
            if not filtered.empty:
                target_date = pd.to_datetime(date).date() if isinstance(date, (str, datetime)) else date
                filtered = filtered[filtered['expiry'] >= target_date]
                if not filtered.empty:
                    filtered = filtered.sort_values('expiry')
                    return filtered.iloc[0]['instrument_key']

        # 2. Try API Lookup (Expired)
        underlying_key = "NSE_INDEX|Nifty 50" if symbol == "NIFTY" else f"NSE_EQ|{symbol}"
        
        # Determine correct expiry dynamically from API
        expiry_str = self._resolve_next_expiry(underlying_key, date)
        if not expiry_str:
             print(f"  ❌ Could not resolve next expiry for {symbol} on {date}")
             return None
        
        # Check internal memory cache first
        cache_k = (symbol, strike, option_type, expiry_str)
        if cache_k in self.expired_contract_cache:
            return self.expired_contract_cache[cache_k]
        
        underlying_key = "NSE_INDEX|Nifty 50" if symbol == "NIFTY" else f"NSE_EQ|{symbol}" # Assumption
        
        print(f"  🔎 API Lookup: {symbol} {strike} {option_type} Exp: {expiry_str}")
        contracts = get_expired_option_contracts(self.access_token, underlying_key, expiry_str)
        
        if contracts:
            print(f"  🔎 Found {len(contracts)} contracts locally. Searching for Strike: {strike} ({option_type})")
            for c in contracts:
                # Robust Strike Match (handle float/int differences)
                c_strike = float(c.get('strike_price', 0))
                target_strike = float(strike)
                
                if (abs(c_strike - target_strike) < 0.1 and 
                    c.get('instrument_type') == option_type):
                    
                    key = c.get('instrument_key')
                    self.expired_contract_cache[cache_k] = key
                    print(f"  ✅ Resolved Key: {key}")
                    return key
        
        print(f"  ❌ Failed to find key for {symbol} {strike} {option_type} ({expiry_str})")
        if contracts:
             # Debug dump first 3
             print(f"    Available Sample: {[ (c['strike_price'], c['instrument_type']) for c in contracts[:3] ]}")
        return None
    
    def check_local_cache(self, instrument_key: str, date: str) -> pd.DataFrame:
        """
        Check if data exists in local Parquet cache.
        
        Args:
            instrument_key: Instrument key (e.g., "NSE_FO|52525|02-01-2025")
            date: Date in YYYY-MM-DD format
            
        Returns:
            DataFrame if cached, None otherwise
        """
        try:
            # Parse instrument key to extract strike and option type
            # Format: NSE_FO|<contract_id>|<expiry_date>
            # We need to match this with our cache structure: {strike}_{option_type}_{date}.parquet
            
            # For now, we'll use a simpler approach: check if the file exists
            # by parsing the instrument key components
            
            # Extract date components for path
            year_month = datetime.strptime(date, '%Y-%m-%d').strftime('%Y-%m')
            
            # Try to find matching file in cache directory
            cache_dir = os.path.join(self.local_cache_path, "NIFTY", year_month)
            
            if not os.path.exists(cache_dir):
                return None
            
            # Look for files matching this date and instrument
            # This is a simplified version - in production, you'd want to parse the instrument_key
            # to extract strike and option type for exact matching
            
            for filename in os.listdir(cache_dir):
                if filename.endswith(f"_{date}.parquet"):
                    # Found a potential match - load and return
                    file_path = os.path.join(cache_dir, filename)
                    df = pd.read_parquet(file_path)
                    
                    # Convert timestamp column to datetime index
                    if 'timestamp' in df.columns:
                        df['timestamp'] = pd.to_datetime(df['timestamp'])
                        df.set_index('timestamp', inplace=True)
                    
                    self.cache_stats['hits'] += 1
                    return df
            
            return None
            
        except Exception as e:
            # If any error, just return None and fall back to API
            return None

    def fetch_data(self, instrument_key, start_date, end_date, interval_unit='minute', interval_val=5):
        # Check local cache first (only for single-day requests)
        if start_date == end_date and not "NSE_INDEX" in instrument_key:
            cached_df = self.check_local_cache(instrument_key, start_date)
            if cached_df is not None:
                print(f"  💾 Using cached data for {instrument_key} on {start_date}")
                return cached_df
            else:
                self.cache_stats['misses'] += 1
        
        # Original fetch_data logic continues...
        # Normalize interval_unit (fix audit issue #1)
        if interval_unit == 'minutes': interval_unit = 'minute'
        if interval_unit == 'days': interval_unit = 'day'
        
        cache_key = f"{instrument_key}_{start_date}_{end_date}_{interval_unit}_{interval_val}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        # Route request based on instrument type
        if "NSE_INDEX" in instrument_key:
            # 1. Index Data -> Use Standard V2 API
            # Standard V2 API expects '1minute', '30minute', 'day' etc.
            
            # Standard V2 API supports ONLY: 1minute, 30minute, day, week, month
            # It DOES NOT support 5minute, 15minute, etc.
            
            # Construct V2 interval string
            if interval_unit == 'day':
                v2_interval = 'day'
            elif interval_unit == 'week':
                v2_interval = 'week'
            elif interval_unit == 'month':
                v2_interval = 'month'
            elif interval_val == 30:
                v2_interval = '30minute'
            else:
                # Default to 1minute for any other minute timeframe (best precision)
                v2_interval = "1minute"
            
            # Use direct request to avoid wrappers that might be broken
            url = f"https://api.upstox.com/v2/historical-candle/{instrument_key}/{v2_interval}/{end_date}/{start_date}"
            
            headers = {
                'Accept': 'application/json',
                'Authorization': f'Bearer {self.access_token}'
            }
            
            try:
                import requests
                response = requests.get(url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    if data.get('status') == 'success':
                        df_list = []
                        for candle in data.get('data', {}).get('candles', []):
                            df_list.append({
                                'timestamp': candle[0],
                                'open': candle[1],
                                'high': candle[2],
                                'low': candle[3],
                                'close': candle[4],
                                'volume': candle[5]
                            })
                        # Sort
                        df_list.sort(key=lambda x: x['timestamp'])
                    else:
                        print(f"  ❌ Index API Error: {data}")
                        df_list = None
                else:
                    print(f"  ❌ Index API HTTP Error {response.status_code}: {response.text}")
                    df_list = None
            except Exception as e:
                print(f"  ❌ Index Fetch Exception: {e}")
                df_list = None
                
        else:
            # 2. Option/Future Data -> Use Expired API
            # Expired API expects similar interval format '1minute'
            
            if interval_unit == "day": 
                exp_interval = "day"
            elif interval_unit == "week": 
                exp_interval = "week"
            elif interval_unit == "month": 
                exp_interval = "month"
            else:
                exp_interval = f"{interval_val}minute"
            
            try:
                df_list = get_expired_historical_candles(
                    self.access_token, instrument_key, exp_interval, start_date, end_date
                )
            except Exception as e:
                print(f"  ❌ Expired API Error for {instrument_key}: {e}")
                df_list = None

        if df_list:
            df = pd.DataFrame(df_list)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)
            self.cache[cache_key] = df
            return df
            
        return pd.DataFrame() # Empty

class BacktestEngine:
    """Base class for Event-Driven Backtesting"""
    
    def __init__(self, name, access_token, start_date, end_date, capital=100000.0, master_path=None):
        self.name = name
        self.start_date = start_date
        self.end_date = end_date
        self.capital = capital
        self.data_manager = BacktestDataManager(access_token, master_path)
        
        self.trades = []
        self.daily_pnl = []
        
    def run(self):
        """Override this to implement strategy logic"""
        raise NotImplementedError("Subclasses must implement run()")

    def record_trade(self, date, symbol, type, qty, entry_price, exit_price, pnl, reason_in, reason_out):
        self.trades.append({
            'date': date,
            'symbol': symbol,
            'type': type,
            'qty': qty,
            'entry': entry_price,
            'exit': exit_price,
            'pnl': pnl,
            'reason_in': reason_in,
            'reason_out': reason_out
        })
        
    def generate_report(self):
        df = pd.DataFrame(self.trades)
        if df.empty:
            print("No trades executed.")
            return
            
        total_pnl = df['pnl'].sum()
        win_trades = df[df['pnl'] > 0]
        loss_trades = df[df['pnl'] <= 0]
        
        print("\n" + "="*50)
        print(f"📊 BACKTEST REPORT: {self.name}")
        print("="*50)
        print(f"Dates       : {self.start_date} to {self.end_date}")
        print(f"Total PnL   : ₹{total_pnl:.2f}")
        print(f"Trades      : {len(df)}")
        print(f"Win Rate    : {len(win_trades)/len(df)*100:.1f}% ({len(win_trades)}W / {len(loss_trades)}L)")
        if not win_trades.empty:
            print(f"Avg Win     : ₹{win_trades['pnl'].mean():.2f}")
        if not loss_trades.empty:
            print(f"Avg Loss    : ₹{loss_trades['pnl'].mean():.2f}")
        print("="*50)
        
        # Save to CSV
        report_path = f"backtest_report_{self.name}_{datetime.now().strftime('%Y%m%d')}.csv"
        df.to_csv(report_path, index=False)
        print(f"📝 Detailed report saved to {report_path}")
        
        # Print cache statistics
        if hasattr(self.data_manager, 'cache_stats'):
            stats = self.data_manager.cache_stats
            total_requests = stats['hits'] + stats['misses']
            if total_requests > 0:
                cache_hit_rate = (stats['hits'] / total_requests) * 100
                print(f"\n💾 Cache Statistics:")
                print(f"  Cache Hits: {stats['hits']}")
                print(f"  Cache Misses: {stats['misses']}")
                print(f"  Hit Rate: {cache_hit_rate:.1f}%")
                print(f"  API Calls: {stats['api_calls']}")

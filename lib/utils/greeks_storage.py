import os
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Optional
from lib.utils.redis_client import redis_wrapper

class GreeksStorage:
    def __init__(self, base_path: str = "c:/algo/upstox/data/greeks_history"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_file_path(self, symbol: str, date: Optional[datetime.date] = None) -> Path:
        if date is None:
            date = datetime.now().date()
        return self.base_path / f"greeks_{symbol.upper()}_{date}.csv"

    def save_snapshot(self, symbol: str, expiry: str, df: pd.DataFrame):
        """
        Appends the current Greeks snapshot to a daily CSV file.
        df should have columns: [timestamp, strike, ce_delta, pe_delta, ce_gamma, pe_gamma, ce_vega, pe_vega, ce_theta, pe_theta, ce_oi, pe_oi, ce_gex, pe_gex, spot_price]
        """
        if df is None or df.empty:
            return

        file_path = self._get_file_path(symbol)
        
        # Add expiry column if missing to track multiple expiries in same file
        if 'expiry' not in df.columns:
            df['expiry'] = expiry

        # Ensure directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Append to CSV
        file_exists = file_path.exists()
        df.to_csv(file_path, mode='a', index=False, header=not file_exists)
        
        # Save to Redis List (cache for fast live reads)
        try:
            redis_key = f"greeks_chain:{symbol.upper()}:{expiry}:{datetime.now().date()}"
            redis_wrapper.push_json_list(redis_key, df.to_dict('records'), max_len=400)
        except Exception as e:
            print(f"Error saving to Redis: {e}")

    def get_strike_history(self, symbol: str, expiry: str, strike: float, date: Optional[datetime.date] = None) -> pd.DataFrame:
        """
        Retrieves historical Greeks for a specific strike from the CSV.
        """
        # Try Redis first
        search_date = date or datetime.now().date()
        redis_key = f"greeks_chain:{symbol.upper()}:{expiry}:{search_date}"
        try:
            cached_list = redis_wrapper.get_json_list(redis_key)
            if cached_list:
                all_records = []
                for snapshot_records in cached_list:
                    all_records.extend(snapshot_records)
                if all_records:
                    df = pd.DataFrame(all_records)
                    mask = (df['expiry'].astype(str) == str(expiry)) & (df['strike_price'].astype(float) == float(strike))
                    return df[mask].copy()
        except Exception as e:
            print(f"Redis read error for greeks_chain: {e}")
            
        # Fallback to CSV
        file_path = self._get_file_path(symbol, date)
        if not file_path.exists():
            return pd.DataFrame()

        try:
            df = pd.read_csv(file_path)
            # Filter by expiry and strike
            # Note: handle strike type matching (float/int)
            mask = (df['expiry'].astype(str) == str(expiry)) & (df['strike_price'].astype(float) == float(strike))
            return df[mask].copy()
        except Exception as e:
            print(f"Error reading Greeks history for {symbol}: {e}")
            return pd.DataFrame()

# Singleton instance
greeks_storage = GreeksStorage()

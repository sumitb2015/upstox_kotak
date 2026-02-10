import os
import sys

from lib.api.market_data import download_nse_market_data
import pandas as pd
from datetime import datetime
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

try:
    print("Downloading Data...")
    df = download_nse_market_data()
    
    # Filter FUT and NIFTY
    mask = (df['name'] == 'NIFTY') & (df['instrument_type'] == 'FUT')
    futs = df[mask].copy()
    
    # Convert expiry to date if possible for display
    # Assuming valid ms timestamp
    if not futs.empty and 'expiry' in futs.columns:
        futs['expiry_date'] = pd.to_datetime(futs['expiry'], unit='ms')
        futs = futs.sort_values('expiry')
        
        print(f"\n--- Found {len(futs)} NIFTY Futures ---")
        for i, row in futs.iterrows():
            print(f"Key: {row.get('instrument_key')} | Symbol: {row.get('tradingsymbol', row.get('symbol'))} | Expiry: {row['expiry_date']} | ExpiryMS: {row['expiry']}")
            
    else:
        print("❌ No NIFTY Futures found.")
        
except Exception as e:
    print(f"❌ Error: {e}")
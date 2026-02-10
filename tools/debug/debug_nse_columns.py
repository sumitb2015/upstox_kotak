import os
import sys

from lib.api.market_data import download_nse_market_data
import pandas as pd
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

try:
    print("Downloading Data...")
    df = download_nse_market_data()
    
    # Filter FUT
    futs = df[df['instrument_type'] == 'FUT']
    
    # Filter Name containing NIFTY
    if 'name' in futs.columns:
        nifty_futs = futs[futs['name'].astype(str).str.contains('NIFTY', case=False)]
        print(f"NIFTY Futures: {len(nifty_futs)}")
        if not nifty_futs.empty:
            print(nifty_futs.iloc[0].to_dict())
            print("Unique Names:", nifty_futs['name'].unique())
            
except Exception as e:
    print(f"❌ Error: {e}")
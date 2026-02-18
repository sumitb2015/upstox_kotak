# Debug script for Upstox Option Chain Data
import sys
import os
import pandas as pd
from datetime import datetime, timedelta

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.core.config import Config
from lib.api.market_data import _fetch_option_chain_data, _get_api_client
from lib.core.authentication import get_access_token
import upstox_client

# Get token
token = get_access_token()

# Params
symbol = "NSE_INDEX|Nifty 50"
expiry = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d") # Assuming close expiry

print(f"Fetching option chain for {symbol} expiring on {expiry or 'nearest'}")

# Fetch raw data
try:
    api_instance = upstox_client.OptionsApi(_get_api_client(token))
    
    # Need valid expiry. Fetch expiries first or guess?
    # Let's fetch expiries first
    from lib.api.option_chain import get_expiries
    expiries = get_expiries(token, symbol)
    if not expiries:
        print("No expiries found.")
        exit()
        
    expiry = expiries[0]
    print(f"Using expiry: {expiry}")
    
    print(f"Using expiry: {expiry}")
    
    # Test Prefetch Logic
    from lib.api.market_data import get_full_option_chain, PREV_OI_CACHE
    import time
    
    print("Calling get_full_option_chain first time...")
    df = get_full_option_chain(token, symbol, expiry)
    print(f"Dataframe size: {len(df)}")
    print(f"Initial Cache Size: {len(PREV_OI_CACHE)}")
    
    if not df.empty and 'prev_oi' in df.columns:
         print(f"Sample Prev OI (API): {df.iloc[0]['prev_oi']}")
    
    print("Waiting 10 seconds for background prefetch...")
    time.sleep(10)
    
    print(f"Cache Size after 10s: {len(PREV_OI_CACHE)}")
    
    print("Calling get_full_option_chain second time...")
    df2 = get_full_option_chain(token, symbol, expiry)
    
    if not df2.empty and 'prev_oi' in df2.columns:
         print(f"Sample Prev OI (Enriched): {df2.iloc[0]['prev_oi']}")
         
         # Identify a key in cache to verify
         if PREV_OI_CACHE:
             k = list(PREV_OI_CACHE.keys())[0]
             v = PREV_OI_CACHE[k]
             print(f"Cache Entry: {k} -> {v}")
             
             # Check if DF has used it
             row = df2[df2['instrument_key'] == k]
             if not row.empty:
                 print(f"DF uses: {row.iloc[0]['prev_oi']}")
    


except Exception as e:
    print(f"Error: {e}")


import sys
import os
import pandas as pd
from datetime import datetime, timedelta

# Path setup
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from lib.api.market_data import download_nse_market_data
from lib.utils.instrument_utils import get_option_instrument_key
from lib.core.authentication import check_existing_token
from lib.api.historical import get_historical_range

# Auth
if check_existing_token():
    with open("lib/core/accessToken.txt", "r") as f: token = f.read().strip()
else:
    print("No token")
    sys.exit(1)

nse_data = download_nse_market_data()

# Strikes to check
strikes = [25500, 25550]
target_date = "2026-01-16"

# Fetch logic
for strike in strikes:
    print(f"\nAnalyzing Strike: {strike}")
    ce_key = get_option_instrument_key("NIFTY", strike, "CE", nse_data)
    pe_key = get_option_instrument_key("NIFTY", strike, "PE", nse_data)
    
    # Fetch 1-Minute Data for that specific day
    # Range: 2026-01-16 to 2026-01-16 (Upstox Range might need same day or next day as end)
    # Using Range API
    ce_data = get_historical_range(token, ce_key, "1minute", target_date, target_date)
    pe_data = get_historical_range(token, pe_key, "1minute", target_date, target_date)
    
    if not ce_data or not pe_data:
        print("No Data Found")
        continue
        
    df_ce = pd.DataFrame(ce_data).set_index('timestamp')
    df_pe = pd.DataFrame(pe_data).set_index('timestamp')
    
    df = df_ce.join(df_pe, lsuffix='_ce', rsuffix='_pe', how='inner')
    
    df['cp_low'] = df['low_ce'] + df['low_pe']
    min_low = df['cp_low'].min()
    min_time = df['cp_low'].idxmin()
    
    print(f"Strike {strike} | 1-Min Low: {min_low:.2f} @ {min_time}")
    
    # Also check 30-min for comparison
    ce_data_30 = get_historical_range(token, ce_key, "30minute", target_date, target_date)
    pe_data_30 = get_historical_range(token, pe_key, "30minute", target_date, target_date)
    
    if ce_data_30 and pe_data_30:
        df_ce30 = pd.DataFrame(ce_data_30).set_index('timestamp')
        df_pe30 = pd.DataFrame(pe_data_30).set_index('timestamp')
        df30 = df_ce30.join(df_pe30, lsuffix='_ce', rsuffix='_pe', how='inner')
        df30['cp_low'] = df30['low_ce'] + df30['low_pe']
        min_low_30 = df30['cp_low'].min()
        print(f"Strike {strike} | 30-Min Low: {min_low_30:.2f}")


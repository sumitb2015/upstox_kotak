
import sys
import os
import pandas as pd
from datetime import datetime

# Path setup
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from lib.api.historical import get_historical_data
from lib.api.market_data import download_nse_market_data
from lib.utils.instrument_utils import get_option_instrument_key
from lib.core.authentication import check_existing_token

# Auth
if check_existing_token():
    with open("lib/core/accessToken.txt", "r") as f: token = f.read().strip()
else:
    print("No token")
    sys.exit(1)

nse_data = download_nse_market_data()

# Get Symbol for NIFTY ATM
# Just pick a known strike, e.g. 25550 CE
strike = 25550
key = get_option_instrument_key("NIFTY", strike, "CE", nse_data)
if not key:
    print("Key not found")
    sys.exit(1)

print(f"Fetching History for {key}...")
data = get_historical_data(token, key, "30minute", 10000) # 7 days approx

if not data:
    print("No Data Returned")
else:
    print(f"Returned {len(data)} candles")
    df = pd.DataFrame(data)
    print(df.head())
    print(df.tail())
    
    dates = sorted(list(set([ts.split('T')[0] for ts in df['timestamp']])))
    print(f"Unique Dates: {dates}")

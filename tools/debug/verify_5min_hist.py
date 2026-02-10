
import sys
import os
from datetime import datetime

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
strike = 25550
target_date = "2026-01-16"

print(f"\nFetching 5-minute History for {strike}...")
key = get_option_instrument_key("NIFTY", strike, "CE", nse_data)

# Try fetching 5minute
data = get_historical_range(token, key, "5minute", target_date, target_date)

if not data:
    print("❌ 5minute interval failed or no data.")
else:
    print(f"✅ Success! Returned {len(data)} candles.")
    print(data[0])

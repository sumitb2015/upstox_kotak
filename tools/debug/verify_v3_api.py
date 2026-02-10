
import sys
import os
from datetime import datetime

# Path setup
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from lib.api.market_data import download_nse_market_data
from lib.utils.instrument_utils import get_option_instrument_key
from lib.core.authentication import check_existing_token
from lib.api.historical import get_historical_data_v3

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

print(f"\nFetching V3 5-minute History for {strike}...")
key = get_option_instrument_key("NIFTY", strike, "CE", nse_data)

# Try fetching V3 5minute
# Note: V3 might use 'minute' (singular) as unit.
data = get_historical_data_v3(token, key, "minutes", 5, "2026-01-16", target_date)

if not data:
    print("❌ V3 5-minute fetch failed.")
else:
    print(f"✅ Success! Returned {len(data)} candles.")
    print(data[0])
    # Check if candles are 5-min apart
    if len(data) > 1:
        t1 = datetime.strptime(data[0]['timestamp'], "%Y-%m-%dT%H:%M:%S%z")
        t2 = datetime.strptime(data[1]['timestamp'], "%Y-%m-%dT%H:%M:%S%z")
        diff = (t2 - t1).total_seconds() / 60
        print(f"Interval Check: {diff} minutes")

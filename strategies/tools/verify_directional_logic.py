
import sys
import os

# Explicitly add project root to path
project_root = "c:\\algo\\upstox"
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from strategies.directional.dynamic_strangle_directional import DynamicStrangleStrategy


import pandas as pd
from datetime import datetime, timedelta

# Mock NSE Data DataFrame
# Create a valid future contract
current_time_ms = datetime.now().timestamp() * 1000
future_expiry_ms = (datetime.now() + timedelta(days=30)).timestamp() * 1000

nse_data = pd.DataFrame([
    {
        'underlying_symbol': 'NIFTY',
        'instrument_type': 'FUTIDX',
        'expiry': future_expiry_ms,
        'instrument_key': 'NSE_FO|NIFTY24JANFUT' # Mock key
    }
])

def get_access_token():
    try:
        with open("lib/core/accessToken.txt", "r") as f:
            return f.read().strip()
    except:
        return "TEST_TOKEN"

def verify():
    token = get_access_token()
    print(f"Using Token: {token[:10]}...")
    
    strategy = DynamicStrangleStrategy(token, nse_data, dry_run=True)
    
    # Manually trigger get_yesterdays_close
    print("\n--- Testing get_yesterdays_close (via Strategy) ---")
    close = strategy.get_yesterdays_close()
    print(f"Result: {close}")
    
    # Test fetch_historical_data directly to debug API "Invalid unit"
    from lib.api.market_data import fetch_historical_data
    from datetime import datetime, timedelta
    
    print("\n--- Debugging fetch_historical_data directly ---")
    token = get_access_token()
    # Use a likely valid key if possible, but mock key checks format
    key = "NSE_INDEX|Nifty 50" # Try with index first as it's stable
    end = datetime.now()
    start = end - timedelta(days=5)
    
    print(f"Attempt Correct: interval_type='days', interval=1")
    df = fetch_historical_data(token, key, "days", 1, start, end)
    print(f"Rows: {len(df)}")
    if not df.empty:
        print(f"Sample: {df.iloc[-1]['close']}")

if __name__ == "__main__":
    verify()

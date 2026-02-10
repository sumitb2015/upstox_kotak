import os
import sys

from lib.api.market_data import get_market_quotes
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
try:
    with open("lib/core/accessToken.txt", "r") as f: token = f.read().strip()
    
    # Index, Jan Fut, Feb Fut
    keys = ["NSE_INDEX|Nifty 50", "NSE_FO|49229", "NSE_FO|59182"]
    
    print(f"Fetching quotes for: {keys}")
    q = get_market_quotes(token, keys)
    
    print("\n--- QUOTE RESPONSE ---")
    if not q:
        print("❌ Empty Response")
    else:
        for k in keys:
            if k in q:
                print(f"✅ Data for {k}: {list(q[k].keys())}")
                if 'average_price' in q[k]:
                    print(f"   VWAP: {q[k]['average_price']}")
            else:
                print(f"❌ No data for {k}")

except Exception as e:
    print(f"❌ Error: {e}")
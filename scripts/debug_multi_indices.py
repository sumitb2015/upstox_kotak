
import sys
import os
import json

# Add project root
sys.path.append(os.path.abspath("c:/algo/upstox"))

from lib.api.market_data import get_market_quotes

def debug_indices():
    # 1. Get Token
    try:
        token_path = "c:/algo/upstox/lib/core/accessToken.txt"
        with open(token_path, "r") as f:
            access_token = f.read().strip()
    except Exception as e:
        print(f"❌ No token found: {e}")
        return

    indices = [
        "NSE_INDEX|Nifty 50", 
        "NSE_INDEX|Nifty Bank",
        "NSE_INDEX|Nifty IT",
        "NSE_INDEX|Nifty Metal",
        "NSE_INDEX|Nifty Fin Service"
    ]
    print(f"🔍 Fetching quotes for: {indices}")
    quotes = get_market_quotes(access_token, indices)
    
    if quotes:
        for k, v in quotes.items():
            print(f"✅ {k}: {v.get('last_price')} (Change: {v.get('net_change')})")
    else:
        print("❌ Could not fetch quotes.")

if __name__ == "__main__":
    debug_indices()

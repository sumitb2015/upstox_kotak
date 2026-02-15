
import sys
import os
import json

# Add project root
sys.path.append(os.path.abspath("c:/algo/upstox"))

from lib.api.market_data import get_market_quote_for_instrument

def debug_quote():
    # 1. Get Token
    try:
        token_path = "c:/algo/upstox/lib/core/accessToken.txt"
        with open(token_path, "r") as f:
            access_token = f.read().strip()
    except Exception as e:
        print(f"❌ No token found: {e}")
        return

    symbol = "NSE_INDEX|Nifty 50"
    print(f"🔍 Fetching quote for: {symbol}")
    quote = get_market_quote_for_instrument(access_token, symbol)
    
    if quote:
        print(json.dumps(quote, indent=2))
    else:
        print("❌ Could not fetch quote.")

if __name__ == "__main__":
    debug_quote()

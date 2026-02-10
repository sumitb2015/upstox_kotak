
import sys
import os
import json

# Add project root to path
root_dir = os.path.dirname(os.path.abspath(__file__))
if root_dir not in sys.path:
    sys.path.append(root_dir)

from lib.core.authentication import get_access_token
from lib.api.market_quotes import get_ltp_quote

def main():
    print("🔐 Authenticating...")
    token = get_access_token()
    if not token:
        print("❌ Auth failed")
        return

    # Keys from the log failure
    keys = ["NSE_FO|42532", "NSE_FO|42540"]
    
    print(f"🔎 Fetching LTP for keys: {keys}")
    
    for key in keys:
        print(f"\n--- Checking {key} ---")
        try:
            quote = get_ltp_quote(token, key)
            print(f"Raw Response:\n{json.dumps(quote, indent=2)}")
        except Exception as e:
            print(f"❌ Exception: {e}")

if __name__ == "__main__":
    main()

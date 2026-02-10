import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.core.authentication import get_access_token
from lib.api.market_data import get_market_quote_for_instrument

def check_quote():
    print("🔑 Getting Access Token...")
    token = get_access_token(auto_refresh=False)
    if not token:
        print("❌ Token not found")
        return

    key = "NSE_FO|59182"
    print(f"📡 Fetching REST Quote for {key}...")
    quote = get_market_quote_for_instrument(token, key)
    
    if quote:
        print(f"✅ Quote Received: {quote}")
        print(f"LTP: {quote.get('last_price')}")
    else:
        print("❌ No Quote Received (None)")

if __name__ == "__main__":
    check_quote()

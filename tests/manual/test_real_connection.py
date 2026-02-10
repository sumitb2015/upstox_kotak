import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from lib.core import authentication
from lib.api import market_data

def run_real_connection_test():
    print("🚀 Starting REAL API Connection Test...")
    print("---------------------------------------")

    # 1. Authentication
    print("1. Checking Access Token...")
    token = authentication.get_access_token()
    if not token:
        print("❌ No access token found in file or environment.")
        return
    print(f"✅ Token Found: {token[:10]}...")

    # 2. Fetch NIFTY Quote (Rest API)
    print("\n2. Fetching Live Quote for NIFTY 50...")
    # Instrument Key for NIFTY 50 Index: NSE_INDEX|Nifty 50
    nifty_key = "NSE_INDEX|Nifty 50"
    
    try:
        quote = market_data.get_market_quote_for_instrument(token, nifty_key)
        
        if quote:
            print(f"✅ Quote Received:")
            print(f"   Symbol: {quote.get('trading_symbol', 'Unknown')}")
            print(f"   LTP: {quote.get('last_price', 0.0)}")
            print(f"   OHLC: {quote.get('ohlc', {})}")
        else:
            print("❌ Failed to fetch quote (Empty response)")
            
    except Exception as e:
        print(f"❌ API Error: {e}")

    # 3. Market Status
    print("\n3. Checking Market Status...")
    status = market_data.get_market_status()
    print(f"✅ Status: {status}")

if __name__ == "__main__":
    run_real_connection_test()

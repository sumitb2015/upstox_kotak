import os
import sys

# Add the project root to sys.path to allow imports from api
sys.path.append(os.path.abspath(os.curdir))

from lib.api.market_quotes import get_ltp_quote

def test_fetch_vix():
    # Load access token
    token_file = "lib/core/accessToken.txt"
    if not os.path.exists(token_file):
        print("❌ Access token file not found.")
        return
        
    with open(token_file, "r") as f:
        access_token = f.read().strip()
        
    vix_symbol = "NSE_INDEX|India VIX"
    print(f"🔍 Attempting to fetch LTP for {vix_symbol}...")
    
    try:
        response = get_ltp_quote(access_token, vix_symbol)
        if response and response.get('status') == 'success':
            data = response.get('data', {})
            if vix_symbol in data:
                price = data[vix_symbol].get('last_price')
                print(f"✅ Success! India VIX LTP: {price}")
            else:
                # Upstox sometimes uses different keys for index results, check all keys
                keys = list(data.keys())
                if keys:
                    price = data[keys[0]].get('last_price')
                    print(f"✅ Success! Found India VIX under key '{keys[0]}'. LTP: {price}")
                else:
                    print("❌ Response received but data dictionary is empty.")
        else:
            print(f"❌ Failed to fetch VIX. Response: {response}")
    except Exception as e:
        print(f"❌ Error occurred: {str(e)}")

if __name__ == "__main__":
    test_fetch_vix()

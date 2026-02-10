import sys
import os
import requests
import json

# Add root to python path to import core modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from lib.core.authentication import get_access_token

def test_expired_contract():
    access_token = get_access_token()
    
    if not access_token:
        print("❌ No access token available.")
        return

    print(f"Token found (len={len(access_token)})")

    # User's code parameters
    # url = 'https://api.upstox.com/v2/expired-instruments/option/contract?instrument_key=NSE_INDEX%7CNifty%2050&expiry_date=2024-11-27'
    # Encoding | to %7C and space to %20 is good practice but requests params usually handle it. 
    # Let's try passing params via dict for cleaner code, or use the exact URL user provided.
    
    url = 'https://api.upstox.com/v2/expired-instruments/option/contract?instrument_key=NSE_INDEX%7CNifty%2050&expiry_date=2024-11-27'
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {access_token}',
        'Accept': 'application/json'
    }

    print(f"Requesting URL: {url}")
    
    try:
        response = requests.get(url, headers=headers)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            # Pretty print just a bit of data to verify
            print("Response Data Sample:")
            print(json.dumps(data, indent=2)[:500] + "...") 
        else:
            print(f"Error: {response.status_code} - {response.text}")
            
    except Exception as e:
        print(f"Exception occurred: {e}")

if __name__ == "__main__":
    test_expired_contract()

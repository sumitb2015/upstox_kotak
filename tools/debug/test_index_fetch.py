import sys
import os
import requests
import json
from datetime import datetime

# Add root directory to path
sys.path.insert(0, os.path.abspath("../.."))
sys.path.insert(0, os.path.abspath("."))

from lib.core.authentication import get_access_token

def make_request(method, url, headers=None):
    try:
        response = requests.request(method, url, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ Error {response.status_code}: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Exception: {e}")
        return None

def test_index_fetch():
    access_token = get_access_token()
    if not access_token:
        print("❌ No access token found")
        return

    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {access_token}'
    }

    instrument_key = "NSE_INDEX|Nifty 50"
    from_date = "2024-10-01"
    to_date = "2024-10-02" 
    
    print(f"Testing Index Fetch for {instrument_key}")
    
    # Variant 1: Expired API (Current approach - Failed)
    print("\n1. Testing Expired API:")
    url = f"https://api.upstox.com/v2/expired-instruments/historical-candle/{instrument_key}/1minute/{to_date}/{from_date}"
    # Note: Expired API usually takes from_date/to_date descending or ascending? Notebook said from/to. 
    # Url param names in notebook example: /{from_date}/{to_date}
    # But usually it's /to_date/from_date for V2.
    # Let's try matching notebook exact structure: 
    # Notebook: /expired-instruments/historical-candle/{instrument_key}/{interval}/{from_date}/{to_date}
    # Wait, in notebook call: url = .../{interval}/{from_date}/{to_date}
    # where from="2024-10-02", to="2024-10-01". This looks backwards?
    # Actually the param names are usually /to/from.
    
    url1 = f"https://api.upstox.com/v2/expired-instruments/historical-candle/{instrument_key}/1minute/{to_date}/{from_date}"
    res1 = make_request("GET", url1, headers)
    if res1: print("✅ Success!")
    
    # Variant 2: Standard V2 API
    print("\n2. Testing Standard V2 API:")
    url2 = f"https://api.upstox.com/v2/historical-candle/{instrument_key}/1minute/{to_date}/{from_date}"
    res2 = make_request("GET", url2, headers)
    if res2: print(f"✅ Success! Data points: {len(res2.get('data', {}).get('candles', []))}")

    # Variant 3: Standard V2 API with 'minute' (singular) - just in case
    print("\n3. Testing Standard V2 API (minute):")
    url3 = f"https://api.upstox.com/v2/historical-candle/{instrument_key}/minute/{to_date}/{from_date}"
    res3 = make_request("GET", url3, headers)
    
if __name__ == "__main__":
    test_index_fetch()

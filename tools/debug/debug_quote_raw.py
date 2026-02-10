import os
import sys

import requests
import json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

try:
    with open("lib/core/accessToken.txt", "r") as f: token = f.read().strip()
    
    keys = ["NSE_INDEX|Nifty 50", "NSE_FO|49229"]
    keys_str = ",".join(keys)
    
    url = "https://api.upstox.com/v2/market-quote/quotes"
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }
    params = {'instrument_key': keys_str}
    
    print(f"Requesting: {url}...")
    response = requests.get(url, headers=headers, params=params)
    
    print(f"Status: {response.status_code}")
    data = response.json()
    
    if 'data' in data:
        resp_keys = list(data['data'].keys())
        print(f"Returned Keys: {resp_keys}")
        
        for k in resp_keys:
            item = data['data'][k]
            print(f"\nKey: {k}")
            print(f"Price: {item.get('last_price')}")
            print(f"OHLC: {item.get('ohlc')}")
            # Check for average_price
            if 'average_price' in item:
                print(f"Has Average Price: {item['average_price']}")
            else:
                print("⚠️ Missing average_price")
    else:
        print("No 'data' field in response")
        print(data)

except Exception as e:
    print(f"❌ Error: {e}")
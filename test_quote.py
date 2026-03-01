import sys
import os
sys.path.append("/home/sumit/upstox_kotak")
from lib.core.authentication import get_access_token
from lib.api.market_data import get_market_quotes
import json

try:
    token = get_access_token()
    quote = get_market_quotes(token, ["NSE_INDEX|Nifty 50"])
    print("REST API Quote:", json.dumps(quote, indent=2))
except Exception as e:
    print(f"Error: {e}")

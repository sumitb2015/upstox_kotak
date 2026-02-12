
import os
import sys
from lib.core.authentication import get_access_token
from lib.api.market_data import get_market_quote_for_instrument, download_nse_market_data
from lib.utils.instrument_utils import get_future_instrument_key
import pandas as pd

token = get_access_token()
nse_data = download_nse_market_data()
f_key = get_future_instrument_key("NIFTY", nse_data)
print(f"Futures Key: {f_key}")

quote = get_market_quote_for_instrument(token, f_key)
print(f"Quote: {quote}")

quote_spot = get_market_quote_for_instrument(token, "NSE_INDEX|Nifty 50")
print(f"Spot: {quote_spot}")

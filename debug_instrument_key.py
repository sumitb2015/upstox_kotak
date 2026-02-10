import pandas as pd
from lib.utils.instrument_utils import get_option_instrument_key
from lib.api.market_data import download_nse_market_data

from lib.core.config import Config
Config.VERBOSE = True

# Simulate Data
print("Downloading Market Data...")
nse_data = download_nse_market_data()

# Test Case 2: PE Option (Simulating Numpy inputs)
import numpy as np
symbol = "NIFTY"
strike = np.int64(25800) # Simulate numpy int from DataFrame
opt_type = "PE"
expiry = np.str_("2026-02-12") # Simulate numpy string

print(f"Testing {symbol} {strike} ({type(strike)}) {opt_type} Expiry: {expiry} ({type(expiry)})")
# Debug: check available expiries for this strike
mask = (nse_data['underlying_symbol'] == symbol) & (nse_data['strike_price'] == strike) & (nse_data['instrument_type'] == opt_type)
subset = nse_data[mask]
if not subset.empty:
    print("Available Expiries (Raw):", subset['expiry'].unique())
    try:
        readable = pd.to_datetime(subset['expiry'], unit='ms').dt.strftime('%Y-%m-%d').unique()
        print("Available Expiries (Readable):", readable)
    except:
        print("Could not convert expiry to readable format")
else:
    print("No data found for this strike/type combo")

key = get_option_instrument_key(symbol, strike, opt_type, nse_data, expiry)
print(f"Result Key: {key}")

if key:
    print("✅ SUCCESS: Key found.")
else:
    print("❌ FAILURE: Key not found.")

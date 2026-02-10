
import sys
import os
sys.path.append(os.getcwd())
from lib.api.historical import get_intraday_data_v3
from datetime import datetime

with open("lib/core/accessToken.txt", "r") as f:
    token = f.read().strip()

key = "NSE_INDEX|Nifty 50"
print(f"Testing Intraday V3 for {key} at 1 min...")
data1 = get_intraday_data_v3(token, key, "minute", 1)
if data1:
    print(f"✅ Success! Got {len(data1)} candles for 1-min.")
    print(f"Latest candle: {data1[-1]}")
else:
    print(f"❌ Failed for 1-min.")

print(f"\nTesting Intraday V3 for {key} at 15 min...")
data15 = get_intraday_data_v3(token, key, "minute", 15)
if data15:
    print(f"✅ Success! Got {len(data15)} candles for 15-min.")
    print(f"Latest candle: {data15[-1]}")
else:
    print(f"❌ Failed for 15-min.")

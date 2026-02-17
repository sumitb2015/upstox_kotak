
import sys
import pandas
import numpy
import talib
import neo_api_client
import upstox_client
import yfinance
import pandas_ta as ta

def get_version(module):
    return getattr(module, "__version__", "Unknown")

print(f"Python: {sys.version}")
print(f"Pandas: {get_version(pandas)}")
print(f"Numpy: {get_version(numpy)}")
print(f"TA-Lib: {get_version(talib)}")
print(f"Neo API Client: {get_version(neo_api_client)}")
print(f"Upstox SDK: {get_version(upstox_client)}")
print(f"Yfinance: {get_version(yfinance)}")
print(f"Pandas TA: {get_version(ta)}")
print("\nEnvironment verification successful!")


import sys
import os
import pandas as pd

# Add project root
sys.path.append(os.path.abspath("c:/algo/upstox"))

import upstox_client
from lib.api.market_data import get_market_quote_for_instrument

def compare_oi():
    # 1. Get Token
    try:
        token_path = "c:/algo/upstox/lib/core/accessToken.txt"
        with open(token_path, "r") as f:
            access_token = f.read().strip()
    except Exception as e:
        print(f"❌ No token found: {e}")
        return

    # 2. Setup API
    configuration = upstox_client.Configuration()
    configuration.access_token = access_token
    api_instance = upstox_client.HistoryApi(upstox_client.ApiClient(configuration))
    
    instrument_key = "NSE_FO|48215" # NIFTY 25450 PE
    print(f"🔍 Checking instrument: {instrument_key}")
    
    # A. Get Quote OI
    quote = get_market_quote_for_instrument(access_token, instrument_key)
    if quote:
        quote_oi = quote.get('oi')
        print(f"📈 Quote Absolute OI: {quote_oi:,}")
    else:
        print("❌ Could not fetch market quote.")

    # B. Get Candle OI
    try:
        api_response = api_instance.get_intra_day_candle_data(instrument_key, "1minute", "2.0")
        if api_response.status == 'success' and api_response.data.candles:
            candles = api_response.data.candles
            df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
            latest_candle_oi = df['oi'].iloc[0] # Usually first in response is latest
            oldest_candle_oi = df['oi'].iloc[-1]
            
            print(f"🕯️ Latest Candle OI:  {latest_candle_oi:,}")
            print(f"🕯️ Oldest Candle OI:  {oldest_candle_oi:,}")
            print(f"🕯️ Difference:       {latest_candle_oi - oldest_candle_oi:,}")
            
            if quote_oi and latest_candle_oi:
                if latest_candle_oi == quote_oi:
                    print("✅ MATCH: Candle OI matches Market Quote.")
                else:
                    print("❌ DISCREPANCY: Candle OI does NOT match Market Quote.")
        else:
            print("❌ No candle data found.")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    compare_oi()


import os
import sys
import pandas as pd
from datetime import datetime, timedelta
import numpy as np

# Add root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.core.authentication import check_existing_token
from lib.api.historical import get_intraday_data_v3, get_historical_data_v3
from lib.utils.indicators import calculate_supertrend

def debug_nifty_st():
    with open("lib/core/accessToken.txt", "r") as f:
        access_token = f.read().strip()
    
    print("✅ Auth Token Loaded")

    token = "NSE_INDEX|Nifty 50"
    symbol = "NIFTY 50"
    interval = "3minute" # Config matches chart interval
    
    # FETCH MORE DATA (15 Days)
    to_date = datetime.now()
    from_date = to_date - timedelta(days=15) 
    
    print(f"📊 Fetching {interval} data for {symbol} (15 Days)...")
    hist_candles = get_historical_data_v3(
        access_token, token, "minute", 3, 
        from_date.strftime('%Y-%m-%d'), to_date.strftime('%Y-%m-%d')
    )
    intra_candles = get_intraday_data_v3(access_token, token, "minute", 3)
    
    hist_df = pd.DataFrame(hist_candles) if hist_candles else pd.DataFrame()
    intra_df = pd.DataFrame(intra_candles) if intra_candles else pd.DataFrame()
    
    if intra_df.empty and hist_df.empty:
        print("❌ No data found")
        return

    df = pd.concat([hist_df, intra_df]).drop_duplicates(subset=['timestamp']).sort_values('timestamp')
    df = df.reset_index(drop=True)
    
    print(f"📄 Loaded {len(df)} candles.")
    print(f"   Start: {df.iloc[0]['timestamp']}")
    print(f"   End:   {df.iloc[-1]['timestamp']}")
    print(f"   Last Close: {df.iloc[-1]['close']}")
    
    # Calculate 10, 2
    t1, v1 = calculate_supertrend(df, period=10, multiplier=2.0)
    print(f"\n🔹 Config (10, 2.0): Trend={t1}, Value={v1:.2f}")
    
    # Calculate 10, 3
    t2, v2 = calculate_supertrend(df, period=10, multiplier=3.0)
    print(f"🔹 Standard (10, 3.0): Trend={t2}, Value={v2:.2f}")

    # Manual Calc verification (10, 2)
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values
    period = 10
    multiplier = 2.0
    
    import talib
    atr = talib.ATR(high, low, close, timeperiod=period)
    basic_upper = (high + low) / 2 + multiplier * atr
    basic_lower = (high + low) / 2 - multiplier * atr
    
    final_upper = np.zeros(len(df))
    final_lower = np.zeros(len(df))
    trend = np.zeros(len(df))
    supertrend = np.zeros(len(df))
    
    # Initialize after warmup
    for i in range(period, len(df)):
        if np.isnan(basic_upper[i]): continue
            
        # First valid value initialization
        if i == period:
             final_upper[i] = basic_upper[i]
             final_lower[i] = basic_lower[i]
             trend[i] = 1 # Default
             supertrend[i] = final_lower[i]
             continue

        # Final Upper
        if basic_upper[i] < final_upper[i-1] or close[i-1] > final_upper[i-1]:
            final_upper[i] = basic_upper[i]
        else:
            final_upper[i] = final_upper[i-1]
            
        # Final Lower
        if basic_lower[i] > final_lower[i-1] or close[i-1] < final_lower[i-1]:
            final_lower[i] = basic_lower[i]
        else:
            final_lower[i] = final_lower[i-1]
            
        # Trend
        if close[i] > final_upper[i-1]:
            trend[i] = 1
        elif close[i] < final_lower[i-1]:
            trend[i] = -1
        else:
            trend[i] = trend[i-1]
            
        # ST Value
        if trend[i] == 1:
            supertrend[i] = final_lower[i]
        else:
            supertrend[i] = final_upper[i]
            
    # Print last 10 candles
    print("\n--- Last 10 Nifty Candles & ST (10, 2) ---")
    print(f"{'Time':<25} | {'Open':<8} | {'High':<8} | {'Low':<8} | {'Close':<8} | {'ST':<8} | {'Trend':<5}")
    print("-" * 90)
    for i in range(len(df)-10, len(df)):
        ts = df.iloc[i]['timestamp']
        o = df.iloc[i]['open']
        h = df.iloc[i]['high']
        l = df.iloc[i]['low']
        c = close[i]
        st = supertrend[i]
        tr = trend[i]
        print(f"{ts} | {o:<8.2f} | {h:<8.2f} | {l:<8.2f} | {c:<8.2f} | {st:<8.2f} | {tr}")

if __name__ == "__main__":
    debug_nifty_st()

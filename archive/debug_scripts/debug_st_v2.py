
import os
import sys
import pandas as pd
from datetime import datetime, timedelta

# Add root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.core.authentication import check_existing_token
from lib.api.historical import get_intraday_data_v3, get_historical_data_v3
from lib.utils.indicators import calculate_supertrend
from lib.api.market_data import get_option_chain_atm
from lib.utils.expiry_cache import get_expiry_for_strategy

def debug_supertrend_v2():
    with open("lib/core/accessToken.txt", "r") as f:
        access_token = f.read().strip()
    
    print("✅ Auth Token Loaded")

    # Use Hardcoded Token from previous run if possible to skip chain fetch, 
    # but let's just find it again to be safe.
    expiry = get_expiry_for_strategy(access_token, "current_week", "NIFTY")
    chain = get_option_chain_atm(access_token, "NSE_INDEX|Nifty 50", expiry)
    
    # Filter for 24950 PE
    target_strike = 24950.0
    target_type = "PE"
    
    row = chain[(chain['strike_price'] == target_strike) & (chain['instrument_type'] == target_type)]
    if row.empty:
        print("❌ Could not find 24950 PE")
        return
        
    token = row.iloc[0]['instrument_key']
    symbol = "NIFTY 24950 PE" # Placeholder
    print(f"🎯 Found Option: {symbol} ({token})")
    
    # FETCH MORE DATA (15 Days)
    to_date = datetime.now()
    from_date = to_date - timedelta(days=15) 
    
    print("📊 Fetching 5-minute data (15 Days)...")
    hist_candles = get_historical_data_v3(
        access_token, token, "minute", 5, 
        from_date.strftime('%Y-%m-%d'), to_date.strftime('%Y-%m-%d')
    )
    intra_candles = get_intraday_data_v3(access_token, token, "minute", 5)
    
    hist_df = pd.DataFrame(hist_candles) if hist_candles else pd.DataFrame()
    intra_df = pd.DataFrame(intra_candles) if intra_candles else pd.DataFrame()
    
    df = pd.concat([hist_df, intra_df]).drop_duplicates(subset=['timestamp']).sort_values('timestamp')
    df = df.reset_index(drop=True)
    
    print(f"📄 Loaded {len(df)} candles.")
    print(f"   Start: {df.iloc[0]['timestamp']}")
    print(f"   End:   {df.iloc[-1]['timestamp']}")
    print(f"   Last Close: {df.iloc[-1]['close']}")
    
    # Calculate 10, 2
    t1, v1 = calculate_supertrend(df, period=10, multiplier=2.0)
    print(f"\n🔹 Config (10, 2.0): Trend={t1} ({'Bullish' if t1==1 else 'Bearish'}), Value={v1:.2f}")

    # Check last few values to see trajectory
    print("\n--- Last 5 Candles Supertrend ---")
    # Quick re-calc to show series (inefficient but fine for debug)
    # We copy the verify logic from calculate_supertrend but expose the series
    import numpy as np
    import talib
    
    # Manual Calc to show series
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values
    period = 10
    multiplier = 2.0
    
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
            
    # Print last 10 candles to find the matching one
    print("\n--- Last 10 Candles Data & Supertrend ---")
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
        print(f"{ts} | {o:<8} | {h:<8} | {l:<8} | {c:<8} | {st:<8.2f} | {tr}")

if __name__ == "__main__":
    debug_supertrend_v2()


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

def debug_supertrend():
    # 1. Auth
    with open("lib/core/accessToken.txt", "r") as f:
        access_token = f.read().strip()
    
    print("✅ Auth Token Loaded")

    # 2. Get Target Option (NIFTY 03 FEB 24950 PE)
    # We need the instrument key. Let's fetch chain and find it.
    expiry = get_expiry_for_strategy(access_token, "current_week", "NIFTY")
    print(f"📅 Expiry: {expiry}")
    
    chain = get_option_chain_atm(access_token, "NSE_INDEX|Nifty 50", expiry)
    
    # Filter for 24950 PE
    target_strike = 24950.0
    target_type = "PE"
    
    row = chain[(chain['strike_price'] == target_strike) & (chain['instrument_type'] == target_type)]
    if row.empty:
        print("❌ Could not find 24950 PE in chain")
        return
        
    token = row.iloc[0]['instrument_key']
    symbol = "Unknown Symbol" # row.iloc[0]['trading_symbol']
    print(f"🎯 Found Option: {symbol} ({token})")
    
    # 3. Fetch Data (3minute)
    # Get 5 days history + today
    to_date = datetime.now()
    from_date = to_date - timedelta(days=5)
    
    print("📊 Fetching 3-minute data...")
    hist_candles = get_historical_data_v3(
        access_token, token, "minute", 3, 
        from_date.strftime('%Y-%m-%d'), to_date.strftime('%Y-%m-%d')
    )
    intra_candles = get_intraday_data_v3(access_token, token, "minute", 3)
    
    # Merge
    hist_df = pd.DataFrame(hist_candles) if hist_candles else pd.DataFrame()
    intra_df = pd.DataFrame(intra_candles) if intra_candles else pd.DataFrame()
    
    if intra_df.empty and hist_df.empty:
        print("❌ No data found")
        return

    df = pd.concat([hist_df, intra_df]).drop_duplicates(subset=['timestamp']).sort_values('timestamp')
    
    print(f"📄 Loaded {len(df)} candles. Last candle: {df.iloc[-1]['timestamp']}")
    print(f"   Last Close: {df.iloc[-1]['close']}")
    
    # 4. Calculate Supertrend Variants
    
    # Variant A: 10, 2 (Current Config)
    t1, v1 = calculate_supertrend(df, period=10, multiplier=2.0)
    print(f"\n🔹 Config (10, 2.0): Trend={t1}, Value={v1:.2f}")
    
    # Variant B: 10, 3 (Standard)
    t2, v2 = calculate_supertrend(df, period=10, multiplier=3.0)
    print(f"🔹 Standard (10, 3.0): Trend={t2}, Value={v2:.2f}")
    
    # Variant C: 7, 3 (Another common one)
    t3, v3 = calculate_supertrend(df, period=7, multiplier=3.0)
    print(f"🔹 Fast (7, 3.0): Trend={t3}, Value={v3:.2f}")

if __name__ == "__main__":
    debug_supertrend()

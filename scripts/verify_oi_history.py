import sys
import os
import datetime
import pandas as pd

# Add project root
sys.path.append(os.path.abspath("c:/algo/upstox"))

from lib.api.historical import get_intraday_data_v3
from lib.utils.instrument_utils import get_option_instrument_key
from lib.api.market_data import download_nse_market_data
from lib.core.config import Config


def verify_oi_history():
    print("🚀 Verifying Historical OI for Options (Re-Test)")
    
    # 1. Get Token
    try:
        token_path = "c:/algo/upstox/lib/core/accessToken.txt"
        with open(token_path, "r") as f:
            access_token = f.read().strip()
    except Exception as e:
        print(f"❌ No token found: {e}")
        return

    # 2. Get Master Data & Instrument Key
    print("📥 Loading Master Data...")
    nse_data = download_nse_market_data()
    
    # Find NIFTY Spot to get ATM
    # We'll just assume Nifty is around 25400 based on previous logs (Spot 25471)
    # Better: Get a known active strike from today's date
    # Let's try to find a highly active strike from the master data directly or just guess close to market
    target_strike = 25400 # Near ATM
    print(f"🔍 Finding Key for NIFTY {target_strike} CE (Current Week)...")
    
    # Get proper expiry
    from lib.utils.expiry_cache import get_expiry_for_strategy
    expiry = get_expiry_for_strategy(access_token, "current_week", "NIFTY")
    print(f"📅 Expiry: {expiry}")
    
    key = get_option_instrument_key("NIFTY", target_strike, "CE", nse_data, expiry_date=expiry)
    
    if not key:
        print("❌ Could not find instrument key")
        return

    print(f"✅ Found Key: {key}")

    # 3. Fetch Intraday Data (1 minute)
    print("📉 Fetching Intraday Data (1min)...")
    candles = get_intraday_data_v3(access_token, key, "minute", 1)
    
    if candles:
        print(f"✅ Fetched {len(candles)} candles")
        print("SAMPLE DATA (Last 5):")
        for item in candles[-5:]:
            timestamp = item.get('timestamp')
            close = item.get('close')
            vol = item.get('volume')
            oi = item.get('oi')
            print(f"Time: {timestamp}, Close: {close}, Vol: {vol}, OI: {oi}")
            
        non_zero_oi = [c for c in candles if c.get('oi', 0) > 0]
        if non_zero_oi:
            print(f"\n🎉 SUCCESS: Found {len(non_zero_oi)} candles with Non-Zero OI!")
            print(f"Example: {non_zero_oi[-1]}")
        else:
            print("\n❌ FAIL: All candles have 0 OI.")
    else:
        print("❌ No candles returned.")

    # 4. Check Daily Data
    print("\n📉 Fetching DAILY Data (1day)...")
    from lib.api.historical import get_historical_data_v3
    from datetime import datetime, timedelta
    
    to_date = datetime.now().strftime('%Y-%m-%d')
    from_date = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')
    
    # Using format 'day' and interval 1
    candles_day = get_historical_data_v3(access_token=access_token, instrument_key=key, interval_unit="days", interval_value=1, from_date=from_date, to_date=to_date)
    
    if candles_day:
        print(f"✅ Fetched {len(candles_day)} daily candles")
        for item in candles_day:
            timestamp = item.get('timestamp')
            oi = item.get('oi')
            print(f"Date: {timestamp}, OI: {oi}")

if __name__ == "__main__":
    verify_oi_history()

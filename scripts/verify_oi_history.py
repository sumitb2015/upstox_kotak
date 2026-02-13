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
    print("🚀 Verifying Historical OI for Options")
    
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
    
    # Get NIFTY Spot to guess a strike
    # Simplified: Just picking a likely active strike (e.g. 23000 CE/PE is probably far, let's try something closer to 25000)
    # Actually, let's just search for NIFTY 25000 CE
    target_strike = 25000
    
    print(f"🔍 Finding Key for NIFTY {target_strike} CE...")
    key = get_option_instrument_key("NIFTY", target_strike, "CE", nse_data)
    
    if not key:
        print("❌ Could not find instrument key")
        return

    print(f"✅ Found Key: {key}")

    # 3. Fetch Intraday Data (1 minute)
    print("📉 Fetching Intraday Data...")
    candles = get_intraday_data_v3(access_token, key, "minute", 1)
    
    if not candles:
        print("❌ No candles returned")
        return

    # 4. Check OI Column (Index 6)
    # Structure: [timestamp, open, high, low, close, volume, oi]
    df = pd.DataFrame(candles)
    # Rename columns for clarity if it matches standard
    # Standard: timestamp, open, high, low, close, volume, oi
    
    print(f"✅ Fetched {len(df)} candles")
    print("SAMPLE DATA (Last 5):")
    for item in candles[-5:]:
        # item is a dict: {'timestamp': '...', 'open': ...}
        timestamp = item.get('timestamp')
        close = item.get('close')
        volume = item.get('volume')
        oi = item.get('oi', 0)  # Safe access
        print(f"Time: {timestamp}, Close: {close}, Vol: {volume}, OI: {oi}")
        
    has_oi = any(c.get('oi', 0) > 0 for c in candles)
    
    if has_oi:
        print("\n✅ SUCCESS: OI Data is present and non-zero.")
    else:
        print("\n⚠️ WARNING: OI Data appears to be zero (might be illiquid or API limitation).")

if __name__ == "__main__":
    verify_oi_history()

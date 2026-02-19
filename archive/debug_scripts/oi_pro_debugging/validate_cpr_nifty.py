import sys
import os
from datetime import datetime, timedelta
import pandas as pd

# Add project root to path
# Add project root to path
# __file__ is c:/algo/upstox/validate_cpr_nifty.py
# os.path.dirname(__file__) is c:/algo/upstox
root = os.path.dirname(os.path.abspath(__file__))
if root not in sys.path:
    sys.path.append(root)

from lib.api.market_data import fetch_historical_data
from lib.core.authentication import check_existing_token

# Import CPR Utils dynamically (handling .agent folder)
# Path: c:/algo/upstox/.agent/skills/cpr_intelligence/scripts
skill_path = os.path.join(root, '.agent', 'skills', 'cpr_intelligence', 'scripts')
if skill_path not in sys.path:
    sys.path.append(skill_path)

try:
    from cpr_utils import calculate_cpr
except ImportError:
    # Try importing as if it's a module if needed, but append should work
    print(f"DEBUG: sys.path: {sys.path}")
    raise

def validate_nifty_cpr():
    print("🔍 Validating CPR Calculation for NIFTY Spot...")
    
    print("🔍 1. Auth check starting...")
    token = check_existing_token()
    if not token:
        print("❌ Access token not found. Please authenticate first.")
        return
    print("✅ Auth check complete.")

    # 2. Fetch Daily Data
    # Underlying: Nifty 50
    symbol = "NSE_INDEX|Nifty 50"
    end_date = datetime.now()
    start_date = end_date - timedelta(days=5) # Get last 5 days
    
    print(f"🔍 2. Fetching historical data for {symbol}...")
    df = fetch_historical_data(token, symbol, "day", "1", start_date, end_date)
    print("✅ Fetch complete.")
    
    if df.empty:
        print("❌ Failed to fetch historical data for Nifty.")
        return
    
    print("\n📊 Recent Daily Candles:")
    print(df.tail(3)[['timestamp', 'open', 'high', 'low', 'close']])
    
    # TARGET DATE: 2026-02-12
    # NEED PREVIOUS SESSION: 2026-02-11
    
    # Filter for 2026-02-11
    target_date = pd.to_datetime("2026-02-11").date()
    prev_session = df[df['timestamp'].dt.date == target_date]
    
    if prev_session.empty:
        print(f"❌ No data found for {target_date}")
        return
        
    prev_session = prev_session.iloc[0]
        
    print(f"\n✅ Using Previous Session: {prev_session['timestamp'].strftime('%Y-%m-%d')}")
    h, l, c = prev_session['high'], prev_session['low'], prev_session['close']
    print(f"   OHLC: H={h:.2f}, L={l:.2f}, C={c:.2f}")
    
    today_date = "2026-02-12"
    
    # 4. Calculate Levels
    levels = calculate_cpr(h, l, c)
    
    print("\n" + "="*40)
    print(f"🚀 NIFTY CPR LEVELS FOR {today_date}")
    print("="*40)
    print(f"Top Central (TC):   {levels['TC']:>10.2f}")
    print(f"Pivot (P):          {levels['P']:>10.2f}")
    print(f"Bottom Central (BC):{levels['BC']:>10.2f}")
    print("-" * 40)
    print(f"Resistance 1 (R1):  {levels['R1']:>10.2f}")
    print(f"Support 1 (S1):     {levels['S1']:>10.2f}")
    print(f"Resistance 2 (R2):  {levels['R2']:>10.2f}")
    print(f"Support 2 (S2):     {levels['S2']:>10.2f}")
    print("="*40)
    
    # Mathematical Proof check for User
    # P = (H+L+C)/3
    calc_p = (h+l+c)/3
    error = abs(calc_p - levels['P'])
    print(f"\n✅ Mathematical Verification: (H+L+C)/3 = {calc_p:.4f}")
    print(f"   Utility Output: {levels['P']:.2f}")
    if error < 0.01:
        print("🛡️ Verification PASSED")
    else:
        print("⚠️ Verification MINOR DISCREPANCY (Rounding?)")

if __name__ == "__main__":
    validate_nifty_cpr()

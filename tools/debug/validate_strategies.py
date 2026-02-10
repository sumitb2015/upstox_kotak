"""
Quick validation script to test strategy initialization with expiry library
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from lib.core.authentication import check_existing_token
from lib.api.market_data import download_nse_market_data

print("=" * 60)
print("Strategy Initialization Validation")
print("=" * 60)

# 1. Check token
print("\n1️⃣ Checking access token...")
if not check_existing_token():
    print("❌ No valid token found. Please authenticate first.")
    sys.exit(1)

with open("lib/core/accessToken.txt", "r") as f:
    token = f.read().strip()
print("✅ Access token loaded")

# 2. Load NSE data
print("\n2️⃣ Loading NSE market data...")
nse_data = download_nse_market_data()
print("✅ NSE data loaded")

# 3. Test Dynamic Strangle Strategy
print("\n3️⃣ Testing Dynamic Strangle Strategy...")
try:
    from strategies.hybrid.dynamic_strangle_strategy import DynamicStrangleStrategy
    
    strategy = DynamicStrangleStrategy(
        token, nse_data,
        lot_size=130,
        expiry_type="current_week",
        dry_run=True
    )
    
    # Test initialize (will fetch expiry)
    if strategy.initialize():
        print(f"✅ Dynamic Strangle initialized successfully")
        print(f"   Expiry Type: {strategy.expiry_type}")
        print(f"   Selected Expiry: {strategy.expiry_date}")
        print(f"   ATM Strike: {strategy.atm_strike}")
    else:
        print("❌ Dynamic Strangle initialization failed")
        
except Exception as e:
    print(f"❌ Dynamic Strangle error: {e}")
    import traceback
    traceback.print_exc()

# 4. Test VWAP Straddle Strategy
print("\n4️⃣ Testing VWAP Straddle Strategy...")
try:
    from strategies.hybrid.vwap_straddle_strategy import VWAPStraddleStrategy
    
    strategy = VWAPStraddleStrategy(
        token, nse_data,
        lot_size=65,
        expiry_type="monthly",
        dry_run=True
    )
    
    # Test initialize (will fetch expiry)
    if strategy.initialize():
        print(f"✅ VWAP Straddle initialized successfully")
        print(f"   Expiry Type: {strategy.expiry_type}")
        print(f"   Selected Expiry: {strategy.expiry_date}")
    else:
        print("❌ VWAP Straddle initialization failed")
        
except Exception as e:
    print(f"❌ VWAP Straddle error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("✅ All validation tests completed!")
print("=" * 60)

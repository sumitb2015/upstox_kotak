import sys
import os
import pandas as pd
# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from lib.api.expired_data import get_expired_expiry_dates, get_expired_option_contracts
from lib.core.authentication import get_access_token

def debug_data():
    try:
        print("Authenticating...")
        token = get_access_token()
        
        print("\n--- Checking Expiry Dates ---")
        dates = get_expired_expiry_dates(token, "NSE_INDEX|Nifty 50")
        dates.sort()
        print(f"Total Expiries Found: {len(dates)}")
        print("Last 10 Expiries:", dates[-10:])
        
        target_expiry = "2025-12-11"
        if target_expiry in dates:
            print(f"\n--- Checking Contracts for {target_expiry} ---")
            contracts = get_expired_option_contracts(token, "NSE_INDEX|Nifty 50", target_expiry)
            print(f"Contracts Found: {len(contracts)}")
            if contracts:
                print("First Contract:", contracts[0])
            else:
                print("❌ No contracts returned by API.")
        else:
            print(f"\n❌ Target expiry {target_expiry} NOT found in list.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_data()

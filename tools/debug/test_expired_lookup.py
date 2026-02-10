
import sys
import os

# Add root to sys path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from lib.api.expired_data import get_expired_option_contracts

def main():
    print("DEBUG: Investigating Specific Date Failure...")
    try:
        with open("lib/core/accessToken.txt", "r") as f: 
            token = f.read().strip()
    except:
        print("Token missing.")
        return

    underlying = "NSE_INDEX|Nifty 50"
    target_expiry = "2026-01-08" # As seen in logs
    
    print(f"Fetching contracts for {underlying} Expiry: {target_expiry}...")
    contracts = get_expired_option_contracts(token, underlying, target_expiry)
    
    if contracts:
        print(f"✅ Found {len(contracts)} contracts.")
        print(f"Sample: {contracts[0]}")
    else:
        print(f"❌ Failed (Empty List) for {target_expiry}")
        
    # Try another date that definitely worked in debug: 2024-10-03? 
    # Wait, if current date is 2026, 2024 is very old. 
    # Let's try to list *all* expiries again to see the distribution.
    from lib.api.expired_data import get_expired_expiry_dates
    dates = get_expired_expiry_dates(token, underlying)
    if dates:
        dates.sort()
        print(f"\nAll Expiries Range: {dates[0]} to {dates[-1]}")
        print(f"Total: {len(dates)}")
        print(f"Last 5: {dates[-5:]}")

if __name__ == "__main__":
    main()

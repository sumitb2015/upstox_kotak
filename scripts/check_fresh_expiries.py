
import sys
import os
import upstox_client
from datetime import datetime

# Add project root
sys.path.append(os.path.abspath("c:/algo/upstox"))

from lib.api.option_chain import get_expiries

def check_nifty_expiries():
    # 1. Get Token
    try:
        token_path = "c:/algo/upstox/lib/core/accessToken.txt"
        with open(token_path, "r") as f:
            access_token = f.read().strip()
    except Exception as e:
        print(f"❌ No token found: {e}")
        return

    # 2. Check Nifty
    nifty_key = "NSE_INDEX|Nifty 50"
    print(f"🔍 Fetching expiries for: {nifty_key}")
    expiries = get_expiries(access_token, nifty_key)
    
    if expiries:
        print(f"✅ Found {len(expiries)} expiries.")
        for e in expiries[:10]:
            dt = e if isinstance(e, datetime) else datetime.strptime(e, "%Y-%m-%d")
            print(f"  - {dt.strftime('%Y-%m-%d')} ({dt.strftime('%A')})")

    # 3. Check BankNifty
    bank_key = "NSE_INDEX|Nifty Bank"
    print(f"\n🔍 Fetching expiries for: {bank_key}")
    expiries_bank = get_expiries(access_token, bank_key)
    if expiries_bank:
        print(f"✅ Found {len(expiries_bank)} expiries.")
        for e in expiries_bank[:10]:
            dt = e if isinstance(e, datetime) else datetime.strptime(e, "%Y-%m-%d")
            print(f"  - {dt.strftime('%Y-%m-%d')} ({dt.strftime('%A')})")

if __name__ == "__main__":
    check_nifty_expiries()

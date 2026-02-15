
import sys
import os
import upstox_client
from datetime import datetime

# Add project root
sys.path.append(os.path.abspath("c:/algo/upstox"))

from lib.api.option_chain import get_expiries, get_option_chain

def check_chain_expiries():
    # 1. Get Token
    try:
        token_path = "c:/algo/upstox/lib/core/accessToken.txt"
        with open(token_path, "r") as f:
            access_token = f.read().strip()
    except Exception as e:
        print(f"❌ No token found: {e}")
        return

    # 2. Setup API
    configuration = upstox_client.Configuration()
    configuration.access_token = access_token
    api_instance = upstox_client.OptionsApi(upstox_client.ApiClient(configuration))
    
    underlying_key = "NSE_INDEX|Nifty 50"
    print(f"🔍 Fetching chain expiries for: {underlying_key}")
    
    try:
        # This endpoint just takes the underlying and returns the chain *including* expiries
        # Actually, in V3 get_put_call_option_chain requires an expiry_date.
        # But wait, there's another endpoint: get_option_contracts (which we tried).
        
        # Let's try to get the chain for what WE think is the expiry (Feb 17)
        # and what the BROKER thinks (Feb 19)
        
        for exp in ["2026-02-17", "2026-02-19"]:
            print(f"\n--- Checking expiry: {exp} ---")
            try:
                res = api_instance.get_put_call_option_chain(underlying_key, exp)
                if res.status == 'success':
                    print(f"✅ SUCCESS: Chain found for {exp}")
                    if res.data:
                        print(f"   Strikes count: {len(res.data)}")
                        # Print sample strike OI
                        sample = res.data[0]
                        print(f"   Sample Strike: {sample.strike_price}")
                else:
                    print(f"❌ FAILED: Status {res.status}")
            except Exception as e:
                print(f"❌ ERROR for {exp}: {e}")

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    check_chain_expiries()

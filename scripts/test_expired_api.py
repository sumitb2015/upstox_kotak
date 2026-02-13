
import sys
import os
import upstox_client
from upstox_client.rest import ApiException

# Add project root
sys.path.append(os.path.abspath("c:/algo/upstox"))

def test_expired_api():
    print("🚀 Final Verification: OI on Expired Contracts")
    
    # 1. Get Token
    try:
        token_path = "c:/algo/upstox/lib/core/accessToken.txt"
        with open(token_path, "r") as f:
            access_token = f.read().strip()
    except Exception as e:
        print(f"❌ No token found: {e}")
        return

    configuration = upstox_client.Configuration()
    configuration.access_token = access_token
    
    try:
        api_client = upstox_client.ApiClient(configuration)
        expired_api = upstox_client.ExpiredInstrumentApi(api_client)
        
        # 1. Get Confirm Expiries
        print("📥 Fetching expiries for Nifty...")
        exp_resp = expired_api.get_expiries("NSE_INDEX|Nifty 50")
        if not exp_resp.data:
            print("❌ No expiries found.")
            return
            
        # Use the most recent expired one from the list: '2026-02-10' (as per prev run)
        # Actually let's use the last one in the list.
        target_expiry = exp_resp.data[-1] 
        print(f"📅 Selected Expiry: {target_expiry}")

        # 2. Get Expired Contracts
        print(f"🔍 Fetching contracts for {target_expiry}...")
        contracts_resp = expired_api.get_expired_option_contracts(
            instrument_key="NSE_INDEX|Nifty 50", 
            expiry_date=target_expiry
        )
        
        if not contracts_resp.data:
            print(f"❌ No contracts found for {target_expiry}")
            return
            
        print(f"✅ Found {len(contracts_resp.data)} contracts.")
        # Pick an ATM/High Strike CE - 25000 CE is generally active
        target_contract = None
        for c in contracts_resp.data:
            # Check for 'CE' and some liquid strike if possible, else just pick first
            if getattr(c, 'option_type', '') == 'CE':
                target_contract = c
                break
        
        if not target_contract:
            target_contract = contracts_resp.data[0]
            
        print(f"🎯 Target Contract: {target_contract.trading_symbol} ({target_contract.instrument_key})")

        # 3. Fetch Historical Data (Specialized Expired Endpoint)
        print(f"📉 Fetching 1-minute data via get_expired_historical_candle_data for {target_expiry}...")
        
        try:
            # We assume similar arguments to get_historical_candle_data1
            # But specific to the expired API instance
            api_resp_candles = expired_api.get_expired_historical_candle_data(
                expired_instrument_key=target_contract.instrument_key,
                interval="1minute", 
                to_date=target_expiry,
                from_date=target_expiry
            )
            
            if not api_resp_candles.data or not api_resp_candles.data.candles:
                print("❌ No candles returned via specialized expired endpoint.")
                return
                
            print(f"✅ Fetched {len(api_resp_candles.data.candles)} candles.")
            
            # Check for OI
            # Schema: [timestamp, open, high, low, close, volume, oi]
            non_zero_oi_count = 0
            for candle in api_resp_candles.data.candles[:10]: # Check first 10
                 if len(candle) > 6 and candle[6] and candle[6] > 0:
                     non_zero_oi_count += 1
            
            print("\nSAMPLE DATA (First 5):")
            for item in api_resp_candles.data.candles[:5]:
                print(f"Time: {item[0]}, Close: {item[4]}, OI: {item[6] if len(item) > 6 else 'N/A'}")
                
            if non_zero_oi_count > 0:
                print(f"\n🎉 SUCCESS: Found {non_zero_oi_count} candles with Non-Zero OI on EXPIRED contract!")
            else:
                print("\n⚠️ CONCLUSION: specialized expired endpoint also returns 0 for OI.")

        except ApiException as e:
            print(f"❌ API Error for Expired Candles: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_expired_api()

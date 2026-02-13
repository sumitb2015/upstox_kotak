import sys
import os
import time
import pandas as pd
from datetime import datetime
import traceback

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from lib.core.config import Config
from lib.api.option_chain import get_option_chain_dataframe
from lib.utils.expiry_cache import get_expiry_for_strategy
from lib.utils.instrument_utils import get_atm_strike

# Configuration
SYMBOL = "NIFTY"  # Can be configurable
INTERVAL_SECONDS = 60
DATA_DIR = os.path.join(os.path.dirname(__file__), '../../data/iv_history')
os.makedirs(DATA_DIR, exist_ok=True)

def main():
    print(f"🚀 Starting IV Recorder for {SYMBOL}")
    
    # 1. Login (simulated via manual token or existing mechanism)
    # Ideally, we use the standard AccessTokenProvider if available, or load from config
    # For now, we assume Config handles loading env/token if set up, 
    # OR we rely on the user to have a valid token in secrets.yaml
    
    try:
        access_token = Config.get_access_token()
        if not access_token:
            print("❌ Access Token not found. Please ensure secrets.yaml is populated.")
            return
            
        print("✅ Access Token loaded.")
    except Exception as e:
        print(f"❌ Error loading access token: {e}")
        return

    while True:
        try:
            now = datetime.now()
            current_date = now.strftime('%Y-%m-%d')
            csv_file = os.path.join(DATA_DIR, f"iv_history_{current_date}.csv")
            
            # 2. Get Expiry
            expiry = get_expiry_for_strategy(access_token, SYMBOL, "current_week")
            if not expiry:
                print("⚠️ Could not fetch expiry. Retrying...")
                time.sleep(10)
                continue
                
            print(f"⏰ {now.strftime('%H:%M:%S')} | Fetching Chain for Expiry: {expiry}")
            
            # 3. Fetch Option Chain
            df_chain = get_option_chain_dataframe(access_token, f"NSE_INDEX|{SYMBOL} 50", expiry) 
            # Note: "NSE_INDEX|Nifty 50" might be needed instead of just SYMBOL
            # Let's verify the key. Standard is "NSE_INDEX|Nifty 50" for NIFTY
            
            if df_chain is None or df_chain.empty:
                print("⚠️ Option Chain empty or failed.");
                time.sleep(10)
                continue
                
            # 4. Identify ATM Strike
            # We can use underlying_spot_price from the first row if available
            spot_price = df_chain['spot_price'].iloc[0] if 'spot_price' in df_chain.columns else 0
            if spot_price == 0:
                 # Fallback/Retry
                 print("⚠️ Spot price 0.")
                 
            atm_strike = get_atm_strike(spot_price, 50) # Nifty strike diff
            
            # 5. Filter for Strikes (e.g., ATM +/- 5)
            # Simple range: [atm_strike - 250, atm_strike + 250]
            lower_bound = atm_strike - 250
            upper_bound = atm_strike + 250
            
            df_subset = df_chain[(df_chain['strike_price'] >= lower_bound) & (df_chain['strike_price'] <= upper_bound)].copy()
            
            if df_subset.empty:
                print("⚠️ No strikes found in range.")
                time.sleep(INTERVAL_SECONDS)
                continue
            
            # 6. Extract and Save Data
            # Columns: Timestamp, Spot, Strike, Expiry, CE_IV, CE_LTP, PE_IV, PE_LTP
            records = []
            timestamp_str = now.strftime('%Y-%m-%d %H:%M:%S')
            
            for _, row in df_subset.iterrows():
                records.append({
                    'timestamp': timestamp_str,
                    'symbol': SYMBOL,
                    'spot_price': spot_price,
                    'expiry': expiry,
                    'strike_price': row['strike_price'],
                    'ce_iv': row.get('ce_iv', 0),
                    'ce_ltp': row.get('ce_ltp', 0),
                    'pe_iv': row.get('pe_iv', 0),
                    'pe_ltp': row.get('pe_ltp', 0)
                })
                
            df_records = pd.DataFrame(records)
            
            # Append to CSV
            if not os.path.exists(csv_file):
                df_records.to_csv(csv_file, index=False)
            else:
                df_records.to_csv(csv_file, mode='a', header=False, index=False)
                
            print(f"✅ Recorded {len(records)} strikes. IV Range: {df_records['ce_iv'].min()} - {df_records['ce_iv'].max()}")
            
            # Wait for next cycle
            time.sleep(INTERVAL_SECONDS)
            
        except KeyboardInterrupt:
            print("\n🛑 Recording stopped by user.")
            break
        except Exception as e:
            print(f"❌ Error in loop: {e}")
            traceback.print_exc()
            time.sleep(10)

if __name__ == "__main__":
    main()

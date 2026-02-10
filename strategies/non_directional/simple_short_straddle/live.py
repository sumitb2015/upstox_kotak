"""
Main execution file for Short Straddle Strategy
Optimized to use all helper functions from the created modules
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from lib.core.authentication import check_existing_token, perform_authentication, save_access_token
from lib.api.market_data import download_nse_market_data
from lib.utils.market_validation import validate_market_conditions
from lib.core.strategy_config import display_strategy_configuration
from strategies.non_directional.legacy_straddle.live import run_short_straddle_strategy
from lib.core.config import Config


def main():
    """Main function to run the Short Straddle Strategy with full validation"""
    if Config.is_verbose():
        print("="*60)
        print("SHORT STRADDLE STRATEGY - OPTIMIZED EXECUTION")
        print("="*60)
    else:
        print("SHORT STRADDLE STRATEGY")
    
    # --- Configuration Toggles ---
    Config.set_verbose(False)         # Clean output mode
    Config.set_streaming_debug(True) # No raw WebSocket data
    # -----------------------------
    debug_streamer = None

    # Step 1: Authentication
    if Config.is_verbose():
        print("\n🔐 STEP 1: AUTHENTICATION")
    if check_existing_token():
        if Config.is_verbose():
            print("✅ Using existing access token")
    else:
        try:
            access_token = perform_authentication()
            save_access_token(access_token)
            if Config.is_verbose():
                print("✅ Authentication completed successfully!")
        except Exception as e:
            print(f"❌ Authentication failed: {e}")
            return
    
    # Step 2: Load access token and NSE data
    if Config.is_verbose():
        print("\n📊 STEP 2: DATA INITIALIZATION")
    try:
        with open("lib/core/accessToken.txt", "r") as file:
            access_token = file.read().strip()
        
        nse_data = download_nse_market_data()
        if nse_data is None:
            print("❌ Failed to download NSE data. Exiting...")
            return
        
        if Config.is_verbose():
            print(f"✅ NSE data loaded: {len(nse_data)} instruments")
            
    except FileNotFoundError:
        print("❌ Access token file not found. Cannot run strategy.")
        return
    except Exception as e:
        print(f"❌ Data initialization failed: {e}")
        return
    
    # Step 3: Market validation
    if Config.is_verbose():
        print("\n🔍 STEP 3: MARKET VALIDATION")
    validation_result = validate_market_conditions(access_token, nse_data)
    if not validation_result:
        print("❌ Market validation failed. Strategy cannot proceed.")
        return
    else:
        if not Config.is_verbose():
            print("✓ Auth | ✓ Data | ✓ Market")
        else:
            print("✅ Market validation completed. Proceeding with strategy...")
    
    # Step 4: Display configuration
    display_strategy_configuration()
    
    # Step 4b: (Optional) WebSocket Debugging
    if Config.is_streaming_debug():
        from lib.api.streaming import UpstoxStreamer
        if Config.is_verbose():
            print("\n📡 STEP 4b: STARTING WEBSOCKET DEBUG FEED")
        try:
            debug_streamer = UpstoxStreamer(access_token)
            debug_streamer.enable_debug(True)
            # Stream Nifty Index by default for debugging
            debug_streamer.connect_market_data(instrument_keys=["NSE_INDEX|Nifty 50"])
            
            # Wait for connection
            print("⏳ [DEBUG] Waiting for WebSocket connection...")
            for _ in range(5):
                import time
                time.sleep(1)
                if debug_streamer.market_data_connected:
                    print("✅ [DEBUG] WebSocket connection confirmed")
                    break
            else:
                 print("⚠️ [DEBUG] WebSocket not confirmed within 5s")
                 
            if Config.is_verbose():
                print("✅ WebSocket debug feed started in background")
        except Exception as e:
            print(f"⚠️  Failed to start debug feed: {e}")
    
    # Step 5: Execute Strategy
    if Config.is_verbose():
        print("\n🚀 Starting Short Straddle Strategy...")
        print("⏹️  Press Ctrl+C to stop the strategy early")
        print("📊 Monitor the console for real-time updates")
    else:
        print("\n🚀 Strategy Starting... (Ctrl+C to stop)")
    
    try:
        # Run the optimized short straddle strategy with clean output
        run_short_straddle_strategy(access_token, nse_data, verbose=False, streamer=debug_streamer, override_market_hours=False)
    except KeyboardInterrupt:
        print("\n⏹️  Strategy stopped by user.")
    except Exception as e:
        print(f"❌ Error running strategy: {e}")
    
    if Config.is_verbose():
        print("\n" + "="*50)
        print("✅ Strategy execution completed!")
    else:
        print("\n✅ Strategy Complete")

    if debug_streamer:
        try:
            print("Stopping debug streamer...")
            debug_streamer.disconnect_all()
        except:
            pass

    import sys
    import os
    print("Forcefully exiting process...")
    os._exit(0)

if __name__ == "__main__":
    main()

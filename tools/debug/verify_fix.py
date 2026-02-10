
import os
import time
import sys
from lib.api.streaming import UpstoxStreamer
from lib.core.authentication import check_existing_token

def test_market_stream():
    print("Starting Market Stream Verification Test...")
    
    # Check for access token
    if not os.path.exists("lib/core/accessToken.txt"):
        print("❌ Error: core/accessToken.txt not found. Please authenticate first.")
        return

    with open("lib/core/accessToken.txt", "r") as f:
        access_token = f.read().strip()

    try:
        streamer = UpstoxStreamer(access_token)
        streamer.enable_debug(True)
        
        # Subscribe to Nifty 50 Index
        print("Attempting to connect to market data stream...")
        streamer.connect_market_data(instrument_keys=["NSE_INDEX|Nifty 50"])
        
        # Wait for 15 seconds to see if handshake completes or errors out
        print("Waiting 15 seconds for connection and data...")
        time.sleep(15)
        
        if streamer.market_data_connected:
            print("✅ TEST PASSED: Market Data Stream is connected and active.")
        else:
            print("❌ TEST FAILED: Market Data Stream could not connect within 15 seconds.")
            
        streamer.disconnect_all()
        
    except Exception as e:
        print(f"❌ TEST ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Ensure project root is in path for imports
    sys.path.append(os.getcwd())
    test_market_stream()

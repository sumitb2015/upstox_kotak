import sys
import os
import time
import logging

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.core.authentication import get_access_token
from lib.api.streaming import UpstoxStreamer

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def on_market_data(data):
    print(f"📡 DATA RECEIVED: {data}")

def debug_ws():
    print("🔑 Getting Access Token...")
    token = get_access_token(auto_refresh=False)
    if not token:
        print("❌ Token not found")
        return

    print("🔌 Connecting to WebSocket...")
    streamer = UpstoxStreamer(token)
    
    # Test Instrument: NIFTY Futures
    keys = ["NSE_FO|59182"] 
    print(f"🎯 Subscribing to: {keys}")
    
    streamer.connect_market_data(keys, mode="ltpc", on_message=on_market_data)
    
    print("⏳ Waiting for data (20 seconds)...")
    try:
        for i in range(20):
            time.sleep(1)
            print(f"Tick {i+1}...")
    except KeyboardInterrupt:
        pass
        
    print("🛑 Disconnecting...")
    # streamer.disconnect_all() # Assuming method exists or handled in destructor

if __name__ == "__main__":
    debug_ws()

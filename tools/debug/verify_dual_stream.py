import os
import time
import logging
from dotenv import load_dotenv
import upstox_client
from lib.api.streaming import UpstoxStreamer
# from lib.core.authentication import authenticate_user

# Configure logging
logging.basicConfig(level=logging.INFO)

def main():
    print("🧪 Starting Dual Stream Verification...")
    
    # Authenticate via file
    load_dotenv("lib/core/.env")
    try:
        with open("lib/core/accessToken.txt", "r") as file:
            access_token = file.read().strip()
        print(f"✅ Loaded access token: {access_token[:10]}...")
    except Exception as e:
        print(f"❌ Failed to load access token: {e}")
        return

    streamer = UpstoxStreamer(access_token)
    streamer.enable_debug(True)
    
    # 1. Connect Market Data
    print("\n📡 Connecting Market Data...")
    streamer.connect_market_data(instrument_keys=["NSE_INDEX|Nifty 50"])
    
    # Wait a bit
    time.sleep(5)
    
    if streamer.market_data_connected:
        print("✅ Market Data Connected successfully")
    else:
        print("❌ Market Data Failed to connect")
        
    # 2. Connect Portfolio Data
    print("\n💼 Connecting Portfolio Data...")
    streamer.connect_portfolio(order_update=True, position_update=True)
    
    # Wait to see if Market Data stays alive
    print("⏳ Waiting 15 seconds to check stability of BOTH streams...")
    for i in range(15):
        if not streamer.market_data_connected:
            print(f"❌ Market Data DISCONNECTED at second {i+1}!")
        if not streamer.portfolio_connected:
             print(f"⚠️ Portfolio Data NOT connected at second {i+1}!")
        time.sleep(1)
        
    print("\n📝 Result Summary:")
    print(f"Market Data Connected: {streamer.market_data_connected}")
    print(f"Portfolio Data Connected: {streamer.portfolio_connected}")
    
    streamer.disconnect_all()
    print("👋 Verification done.")

if __name__ == "__main__":
    main()

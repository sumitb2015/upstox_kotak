"""
WebSocket Streaming Test

Tests the UpstoxAPI library's WebSocket functionality by streaming:
- NIFTY Futures live price
- NIFTY Index (spot) live price

This validates:
1. WebSocket connection stability
2. Data parsing and conversion
3. Callback mechanism
4. Real-time price updates
5. Error handling

Usage:
    python test_websocket_stream.py

Press Ctrl+C to stop.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import time
from datetime import datetime
from lib.utils.api_wrapper import UpstoxAPI
from lib.utils.instrument_utils import get_future_instrument_key
from lib.api.market_data import download_nse_market_data


class WebSocketTest:
    """Test WebSocket streaming functionality"""
    
    def __init__(self):
        self.futures_price = 0.0
        self.spot_price = 0.0
        self.futures_key = None
        self.spot_key = "NSE_INDEX|Nifty 50"
        
        # Additional stocks to test
        self.stocks = {
            "RELIANCE": {"key": None, "price": 0.0},
            "HDFCBANK": {"key": None, "price": 0.0},
            "ICICIBANK": {"key": None, "price": 0.0},
            "TCS": {"key": None, "price": 0.0},
            "INFY": {"key": None, "price": 0.0}
        }
        
        self.update_count = 0
        self.last_update_time = None
        self.api = None
        self.instrument_map = {} # Map key -> symbol name for fast lookup
        
    def on_market_data(self, data):
        """
        Callback for market data updates.
        
        Args:
            data: Single instrument data dict (flattened by UpstoxStreamer)
        """
        try:
            # Extract instrument key (injected by UpstoxStreamer)
            instrument_key = data.get('instrument_key') or data.get('instrument_token')
            
            if not instrument_key:
                return
            
            # Get last price
            last_price = data.get('last_price') or data.get('ltp')
            
            if last_price is None:
                return
            
            # Update prices based on key
            if instrument_key == self.futures_key:
                self.futures_price = last_price
            elif instrument_key == self.spot_key:
                self.spot_price = last_price
            elif instrument_key in self.instrument_map:
                symbol = self.instrument_map[instrument_key]
                if symbol in self.stocks:
                    self.stocks[symbol]["price"] = last_price
            
            self.update_count += 1
            self.last_update_time = datetime.now()
            
            # Print status every update
            if self.update_count > 0:
                self.print_status()
                
        except Exception as e:
            print(f"❌ Error in callback: {e}")
            import traceback
            traceback.print_exc()
    
    def print_status(self):
        """Print current status"""
        now = datetime.now().strftime("%H:%M:%S")
        
        # Clear screen for cleaner dashboard view (optional, might flicker)
        # print("\033[H\033[J", end="") 
        
        print(f"[{now}] #{self.update_count:<4d} | ", end="")
        
        # Print Futures/Spot
        fut_val = f"{self.futures_price:,.1f}" if self.futures_price > 0 else "N/A"
        print(f"NIFTY: {fut_val} | ", end="")
        
        # Print Stocks
        stock_strs = []
        for name, data in self.stocks.items():
            price = data["price"]
            p_str = f"{price:,.1f}" if price > 0 else "N/A"
            # Use short name
            short_name = name[:4]
            stock_strs.append(f"{short_name}: {p_str}")
            
        print(" | ".join(stock_strs))
    
    def run_test(self):
        """Run the WebSocket streaming test"""
        
        print("=" * 80)
        print("WebSocket Streaming Test - Multi-Stock Stress Test")
        print("=" * 80)
        print()
        
        # 1. Load access token
        print("🔐 Loading access token...")
        try:
            with open("lib/core/accessToken.txt", "r") as f:
                access_token = f.read().strip()
        except FileNotFoundError:
            print("❌ Token file not found: core/accessToken.txt")
            return False
        except Exception as e:
            print(f"❌ Failed to read token: {e}")
            return False
        print(f"✅ Token loaded (length: {len(access_token)})")
        print()
        
        # 2. Load NSE data
        print("📊 Loading NSE market data...")
        nse_data = download_nse_market_data()
        if nse_data is None or nse_data.empty:
            print("❌ Failed to load NSE data")
            return False
        print(f"✅ NSE data loaded: {len(nse_data)} instruments")
        print()
        
        # 3. Find Instruments
        print("🔍 Finding Instruments...")
        
        # Nifty Futures
        self.futures_key = get_future_instrument_key("NIFTY", nse_data)
        if self.futures_key:
             print(f"✅ Futures: {self.futures_key}")
        
        # Lookup Stocks (Equity)
        # Assuming NSE EQ logic: name match in trading_symbol or name
        for symbol in self.stocks:
            # Filter for NSE EQ and matching symbol
            # Note: Master data usually has 'tradingsymbol' column
            # EQ symbols usually like 'RELIANCE', 'TCS' with instrument_type 'EQ'
            
            # Simple lookup: exact match on trading_symbol where instrument_type is EQ/NSE_EQ
            # Or simplified: checking if 'trading_symbol' == symbol and exchange == 'NSE_EQ'
            
            # Let's try to find it in the dataframe
            # Columns: instrument_key, trading_symbol, name, etc.
            
            # Filter for NSE EQ instruments
            # Note: exchange is 'NSE', segment is 'NSE_EQ', instrument_type is 'EQ'
            try:
                # Look for exact match in trading_symbol with correct segment
                mask = (nse_data['trading_symbol'] == symbol) & (nse_data['segment'] == 'NSE_EQ')
                matches = nse_data[mask]
                
                if matches.empty:
                     # Fallback: Try searching by name if symbol match fails (unlikely for major stocks)
                     mask = (nse_data['name'].str.contains(symbol, case=False, na=False)) & (nse_data['segment'] == 'NSE_EQ')
                     matches = nse_data[mask]
                
                if not matches.empty:
                    # Prefer EQ instrument type if multiple found
                    eq_only = matches[matches['instrument_type'] == 'EQ']
                    if not eq_only.empty:
                        matches = eq_only
                        
                    key = matches.iloc[0]['instrument_key']
                    self.stocks[symbol]["key"] = key
                    self.instrument_map[key] = symbol
                    print(f"✅ {symbol}: {key}")
                else:
                    print(f"❌ {symbol}: Not Found")
                    
            except Exception as e:
                print(f"⚠️ Error finding {symbol}: {e}")
        
        print()
        
        # 4. Initialize API
        print("🚀 Initializing UpstoxAPI...")
        self.api = UpstoxAPI(access_token)
        print("✅ API initialized")
        print()
        
        # 5. Subscribe to WebSocket
        keys_to_subscribe = [self.spot_key]
        if self.futures_key:
            keys_to_subscribe.append(self.futures_key)
            
        for data in self.stocks.values():
            if data["key"]:
                keys_to_subscribe.append(data["key"])
        
        print(f"📡 Subscribing to {len(keys_to_subscribe)} instruments...")
        
        try:
            self.api.subscribe_live_data(
                instrument_keys=keys_to_subscribe,
                mode='ltpc',
                callback=self.on_market_data
            )
            
            print("✅ WebSocket connection established")
            print()
            print("-" * 80)
            print("Live Streaming Started (Press Ctrl+C to stop)")
            print("-" * 80)
            print()
            
            # Wait for updates
            start_time = time.time()
            timeout = 300  # 5 minutes max
            
            while time.time() - start_time < timeout:
                time.sleep(1)
            
            print("\n⏰ Test completed (timeout reached)")
            
        except KeyboardInterrupt:
            print("\n\n⚠️  Test stopped by user")
        except Exception as e:
            print(f"\n❌ Test failed: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            # Cleanup
            print("\n🔌 Disconnecting WebSocket...")
            if self.api:
                self.api.disconnect()
            print("✅ Disconnected")
            
        return True


def main():
    """Main entry point"""
    test = WebSocketTest()
    success = test.run_test()
    
    print()
    if success:
        print("🎉 WebSocket test completed successfully!")
        sys.exit(0)
    else:
        print("💥 WebSocket test failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()

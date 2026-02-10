#!/usr/bin/env python3
"""
Test script to verify strangle monitoring display works correctly
"""

import sys
import os
# Add parent directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategies.non_directional.legacy_straddle.live import ShortStraddleStrategy
from lib.core.authentication import get_access_token
from lib.api.market_data import download_nse_market_data
import time

def test_strangle_monitoring():
    """Test strangle monitoring display"""
    print("🧪 Testing Strangle Monitoring Display")
    print("=" * 50)
    
    try:
        # Get access token and NSE data
        access_token = get_access_token()
        if not access_token:
            print("❌ Failed to get access token")
            return
        
        nse_data = download_nse_market_data()
        if nse_data is None:
            print("❌ Failed to get NSE data")
            return
        
        # Initialize strategy
        strategy = ShortStraddleStrategy(
            access_token=access_token,
            nse_data=nse_data,
            underlying_symbol="NIFTY",
            lot_size=1,
            profit_target=3000,
            max_loss_limit=3000,
            ratio_threshold=0.6,
            straddle_width_threshold=0.25,
            max_deviation_points=200,
            enable_oi_analysis=True
        )
        
        # Simulate a strangle position for testing
        test_strangle_id = "TEST_STRANGLE_001"
        strategy.strangle_positions[test_strangle_id] = {
            'ce_strike': 25200,
            'pe_strike': 25050,
            'ce_instrument_key': 'NSE_FO|47755',  # Dummy key
            'pe_instrument_key': 'NSE_FO|47756',  # Dummy key
            'ce_entry_price': 45.50,
            'pe_entry_price': 35.25,
            'combined_entry_premium': 80.75,
            'timestamp': strategy.datetime.now()
        }
        
        print("✅ Test strangle position created")
        print(f"   CE Strike: 25200, Entry: ₹45.50")
        print(f"   PE Strike: 25050, Entry: ₹35.25")
        print(f"   Combined Entry Premium: ₹80.75")
        
        # Test the display method
        print("\n📊 Testing Position Display:")
        print("-" * 30)
        
        # Call display_current_positions which should now show strangle
        strategy.display_current_positions()
        
        print("\n✅ Strangle monitoring display test completed!")
        print("Expected output format:")
        print("[HH:MM:SS] STRANGLE TEST_STRANGLE_001: 25200 ₹XX.XX 25050 ₹XX.XX ₹80.75 ₹XX.XX P&L:₹XXX ₹XXXXX.X")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_strangle_monitoring()

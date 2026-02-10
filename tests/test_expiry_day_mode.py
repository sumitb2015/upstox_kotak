#!/usr/bin/env python3
"""
Test script to verify expiry day mode with dynamic ratio thresholds
"""

import sys
import os
# Add parent directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategies.non_directional.legacy_straddle.live import ShortStraddleStrategy
from lib.core.authentication import get_access_token
from lib.api.market_data import download_nse_market_data

def test_expiry_day_mode():
    """Test expiry day mode with different premium levels"""
    print("🧪 Testing Expiry Day Mode - Dynamic Ratio Thresholds")
    print("=" * 60)
    
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
        
        # Initialize strategy with expiry day mode
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
            enable_oi_analysis=True,
            expiry_day_mode=True  # Enable expiry day mode
        )
        
        print("\n📊 Testing Dynamic Ratio Thresholds:")
        print("-" * 40)
        
        # Test different premium scenarios
        test_cases = [
            {"ce_price": 15.0, "pe_price": 12.0, "description": "Very Low Premiums (< ₹30)"},
            {"ce_price": 25.0, "pe_price": 20.0, "description": "Low Premiums (< ₹50)"},
            {"ce_price": 35.0, "pe_price": 30.0, "description": "Medium Premiums (≥ ₹50)"},
            {"ce_price": 50.0, "pe_price": 45.0, "description": "Higher Premiums (≥ ₹50)"},
        ]
        
        for i, case in enumerate(test_cases, 1):
            ce_price = case["ce_price"]
            pe_price = case["pe_price"]
            description = case["description"]
            
            # Calculate ratio
            ratio = strategy.calculate_ratio(ce_price, pe_price)
            
            # Get dynamic threshold
            dynamic_threshold = strategy.get_dynamic_ratio_threshold(ce_price, pe_price)
            
            # Determine if ratio would trigger adjustment
            would_trigger = ratio < dynamic_threshold
            
            print(f"\n{i}. {description}")
            print(f"   CE: ₹{ce_price:.2f}, PE: ₹{pe_price:.2f}")
            print(f"   Combined Premium: ₹{ce_price + pe_price:.2f}")
            print(f"   Ratio: {ratio:.3f}")
            print(f"   Dynamic Threshold: {dynamic_threshold:.2f}")
            print(f"   Would Trigger Adjustment: {'❌ YES' if would_trigger else '✅ NO'}")
            
            if would_trigger:
                print(f"   🚨 Would square off losing side and adjust strike")
            else:
                print(f"   ✅ Position would remain stable")
        
        print(f"\n📈 Summary:")
        print(f"   Base Ratio Threshold: 0.60")
        print(f"   Expiry Day Mode: ENABLED")
        print(f"   Dynamic Thresholds:")
        print(f"     - Premiums < ₹30: 0.40 (very lenient)")
        print(f"     - Premiums < ₹50: 0.50 (lenient)")
        print(f"     - Premiums ≥ ₹50: 0.55 (slightly lenient)")
        
        print(f"\n✅ Expiry day mode test completed!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_expiry_day_mode()

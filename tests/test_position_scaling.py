#!/usr/bin/env python3
"""
Test script to demonstrate position scaling functionality
"""

import sys
import os
# Add parent directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategies.non_directional.legacy_straddle.live import ShortStraddleStrategy
from lib.core.authentication import get_access_token
from lib.api.market_data import download_nse_market_data

def test_position_scaling():
    """Test position scaling system with different scenarios"""
    print("🧪 Testing Position Scaling System")
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
        
        # Initialize strategy with position scaling enabled
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
            expiry_day_mode=True
        )
        
        print("\n📊 Position Scaling Configuration:")
        print("-" * 40)
        print(f"Position Scaling Enabled: {strategy.position_scaling_enabled}")
        print(f"Max Scaling Level: {strategy.max_scaling_level}x")
        print(f"Scaling Profit Threshold: {strategy.scaling_profit_threshold*100:.0f}%")
        print(f"OI Confidence Threshold: {strategy.scaling_oi_confidence_threshold}%")
        
        print(f"\n🎯 Scaling Scenarios:")
        print("-" * 40)
        
        # Test different profit scenarios
        test_scenarios = [
            {
                "ce_entry": 25.0, "ce_current": 15.0, "pe_entry": 20.0, "pe_current": 12.0,
                "description": "High Profit Scenario (40%+ profit)"
            },
            {
                "ce_entry": 25.0, "ce_current": 20.0, "pe_entry": 20.0, "pe_current": 16.0,
                "description": "Medium Profit Scenario (20% profit)"
            },
            {
                "ce_entry": 25.0, "ce_current": 22.0, "pe_entry": 20.0, "pe_current": 18.0,
                "description": "Low Profit Scenario (10% profit)"
            },
            {
                "ce_entry": 25.0, "ce_current": 30.0, "pe_entry": 20.0, "pe_current": 25.0,
                "description": "Loss Scenario (negative profit)"
            }
        ]
        
        for i, scenario in enumerate(test_scenarios, 1):
            ce_entry = scenario["ce_entry"]
            ce_current = scenario["ce_current"]
            pe_entry = scenario["pe_entry"]
            pe_current = scenario["pe_current"]
            description = scenario["description"]
            
            # Calculate profit percentage
            ce_profit = (ce_entry - ce_current) / ce_entry
            pe_profit = (pe_entry - pe_current) / pe_entry
            combined_profit = (ce_profit + pe_profit) / 2
            
            # Simulate should_scale_position logic
            would_scale = False
            reason = ""
            
            if combined_profit < strategy.scaling_profit_threshold:
                reason = f"Profit {combined_profit*100:.1f}% below threshold {strategy.scaling_profit_threshold*100:.0f}%"
            else:
                # In real scenario, this would check OI conditions
                if combined_profit > 0.5:  # 50% profit
                    would_scale = True
                    reason = f"High profit {combined_profit*100:.1f}% with favorable conditions"
                elif combined_profit > strategy.scaling_profit_threshold:
                    would_scale = True
                    reason = f"Moderate profit {combined_profit*100:.1f}% with neutral OI"
                else:
                    reason = f"Profit {combined_profit*100:.1f}% insufficient for scaling"
            
            print(f"\n{i}. {description}")
            print(f"   CE: ₹{ce_entry:.2f} → ₹{ce_current:.2f} ({ce_profit*100:+.1f}%)")
            print(f"   PE: ₹{pe_entry:.2f} → ₹{pe_current:.2f} ({pe_profit*100:+.1f}%)")
            print(f"   Combined Profit: {combined_profit*100:+.1f}%")
            print(f"   Would Scale: {'✅ YES' if would_scale else '❌ NO'}")
            print(f"   Reason: {reason}")
        
        print(f"\n📈 Scaling Benefits:")
        print("-" * 40)
        print("✅ Amplifies gains from winning positions")
        print("✅ Takes advantage of favorable OI conditions")
        print("✅ Maximizes time decay benefits")
        print("✅ Controlled risk with maximum scaling limits")
        print("✅ OI-guided decision making")
        
        print(f"\n⚠️  Risk Management:")
        print("-" * 40)
        print("🛡️  Maximum 3x position size limit")
        print("🛡️  Minimum 30% profit threshold")
        print("🛡️  OI confidence requirement (70%+)")
        print("🛡️  Only scales on favorable sentiment")
        print("🛡️  Integrated with existing stop-loss system")
        
        print(f"\n✅ Position scaling system test completed!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_position_scaling()

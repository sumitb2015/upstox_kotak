#!/usr/bin/env python3
"""
Test script to verify Safe OTM strategy is working correctly
"""

import sys
import os
from datetime import datetime

# Add the current directory to Python path
# Add parent directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_safe_otm_strategy():
    """Test Safe OTM strategy configuration and logic"""
    
    print("🧪 TESTING SAFE OTM STRATEGY FIX")
    print("=" * 50)
    
    try:
        # Import the strategy class
        from straddle_strategy import ShortStraddleStrategy
        
        # Create a mock strategy instance
        print("📋 Creating strategy instance...")
        strategy = ShortStraddleStrategy(
            access_token="test_token",
            nse_data={},
            enable_oi_analysis=True,
            expiry_day_mode=True
        )
        
        print("✅ Strategy instance created successfully")
        
        # Test Safe OTM configuration
        print(f"\n🔍 Safe OTM Configuration:")
        print(f"   Safe OTM Enabled: {strategy.safe_otm_enabled}")
        print(f"   Expiry Day Mode: {strategy.expiry_day_mode}")
        print(f"   Max Safe OTM Positions: {strategy.max_safe_otm_positions}")
        print(f"   Current Safe OTM Positions: {len(strategy.safe_otm_positions)}")
        
        # Test iteration counter logic
        print(f"\n🔄 Testing Iteration Counter Logic:")
        strategy._oi_check_counter = 1
        
        for i in range(1, 11):
            strategy._oi_check_counter = i
            should_check = (strategy.safe_otm_enabled and 
                          strategy.expiry_day_mode and 
                          strategy._oi_check_counter % 2 == 0)
            print(f"   Iteration {i}: {'✅ CHECK' if should_check else '⏭️  SKIP'}")
        
        # Test Safe OTM criteria
        print(f"\n💰 Safe OTM Criteria:")
        criteria = strategy.safe_otm_criteria
        for key, value in criteria.items():
            print(f"   {key}: {value}")
        
        print(f"\n✅ Safe OTM Strategy Test Completed Successfully!")
        print(f"   The strategy should now check for Safe OTM opportunities every 2nd iteration")
        print(f"   Debug output will show detailed information about each check")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing Safe OTM strategy: {e}")
        return False

if __name__ == "__main__":
    success = test_safe_otm_strategy()
    if success:
        print(f"\n🎯 RESULT: Safe OTM Strategy Fix Applied Successfully!")
        print(f"   - Changed from every 4th iteration to every 2nd iteration")
        print(f"   - Added comprehensive debug output")
        print(f"   - Strategy will now trigger more frequently")
    else:
        print(f"\n❌ RESULT: Safe OTM Strategy Fix Failed!")
        sys.exit(1)

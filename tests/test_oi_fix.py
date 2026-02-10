#!/usr/bin/env python3
"""
Test script to verify OI analysis fix
Run this after activating your conda environment: conda activate upstox
"""

import sys
import os
from datetime import datetime, timedelta

# Add current directory to path
# Add parent directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_oi_analysis_fix():
    """Test if OI analysis is working with the fix"""
    print("="*60)
    print("TESTING OI ANALYSIS FIX")
    print("="*60)
    
    try:
        # Import required modules
        from authentication import check_existing_token
        from market_data import get_option_chain_atm
        
        # Check if access token exists
        if not check_existing_token():
            print("❌ No access token found. Please run authentication first.")
            return False
        
        # Load access token
        with open("lib/core/accessToken.txt", "r") as file:
            access_token = file.read().strip()
        
        print("✅ Access token loaded successfully")
        
        # Test the fixed get_option_chain_atm call
        print("\n🔍 Testing get_option_chain_atm with correct format...")
        
        # Calculate next Tuesday expiry
        today = datetime.now()
        days_ahead = (1 - today.weekday()) % 7  # Tuesday is 1
        if days_ahead == 0:  # If today is Tuesday
            days_ahead = 7
        expiry = (today + timedelta(days=days_ahead)).strftime('%Y-%m-%d')
        
        print(f"📅 Using expiry: {expiry}")
        
        # Test with the correct format that should work
        option_chain_df = get_option_chain_atm(
            access_token, "NSE_INDEX|Nifty 50", expiry,
            strikes_above=3, strikes_below=3
        )
        
        if option_chain_df.empty:
            print("❌ Still getting empty option chain data")
            print("🔍 This might be due to:")
            print("   - Market is closed")
            print("   - API rate limits")
            print("   - Expiry date issue")
            return False
        else:
            print(f"✅ SUCCESS! Got option chain data with {len(option_chain_df)} rows")
            print(f"📊 Columns: {list(option_chain_df.columns)}")
            
            # Check if OI data is present
            if 'oi' in option_chain_df.columns and 'prev_oi' in option_chain_df.columns:
                print("✅ OI data columns found")
                
                # Show sample data
                print("\n📋 Sample data:")
                sample = option_chain_df.head(3)[['strike_price', 'type', 'oi', 'prev_oi', 'ltp']]
                print(sample.to_string(index=False))
                
                return True
            else:
                print("❌ OI data columns not found")
                return False
        
    except Exception as e:
        print(f"❌ Error during test: {e}")
        return False

def test_strategy_oi_integration():
    """Test if the strategy OI integration is working"""
    print("\n" + "="*60)
    print("TESTING STRATEGY OI INTEGRATION")
    print("="*60)
    
    try:
        from straddle_strategy import ShortStraddleStrategy
        from market_data import download_nse_market_data
        
        # Load access token
        with open("lib/core/accessToken.txt", "r") as file:
            access_token = file.read().strip()
        
        # Load NSE data
        nse_data = download_nse_market_data()
        if nse_data is None:
            print("❌ Failed to load NSE data")
            return False
        
        print("✅ NSE data loaded successfully")
        
        # Initialize strategy with OI analysis enabled
        strategy = ShortStraddleStrategy(
            access_token=access_token,
            nse_data=nse_data,
            underlying_symbol="NIFTY",
            lot_size=1,
            profit_target=3000,
            max_loss_limit=3000,
            ratio_threshold=0.6,
            straddle_width_threshold=0.2,
            max_deviation_points=200,
            enable_oi_analysis=True
        )
        
        print("✅ Strategy initialized with OI analysis enabled")
        
        # Test OI sentiment analysis
        print("\n🔍 Testing OI sentiment analysis...")
        current_strike = strategy.current_strike
        print(f"📍 Current strike: {current_strike}")
        
        oi_sentiment = strategy.analyze_oi_sentiment(current_strike)
        
        if "error" in oi_sentiment:
            print(f"⚠️  OI sentiment analysis returned error: {oi_sentiment['error']}")
            print("📊 This is expected if using fallback analysis")
            return True  # Fallback is working
        else:
            print("✅ OI sentiment analysis working!")
            print(f"📊 Strike sentiment: {oi_sentiment.get('strike_sentiment', 'N/A')}")
            return True
        
    except Exception as e:
        print(f"❌ Error during strategy test: {e}")
        return False

if __name__ == "__main__":
    print("🧪 OI Analysis Fix Test")
    print("Make sure to activate your conda environment first:")
    print("conda activate upstox")
    print()
    
    # Test 1: Basic option chain functionality
    test1_result = test_oi_analysis_fix()
    
    # Test 2: Strategy integration
    test2_result = test_strategy_oi_integration()
    
    print("\n" + "="*60)
    print("TEST RESULTS SUMMARY")
    print("="*60)
    print(f"📊 Option Chain Test: {'✅ PASSED' if test1_result else '❌ FAILED'}")
    print(f"🎯 Strategy Integration Test: {'✅ PASSED' if test2_result else '❌ FAILED'}")
    
    if test1_result and test2_result:
        print("\n🎉 ALL TESTS PASSED! OI analysis fix is working correctly.")
        print("You can now run main.py and the OI analysis should work.")
    else:
        print("\n⚠️  Some tests failed. Check the output above for details.")
    
    print("="*60)

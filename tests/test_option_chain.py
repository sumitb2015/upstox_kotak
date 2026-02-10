"""
Test script for get_filtered_option_chain function
Tests if option chain data is available
"""

import sys
import os
from datetime import datetime, timedelta

# Add parent directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.api.market_data import get_filtered_option_chain, get_option_chain_atm, _fetch_option_chain_data


def test_option_chain_functions():
    """Test option chain functions to see if data is available"""
    print("="*60)
    print("TESTING OPTION CHAIN FUNCTIONS")
    print("="*60)
    
    try:
        # Read access token
        with open("lib/core/accessToken.txt", "r") as file:
            access_token = file.read().strip()
        
        print("✅ Access token loaded successfully")
        
        # Test 1: Get current expiry date
        print("\n📅 TEST 1: Expiry Date Calculation")
        print("-" * 40)
        
        today = datetime.now()
        # Get next Tuesday (current NIFTY expiry)
        days_ahead = (1 - today.weekday()) % 7  # Tuesday is 1
        if days_ahead == 0:  # If today is Tuesday
            days_ahead = 7
        expiry = (today + timedelta(days=days_ahead)).strftime('%Y-%m-%d')
        
        print(f"Today: {today.strftime('%Y-%m-%d')} ({today.strftime('%A')})")
        print(f"Next Tuesday: {expiry}")
        
        # Test 2: Test different underlying keys
        print("\n🔑 TEST 2: Testing Different Underlying Keys")
        print("-" * 40)
        
        underlying_keys_to_test = [
            "NSE_INDEX|Nifty 50",
            "NSE_INDEX|NIFTY 50",
            "NSE_INDEX|Nifty",
            "NSE_INDEX|NIFTY"
        ]
        
        working_underlying = None
        working_expiry = None
        
        for underlying_key in underlying_keys_to_test:
            print(f"\nTesting: {underlying_key}")
            try:
                # Test _fetch_option_chain_data directly
                api_data, spot_price = _fetch_option_chain_data(access_token, underlying_key, expiry)
                
                if api_data is not None and spot_price is not None:
                    print(f"✅ SUCCESS: Found {len(api_data)} option chain entries")
                    print(f"   Spot Price: {spot_price}")
                    working_underlying = underlying_key
                    working_expiry = expiry
                    break
                else:
                    print(f"❌ No data returned for {underlying_key}")
            except Exception as e:
                print(f"❌ Exception: {e}")
        
        if not working_underlying:
            print("\n❌ No working underlying key found. Testing different expiry dates...")
            
            # Test different expiry dates with the first underlying key
            test_underlying = underlying_keys_to_test[0]
            current_week_tuesday = today + timedelta(days=days_ahead)
            expiry_dates_to_test = [
                current_week_tuesday.strftime('%Y-%m-%d'),
                (current_week_tuesday + timedelta(days=7)).strftime('%Y-%m-%d'),
                (current_week_tuesday + timedelta(days=14)).strftime('%Y-%m-%d'),
                (current_week_tuesday + timedelta(days=21)).strftime('%Y-%m-%d')
            ]
            
            for expiry_date in expiry_dates_to_test:
                print(f"\nTesting expiry: {expiry_date}")
                try:
                    api_data, spot_price = _fetch_option_chain_data(access_token, test_underlying, expiry_date)
                    
                    if api_data is not None and spot_price is not None:
                        print(f"✅ SUCCESS: Found {len(api_data)} option chain entries")
                        print(f"   Spot Price: {spot_price}")
                        working_underlying = test_underlying
                        working_expiry = expiry_date
                        break
                    else:
                        print(f"❌ No data returned for expiry {expiry_date}")
                except Exception as e:
                    print(f"❌ Exception: {e}")
        
        # Test 3: Test get_filtered_option_chain function
        print("\n📊 TEST 3: Testing get_filtered_option_chain Function")
        print("-" * 40)
        
        if working_underlying and working_expiry:
            print(f"Using working parameters:")
            print(f"  Underlying: {working_underlying}")
            print(f"  Expiry: {working_expiry}")
            
            try:
                # Test with different strike ranges
                test_cases = [
                    (5, 5, "5 strikes above and below"),
                    (10, 10, "10 strikes above and below"),
                    (3, 3, "3 strikes above and below")
                ]
                
                for strikes_above, strikes_below, description in test_cases:
                    print(f"\nTesting {description}:")
                    
                    option_chain_df = get_filtered_option_chain(
                        access_token, working_underlying, working_expiry,
                        strikes_above=strikes_above, strikes_below=strikes_below
                    )
                    
                    if not option_chain_df.empty:
                        print(f"✅ SUCCESS: Got {len(option_chain_df)} option chain entries")
                        print(f"   Columns: {list(option_chain_df.columns)}")
                        
                        # Show sample data
                        if len(option_chain_df) > 0:
                            print(f"   Sample data:")
                            sample = option_chain_df.head(3)
                            for _, row in sample.iterrows():
                                print(f"     Strike: {row.get('strike_price', 'N/A')}, "
                                      f"Type: {row.get('type', 'N/A')}, "
                                      f"OI: {row.get('oi', 'N/A')}, "
                                      f"Prev OI: {row.get('prev_oi', 'N/A')}")
                        
                        # Check if OI data is available
                        if 'oi' in option_chain_df.columns and 'prev_oi' in option_chain_df.columns:
                            print(f"✅ OI data is available")
                            oi_data = option_chain_df[['strike_price', 'type', 'oi', 'prev_oi']].dropna()
                            if not oi_data.empty:
                                print(f"   Valid OI entries: {len(oi_data)}")
                            else:
                                print(f"   ⚠️  No valid OI data found")
                        else:
                            print(f"❌ OI data columns not found")
                            print(f"   Available columns: {list(option_chain_df.columns)}")
                        
                        break  # Use the first successful test case
                    else:
                        print(f"❌ No data returned for {description}")
                        
            except Exception as e:
                print(f"❌ Exception in get_filtered_option_chain: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("❌ Cannot test get_filtered_option_chain - no working parameters found")
        
        # Test 4: Test get_option_chain_atm function
        print("\n📊 TEST 4: Testing get_option_chain_atm Function")
        print("-" * 40)
        
        if working_underlying and working_expiry:
            try:
                option_chain_atm_df = get_option_chain_atm(
                    access_token, working_underlying, working_expiry,
                    strikes_above=5, strikes_below=5
                )
                
                if not option_chain_atm_df.empty:
                    print(f"✅ SUCCESS: Got {len(option_chain_atm_df)} ATM option chain entries")
                    print(f"   Columns: {list(option_chain_atm_df.columns)}")
                    
                    # Show sample data
                    if len(option_chain_atm_df) > 0:
                        print(f"   Sample ATM data:")
                        sample = option_chain_atm_df.head(3)
                        for _, row in sample.iterrows():
                            print(f"     Strike: {row.get('strike_price', 'N/A')}, "
                                  f"Type: {row.get('type', 'N/A')}, "
                                  f"OI: {row.get('oi', 'N/A')}, "
                                  f"Prev OI: {row.get('prev_oi', 'N/A')}")
                else:
                    print(f"❌ No data returned from get_option_chain_atm")
                    
            except Exception as e:
                print(f"❌ Exception in get_option_chain_atm: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("❌ Cannot test get_option_chain_atm - no working parameters found")
        
        # Test 5: Market hours check
        print("\n⏰ TEST 5: Market Hours Check")
        print("-" * 40)
        
        current_time = datetime.now()
        market_open = current_time.replace(hour=9, minute=15, second=0, microsecond=0)
        market_close = current_time.replace(hour=15, minute=30, second=0, microsecond=0)
        
        print(f"Current time: {current_time.strftime('%H:%M:%S')}")
        print(f"Market open: {market_open.strftime('%H:%M:%S')}")
        print(f"Market close: {market_close.strftime('%H:%M:%S')}")
        
        if market_open <= current_time <= market_close:
            print("✅ Market is currently OPEN")
        else:
            print("⚠️  Market is currently CLOSED")
            print("   Option chain data might not be available during market hours")
        
        print("\n" + "="*60)
        print("OPTION CHAIN TESTING COMPLETED")
        print("="*60)
        
        # Summary
        if working_underlying and working_expiry:
            print(f"\n✅ SUMMARY: Option chain data is AVAILABLE")
            print(f"   Working Underlying: {working_underlying}")
            print(f"   Working Expiry: {working_expiry}")
            print(f"   You can use the full OI analysis features")
        else:
            print(f"\n❌ SUMMARY: Option chain data is NOT AVAILABLE")
            print(f"   Use the fallback OI analysis system")
            print(f"   The fallback provides basic but useful analysis")
        
    except FileNotFoundError:
        print("❌ Error: accessToken.txt file not found")
        print("Please run authentication first to generate the access token")
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("Option Chain Function Test Suite")
    print("This script tests the get_filtered_option_chain function")
    print()
    
    # Run tests
    test_option_chain_functions()
    
    print("\n💡 NEXT STEPS:")
    print("1. If option chain data is available, you can use full OI analysis")
    print("2. If option chain data is not available, use fallback analysis")
    print("3. The fallback system provides basic but useful analysis")
    print("4. Your strategy will automatically choose the best available option")

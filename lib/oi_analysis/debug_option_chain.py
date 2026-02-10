"""
Debug script for Option Chain API issues
Helps identify and fix "No option chain data found" errors
"""

import sys
import os
from datetime import datetime, timedelta

# Add current directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import upstox_client
from upstox_client.rest import ApiException


def debug_option_chain_api():
    """Debug option chain API issues"""
    print("="*60)
    print("DEBUGGING OPTION CHAIN API ISSUES")
    print("="*60)
    
    try:
        # Read access token
        with open("lib/core/accessToken.txt", "r") as file:
            access_token = file.read().strip()
        
        print("✅ Access token loaded successfully")
        
        # Test 1: Check API configuration
        print("\n🔧 TEST 1: API Configuration")
        print("-" * 40)
        
        configuration = upstox_client.Configuration()
        configuration.access_token = access_token
        print(f"✅ Configuration created with access token: {access_token[:10]}...")
        
        # Test 2: Check API instance creation
        print("\n🔧 TEST 2: API Instance Creation")
        print("-" * 40)
        
        api_instance = upstox_client.OptionsApi(upstox_client.ApiClient(configuration))
        print("✅ OptionsApi instance created successfully")
        
        # Test 3: Get current expiry date
        print("\n🔧 TEST 3: Expiry Date Calculation")
        print("-" * 40)
        
        today = datetime.now()
        # Get next Tuesday (current NIFTY expiry)
        days_ahead = (1 - today.weekday()) % 7  # Tuesday is 1
        if days_ahead == 0:  # If today is Tuesday
            days_ahead = 7
        expiry = (today + timedelta(days=days_ahead)).strftime('%Y-%m-%d')
        
        print(f"Today: {today.strftime('%Y-%m-%d')} ({today.strftime('%A')})")
        print(f"Next Tuesday: {expiry}")
        
        # Test 4: Test different underlying keys
        print("\n🔧 TEST 4: Testing Different Underlying Keys")
        print("-" * 40)
        
        underlying_keys_to_test = [
            "NSE_INDEX|Nifty 50",
            "NSE_INDEX|NIFTY 50",
            "NSE_INDEX|Nifty",
            "NSE_INDEX|NIFTY",
            "NSE_INDEX|Nifty50",
            "NSE_INDEX|NIFTY50"
        ]
        
        for underlying_key in underlying_keys_to_test:
            print(f"\nTesting: {underlying_key}")
            try:
                api_response = api_instance.get_put_call_option_chain(underlying_key, expiry)
                if api_response.data:
                    print(f"✅ SUCCESS: Found {len(api_response.data)} option chain entries")
                    spot_price = api_response.data[0].underlying_spot_price
                    print(f"   Spot Price: {spot_price}")
                    break
                else:
                    print(f"❌ No data returned for {underlying_key}")
            except ApiException as e:
                print(f"❌ API Exception: {e}")
                if hasattr(e, 'body'):
                    print(f"   Error body: {e.body}")
            except Exception as e:
                print(f"❌ General Exception: {e}")
        
        # Test 5: Test different expiry dates
        print("\n🔧 TEST 5: Testing Different Expiry Dates")
        print("-" * 40)
        
        # Test current week and next week
        current_week_tuesday = today + timedelta(days=days_ahead)
        next_week_tuesday = current_week_tuesday + timedelta(days=7)
        
        expiry_dates_to_test = [
            current_week_tuesday.strftime('%Y-%m-%d'),
            next_week_tuesday.strftime('%Y-%m-%d'),
            (current_week_tuesday + timedelta(days=14)).strftime('%Y-%m-%d'),
            (current_week_tuesday + timedelta(days=21)).strftime('%Y-%m-%d')
        ]
        
        working_underlying = "NSE_INDEX|Nifty 50"  # Use the working one from previous test
        
        for expiry_date in expiry_dates_to_test:
            print(f"\nTesting expiry: {expiry_date}")
            try:
                api_response = api_instance.get_put_call_option_chain(working_underlying, expiry_date)
                if api_response.data:
                    print(f"✅ SUCCESS: Found {len(api_response.data)} option chain entries")
                    spot_price = api_response.data[0].underlying_spot_price
                    print(f"   Spot Price: {spot_price}")
                    break
                else:
                    print(f"❌ No data returned for expiry {expiry_date}")
            except ApiException as e:
                print(f"❌ API Exception: {e}")
            except Exception as e:
                print(f"❌ General Exception: {e}")
        
        # Test 6: Check market hours
        print("\n🔧 TEST 6: Market Hours Check")
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
        
        # Test 7: Test with minimal parameters
        print("\n🔧 TEST 7: Minimal API Test")
        print("-" * 40)
        
        try:
            # Try to get any option chain data
            api_response = api_instance.get_put_call_option_chain("NSE_INDEX|Nifty 50", expiry)
            
            print(f"API Response Status: {api_response}")
            print(f"API Response Data: {api_response.data}")
            
            if api_response.data:
                print(f"✅ Data found: {len(api_response.data)} entries")
                # Show first entry structure
                first_entry = api_response.data[0]
                print(f"First entry structure:")
                print(f"  Strike Price: {first_entry.strike_price}")
                print(f"  Expiry: {first_entry.expiry}")
                print(f"  Underlying Key: {first_entry.underlying_key}")
                print(f"  Underlying Spot: {first_entry.underlying_spot_price}")
                print(f"  PCR: {first_entry.pcr}")
                
                if hasattr(first_entry, 'call_options'):
                    call = first_entry.call_options
                    print(f"  Call Options:")
                    print(f"    Instrument Key: {call.instrument_key}")
                    print(f"    LTP: {call.market_data.ltp}")
                    print(f"    OI: {call.market_data.oi}")
                    print(f"    Prev OI: {call.market_data.prev_oi}")
                
                if hasattr(first_entry, 'put_options'):
                    put = first_entry.put_options
                    print(f"  Put Options:")
                    print(f"    Instrument Key: {put.instrument_key}")
                    print(f"    LTP: {put.market_data.ltp}")
                    print(f"    OI: {put.market_data.oi}")
                    print(f"    Prev OI: {put.market_data.prev_oi}")
            else:
                print("❌ No data in API response")
                
        except ApiException as e:
            print(f"❌ API Exception: {e}")
            print(f"   Status: {e.status}")
            print(f"   Reason: {e.reason}")
            if hasattr(e, 'body'):
                print(f"   Body: {e.body}")
        except Exception as e:
            print(f"❌ General Exception: {e}")
            import traceback
            traceback.print_exc()
        
        print("\n" + "="*60)
        print("DEBUGGING COMPLETED")
        print("="*60)
        
    except FileNotFoundError:
        print("❌ Error: accessToken.txt file not found")
        print("Please run authentication first to generate the access token")
    except Exception as e:
        print(f"❌ Error during debugging: {e}")
        import traceback
        traceback.print_exc()


def test_alternative_approach():
    """Test alternative approach using market quotes API"""
    print("\n" + "="*60)
    print("TESTING ALTERNATIVE APPROACH - MARKET QUOTES API")
    print("="*60)
    
    try:
        from market_quotes import get_ltp_quote
        
        # Read access token
        with open("lib/core/accessToken.txt", "r") as file:
            access_token = file.read().strip()
        
        # Test NIFTY index
        print("Testing NIFTY index quote...")
        nifty_quote = get_ltp_quote(access_token, "NSE_INDEX|Nifty 50")
        
        if nifty_quote and nifty_quote.get('status') == 'success':
            print("✅ NIFTY index quote successful")
            data = nifty_quote.get('data', {})
            if data:
                key = list(data.keys())[0]
                spot_price = data[key].get('last_price', 0)
                print(f"   NIFTY Spot Price: {spot_price}")
        else:
            print("❌ NIFTY index quote failed")
            print(f"   Response: {nifty_quote}")
        
    except Exception as e:
        print(f"❌ Error in alternative approach: {e}")


if __name__ == "__main__":
    print("Option Chain API Debug Tool")
    print("This script helps identify and fix option chain API issues")
    print()
    
    # Run debugging
    debug_option_chain_api()
    
    # Test alternative approach
    test_alternative_approach()
    
    print("\n💡 TROUBLESHOOTING TIPS:")
    print("1. Check if market is open (9:15 AM - 3:30 PM)")
    print("2. Verify access token is valid and not expired")
    print("3. Check if the underlying key format is correct")
    print("4. Ensure expiry date is valid (typically Thursdays)")
    print("5. Check API rate limits and quotas")
    print("6. Verify network connectivity to Upstox API")

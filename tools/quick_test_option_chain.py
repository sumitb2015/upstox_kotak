"""
Quick test for get_filtered_option_chain function
Simple test to check if option chain data is available
"""

import sys
import os
from datetime import datetime, timedelta

# Add project root to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def quick_test():
    """Quick test of option chain functions"""
    print("🔍 Quick Test: get_filtered_option_chain")
    print("="*50)
    
    try:
        # Import functions
        from lib.api.market_data import get_filtered_option_chain, _fetch_option_chain_data
        
        # Read access token
        with open("lib/core/accessToken.txt", "r") as file:
            access_token = file.read().strip()
        
        print("✅ Access token loaded")
        
        # Get expiry date (next Tuesday)
        today = datetime.now()
        days_ahead = (1 - today.weekday()) % 7  # Tuesday is 1
        if days_ahead == 0:
            days_ahead = 7
        expiry = (today + timedelta(days=days_ahead)).strftime('%Y-%m-%d')
        
        print(f"📅 Testing expiry: {expiry}")
        
        # Test underlying keys
        underlying_keys = [
            "NSE_INDEX|Nifty 50",
            "NSE_INDEX|NIFTY 50",
            "NSE_INDEX|Nifty"
        ]
        
        for underlying in underlying_keys:
            print(f"\n🔑 Testing: {underlying}")
            
            try:
                # Test direct API call first
                api_data, spot_price = _fetch_option_chain_data(access_token, underlying, expiry)
                
                if api_data is not None and spot_price is not None:
                    print(f"✅ API Success: {len(api_data)} entries, Spot: {spot_price}")
                    
                    # Test get_filtered_option_chain
                    df = get_filtered_option_chain(access_token, underlying, expiry, 5, 5)
                    
                    if not df.empty:
                        print(f"✅ Filtered Success: {len(df)} entries")
                        print(f"   Columns: {list(df.columns)}")
                        
                        # Check OI data
                        if 'oi' in df.columns and 'prev_oi' in df.columns:
                            print(f"✅ OI data available")
                            oi_entries = df[['strike_price', 'type', 'oi', 'prev_oi']].dropna()
                            print(f"   Valid OI entries: {len(oi_entries)}")
                            
                            # Show sample
                            if len(oi_entries) > 0:
                                print(f"   Sample:")
                                for _, row in oi_entries.head(2).iterrows():
                                    print(f"     {row['strike_price']} {row['type']}: OI={row['oi']}, Prev={row['prev_oi']}")
                        else:
                            print(f"❌ OI columns missing")
                        
                        print(f"\n🎯 RESULT: Option chain data is AVAILABLE!")
                        print(f"   You can use full OI analysis features")
                        return True
                    else:
                        print(f"❌ Filtered function returned empty DataFrame")
                else:
                    print(f"❌ API returned no data")
                    
            except Exception as e:
                print(f"❌ Error: {e}")
        
        print(f"\n❌ RESULT: Option chain data is NOT AVAILABLE")
        print(f"   Use fallback OI analysis system")
        return False
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    success = quick_test()
    
    if success:
        print(f"\n💡 Your OI analysis will use full option chain data")
    else:
        print(f"\n💡 Your OI analysis will use fallback system")
        print(f"   The fallback still provides useful analysis for option selling")

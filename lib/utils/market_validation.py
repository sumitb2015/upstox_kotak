"""
Market validation utilities for checking market conditions before strategy execution
"""

from datetime import datetime
from lib.api.market_quotes import get_ltp_quote
from lib.utils.instrument_utils import get_option_instrument_key


def validate_market_conditions(access_token, nse_data):
    """Validate market conditions before starting strategy"""
    print("\n" + "="*50)
    print("MARKET CONDITIONS VALIDATION")
    print("="*50)
    
    try:
        # Check if market is open (basic check)
        current_time = datetime.now()
        if current_time.hour < 9 or current_time.hour > 15:
            print("⚠️  WARNING: Market may be closed (9:15 AM - 3:30 PM)")
        
        # Get NIFTY index instrument key and fetch spot price
        print("Fetching NIFTY index instrument key...")
        nifty_index_key = "NSE_INDEX|Nifty 50"
        print(f"Using NIFTY index key: {nifty_index_key}")
        
        print("Fetching NIFTY spot price...")
        nifty_spot = get_ltp_quote(access_token, nifty_index_key)
        print(f"NIFTY spot response: {nifty_spot}")
        
        if nifty_spot and nifty_spot.get('status') == 'success':
            # Extract price from the nested response structure
            nifty_data = nifty_spot.get('data', {})
            if nifty_data:
                nifty_key = list(nifty_data.keys())[0]
                spot_price = nifty_data[nifty_key].get('last_price', 0)
                
                if spot_price > 0:
                    print(f"📊 Current NIFTY Spot: ₹{spot_price}")
                    
                    # Calculate ATM strike
                    atm_strike = round(spot_price / 50) * 50
                    print(f"🎯 Calculated ATM Strike: {atm_strike}")
                else:
                    print("⚠️  NIFTY spot price is 0")
                    atm_strike = 25000  # Default strike
                    print(f"🎯 Using Default ATM Strike: {atm_strike}")
            else:
                print("⚠️  No data in NIFTY response")
                atm_strike = 25000  # Default strike
                print(f"🎯 Using Default ATM Strike: {atm_strike}")
        else:
            print("⚠️  Could not fetch valid NIFTY spot price")
            print("This might be because:")
            print("   - Market is closed")
            print("   - API connection issue")
            print("   - Invalid instrument key")
            print("Using default ATM strike for validation...")
            atm_strike = 25000  # Default strike for validation
            print(f"🎯 Using Default ATM Strike: {atm_strike}")
        
        # Get instrument keys for ATM options using the simpler approach
        print("Fetching instrument keys for ATM options...")
        
        # Use the helper function that extends get_instrument_key logic
        ce_instrument_key = get_option_instrument_key("NIFTY", atm_strike, "CE", nse_data)
        pe_instrument_key = get_option_instrument_key("NIFTY", atm_strike, "PE", nse_data)
        
        if ce_instrument_key and pe_instrument_key:
            print(f"CE Instrument Key: {ce_instrument_key}")
            print(f"PE Instrument Key: {pe_instrument_key}")
            
            # Get current prices for both options using LTP
            print("Fetching option prices...")
            ce_price_data = get_ltp_quote(access_token, ce_instrument_key)
            pe_price_data = get_ltp_quote(access_token, pe_instrument_key)
            
            print(f"CE Price Response: {ce_price_data}")
            print(f"PE Price Response: {pe_price_data}")
            
            if ce_price_data and pe_price_data:
                # Extract prices from the nested response structure
                ce_data = ce_price_data.get('data', {})
                pe_data = pe_price_data.get('data', {})
                
                # Get the first (and only) entry from the data dictionary
                ce_price = 0
                pe_price = 0
                
                if ce_data:
                    ce_key = list(ce_data.keys())[0]
                    ce_price = ce_data[ce_key].get('last_price', 0)
                
                if pe_data:
                    pe_key = list(pe_data.keys())[0]
                    pe_price = pe_data[pe_key].get('last_price', 0)
                
                print(f"📈 ATM CE Price: ₹{ce_price}")
                print(f"📉 ATM PE Price: ₹{pe_price}")
                
                # Calculate initial ratio
                if ce_price > 0 and pe_price > 0:
                    ratio = min(ce_price, pe_price) / max(ce_price, pe_price)
                    print(f"⚖️  Initial Ratio: {ratio:.3f}")
                    
                    if ratio < 0.8:
                        print("⚠️  WARNING: Initial ratio is below 0.8 threshold!")
                        print("📋 Strategy will wait for better market conditions before entering...")
                        # Don't return False - let the strategy handle the waiting logic
                else:
                    print("❌ Could not fetch valid option prices")
                    return False
            else:
                print("❌ Could not fetch option prices")
                return False
        else:
            print("❌ Could not get instrument keys for ATM options")
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ Market validation failed: {e}")
        return False

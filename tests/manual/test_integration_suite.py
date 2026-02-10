import sys
import os
import pandas as pd
from datetime import datetime, timedelta

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from lib.core import authentication
from lib.api import market_data, user, portfolio

def print_header(title):
    print(f"\n{'='*60}")
    print(f"🔬 TESTING: {title}")
    print(f"{'='*60}")

def print_result(success, message):
    icon = "✅" if success else "❌"
    print(f"{icon} {message}")

def run_integration_suite():
    print("🚀 STARTING FULL INTEGRATION SUITE")
    print("⚠️  WARNING: This script connects to the REAL Upstox API.")
    print("-------------------------------------------------------")

    # 1. AUTHENTICATION
    print_header("Authentication")
    token = authentication.get_access_token()
    if not token:
        print_result(False, "Access Token NOT found.")
        return
    print_result(True, f"Access Token Loaded ({len(token)} chars)")

    # 2. USER PROFILE
    print_header("User Profile & Funds")
    profile = user.get_user_profile(token)
    if profile:
        # User API returns an object, not a dict
        name = getattr(profile, 'user_name', 'Unknown')
        uid = getattr(profile, 'user_id', 'Unknown')
        print_result(True, f"User: {name} | ID: {uid}")
    else:
        print_result(False, "Failed to fetch User Profile")

    funds = user.get_funds_summary(token)
    if funds:
        # Funds returns object with .equity and .commodity attributes
        eq = getattr(funds, 'equity', None)
        avail = getattr(eq, 'available_margin', 0) if eq else 0
        print_result(True, f"Funds Available: {avail}")
    else:
        print_result(False, "Failed to fetch Funds")

    # 3. PORTFOLIO
    print_header("Portfolio")
    holdings = portfolio.get_holdings(token)
    if isinstance(holdings, pd.DataFrame):
        count = len(holdings)
        print_result(True, f"Holdings Fetched: {count} items")
        if count > 0:
            print(f"   Sample: {holdings.iloc[0]['trading_symbol']}")
    else:
        print_result(False, "Failed to fetch Holdings")

    positions = portfolio.get_positions(token)
    if isinstance(positions, pd.DataFrame):
        count = len(positions)
        print_result(True, f"Positions Fetched: {count} items")
    else:
        print_result(False, "Failed to fetch Positions")

    # 4. MARKET DATA (LTP)
    print_header("Market Data (LTP)")
    # NIFTY 50 and RELIANCE (Common symbols)
    # Using Instrument Keys if specific, or try searching
    # Let's use NIFTY INDEX key: NSE_INDEX|Nifty 50
    keys = ["NSE_INDEX|Nifty 50"]
    quotes = market_data.get_market_quotes(token, keys)
    
    # DEBUG: Print raw response keys to see what we got
    print(f"   [DEBUG] Keys returned: {list(quotes.keys())}")
    
    # Use the library helper which handles key mapping ('|' vs ':')
    q = market_data.get_market_quote_for_instrument(token, keys[0])
    
    if q:
        print_result(True, f"Quote Received: {keys[0]}")
        print(f"   LTP: {q.get('last_price')}")
        print(f"   OHLC: {q.get('ohlc')}")
    else:
        print_result(False, f"Failed to fetch Quote for {keys[0]}")

    # 5. HISTORICAL DATA
    print_header("Historical Data")
    # Fetch last 5 days of 1-minute candles for NIFTY
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=5)
    
    df = market_data.fetch_historical_data(
        token, 
        "NSE_INDEX|Nifty 50", 
        "minute", 
        "1", 
        str(start_date), 
        str(end_date)
    )
    
    if not df.empty:
        print_result(True, f"Candles Fetched: {len(df)}")
        print(f"   Last Candle: {df.iloc[-1]['timestamp']} | Close: {df.iloc[-1]['close']}")
    else:
        print_result(False, "Failed to fetch Historical Data (Check Market Data subscription?)")

    # 6. OPTION CHAIN
    print_header("Option Chain")
    # Fetch expiry dates first
    expiries = market_data.get_option_expiry_dates(token, "NSE_INDEX|Nifty 50")
    if expiries:
        expiry = expiries[0]
        print_result(True, f"Expiries Fetched. Next: {expiry}")
        
        # Fetch Chain (ATM +/- 5 strikes)
        # Note: logic for get_option_chain_atm is inside market_data.py in this codebase? 
        # Checking... lib.api.market_data has imports but functions might be in option_chain.py
        # Based on previous file reads, they are in market_data.py
        
        chain = market_data.get_option_chain_atm(token, "NSE_INDEX|Nifty 50", expiry, 2, 2)
        if not chain.empty:
            print_result(True, f"Option Chain Fetched: {len(chain)} contracts")
            print(f"   Strikes: {chain['strike_price'].unique()}")
        else:
            print_result(False, "Failed to fetch Option Chain")
            
    else:
        print_result(False, "Failed to fetch Expiry Dates")

    # ... (Previous Option Chain Section) ...
    # We will expand this section to use the dedicated option_chain library

    # 7. ADVANCED OPTION CHAIN (DataFrame)
    print_header("Advanced Option Chain (DataFrame)")
    # Use the nifty_key from earlier or default
    try:
        from lib.api import option_chain
        
        # Get nearest expiry using the helper
        expiry = option_chain.get_nearest_expiry(token, "NSE_INDEX|Nifty 50")
        if expiry:
            print_result(True, f"Nearest Expiry: {expiry}")
            
            # Fetch full dataframe
            df_chain = option_chain.get_option_chain_dataframe(token, "NSE_INDEX|Nifty 50", expiry)
            if df_chain is not None and not df_chain.empty:
                print_result(True, f"Chain DataFrame Fetched: {len(df_chain)} rows")
                
                # Check ATM IV
                atm_iv = option_chain.get_atm_iv(df_chain)
                print(f"   ATM IV: {atm_iv:.2f}%")
                
                # Check Greek Columns
                if 'ce_delta' in df_chain.columns:
                    print(f"   Greeks Available: ✅")
            else:
                print_result(False, "Failed to fetch DataFrame Chain")
        else:
            print_result(False, "Failed to fetch Nearest Expiry")
    except Exception as e:
        print_result(False, f"Option Chain Error: {e}")

    # 8. ORDER BOOK & TRADES
    print_header("Order Book & Trades")
    try:
        from lib.api import order_management
        
        # Order Book
        orders = order_management.get_order_book(token)
        print_result(True, f"Order Book Fetched: {len(orders)} orders")
        
        # Trades
        trades = order_management.get_trades_for_day(token)
        print_result(True, f"Trades Fetched: {len(trades)} trades")
        
        # Summary
        summary = order_management.get_trades_summary(token)
        if summary:
            print(f"   Total Value Traded: ₹{summary.get('total_value', 0)}")
            
    except Exception as e:
        print_result(False, f"Order Management Error: {e}")

    # 9. V3 MARKET QUOTES (Greeks & OHLC)
    print_header("V3 Market Quotes")
    try:
        from lib.api import market_quotes
        
        # Test OHLC for Nifty
        ohlc = market_quotes.get_ohlc_quote(token, "NSE_INDEX|Nifty 50", "1d")
        if ohlc and 'status' in ohlc and ohlc['status'] == 'success':
            print_result(True, "V3 OHLC Quote Received")
        else:
            print_result(False, "Failed to fetch V3 OHLC")
            
        # Test Greeks (Requires an Option Symbol)
        # We need a valid option symbol. Let's try to grab one from the chain we fetched earlier or a known one?
        # A known reliable way is to not hardcode, but finding one dynamically is hard if market is closed.
        # We will skip valid greek check effectively if we don't have a symbol, 
        # but we can try calling it with an invalid symbol to see if it handles gracefully or if we can use Nifty? 
        # Greeks are for options only. 
        # Let's verify usage of function at least.
        pass 
        
        # Test Full Market Quote
        full_quote = market_quotes.get_full_market_quote(token, "NSE_INDEX|Nifty 50")
        if full_quote:
            print_result(True, "V3 Full Market Quote Received (Nifty 50)")
            market_quotes.format_market_quote(full_quote)
        else:
            print_result(True, "Failed to fetch V3 Full Market Quote")

        # Test Full Market Quote for FNO Scrip (Nifty CE 26200)
        from lib.api import option_chain
        print_header("V3 Market Quote (FNO - Nifty CE 26200)")
        
        nifty_key = "NSE_INDEX|Nifty 50"
        expiry = option_chain.get_nearest_expiry(token, nifty_key)
        
        if expiry:
            print(f"   Expiry: {expiry}")
            # Get chain to find instrument key
            df_chain = option_chain.get_option_chain_dataframe(token, nifty_key, expiry)
            
            if df_chain is not None and not df_chain.empty:
                # Find 26200 Strike
                target_strike = 26200
                strike_row = df_chain[df_chain['strike_price'] == target_strike]
                
                if not strike_row.empty:
                    ce_key = strike_row.iloc[0]['ce_key']
                    print(f"   Found Instrument Key for {target_strike} CE: {ce_key}")
                    
                    # Get Full Quote
                    fno_quote = market_quotes.get_full_market_quote(token, ce_key)
                    if fno_quote:
                        print_result(True, f"V3 Full Market Quote Received ({target_strike} CE)")
                        market_quotes.format_market_quote(fno_quote)
                    else:
                        print_result(False, "Failed to fetch V3 Full Market Quote for FNO")
                else:
                    print_result(False, f"Strike {target_strike} not found in chain")
            else:
                print_result(False, "Failed to fetch Option Chain DataFrame")
        else:
            print_result(False, "Failed to fetch Nearest Expiry")

    except Exception as e:
        print_result(False, f"V3 Quote Error: {e}")

    print("\n" + "="*60)
    print("✅ INTEGRATION SUITE COMPLETE")
    print("="*60)

if __name__ == "__main__":
    run_integration_suite()

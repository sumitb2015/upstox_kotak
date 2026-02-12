import sys
import os
import logging
from lib.core import authentication
from lib.api import market_data, order_management, option_chain

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VerifyRefactor")

def main():
    print("🚀 Starting verification of API Refactoring...")
    
    # Authenticate
    try:
        access_token = authentication.perform_authentication()
        print("✅ Authentication successful")
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        return

    # 1. Test Market Data (SDK)
    print("\n--- Testing Market Data (SDK) ---")
    try:
        # NSE Download
        df_nse = market_data.download_nse_market_data()
        if df_nse is not None and not df_nse.empty:
            print(f"✅ NSE Data: Fetched {len(df_nse)} rows")
        else:
            print("⚠️ NSE Data fetch failed or empty")
            
        # Holidays
        market_data.get_market_holidays(access_token)
        
        # Quotes (LTP)
        # Use a common valid key
        test_key = "NSE_INDEX|Nifty 50"
        quotes = market_data.get_market_quotes(access_token, [test_key])
        print(f"DEBUG: Quotes result: {quotes}")
        if quotes and test_key in quotes:
            print(f"✅ Market Quotes: Success for {test_key}: {quotes[test_key]}")
        else:
            print(f"⚠️ Market Quotes: Failed for {test_key} (might be market closed or bad key)")

    except Exception as e:
        print(f"❌ Market Data Test Failed: {e}")
        import traceback
        traceback.print_exc()

    # 2. Test Option Chain (SDK)
    print("\n--- Testing Option Chain (SDK) ---")
    try:
        test_key = "NSE_INDEX|Nifty 50"
        
        # Expiries
        expiries = option_chain.get_expiries(access_token, test_key)
        if expiries:
            print(f"✅ Expiries: Found {len(expiries)} dates. First: {expiries[0]}")
            expiry = expiries[0]
            
            # Chain
            df_chain = option_chain.get_option_chain_dataframe(access_token, test_key, expiry)
            if df_chain is not None and not df_chain.empty:
                print(f"✅ Option Chain: Fetched {len(df_chain)} strikes for {expiry}")
            else:
                 print("⚠️ Option Chain: Data empty")
        else:
            print("⚠️ No expiries found")

    except Exception as e:
        print(f"❌ Option Chain Test Failed: {e}")
        import traceback
        traceback.print_exc()

    # 3. Test Order Management (SDK)
    print("\n--- Testing Order Management (SDK) ---")
    try:
        # Book
        df_book = order_management.get_order_book(access_token)
        print(f"✅ Order Book: Fetched (Rows: {len(df_book) if not df_book.empty else 0})")
        
        # Trades
        df_trades = order_management.get_trades_for_day(access_token)
        print(f"✅ Trades: Fetched (Rows: {len(df_trades) if not df_trades.empty else 0})")

    except Exception as e:
        print(f"❌ Order Management Test Failed: {e}")
        import traceback
        traceback.print_exc()

    print("\n🎉 Verification Complete (Check above for checkmarks)")

if __name__ == "__main__":
    main()

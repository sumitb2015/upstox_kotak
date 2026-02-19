import os, sys, asyncio
from dotenv import load_dotenv
load_dotenv()
from lib.core.authentication import get_access_token
from lib.api.option_chain import get_option_chain_dataframe, get_expiries
from lib.utils.greeks_helper import calculate_gex_for_chain, calculate_flip_point

async def scan_expiries():
    try:
        token = get_access_token()
        symbol_key = 'NSE_INDEX|Nifty 50'
        expiries = get_expiries(token, symbol_key)
        
        print(f"Scanning {len(expiries)} expiries for NIFTY...")
        for expiry in expiries[:8]:
            df = get_option_chain_dataframe(token, symbol_key, expiry)
            if df is None or df.empty:
                continue
            df = calculate_gex_for_chain(df, 'NIFTY')
            flip = calculate_flip_point(df)
            print(f"  Expiry: {expiry} | Flip Point: {flip}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    asyncio.run(scan_expiries())

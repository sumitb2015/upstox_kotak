import os, sys, asyncio
from dotenv import load_dotenv
load_dotenv()
from lib.core.authentication import get_access_token
from lib.api.option_chain import get_option_chain_dataframe, get_expiries
from lib.utils.greeks_helper import calculate_gex_for_chain, calculate_flip_point

async def check_intraday_flip():
    try:
        token = get_access_token()
        symbol_key = 'NSE_INDEX|Nifty 50'
        expiry = get_expiries(token, symbol_key)[0]
        df = get_option_chain_dataframe(token, symbol_key, expiry)
        
        # We need oi_change
        # Some Upstox responses might not have it directly in the flattened df
        # But it should be there if we mapped it.
        
        # Let's check columns
        print(f"Columns: {df.columns.tolist()}")
        
        # Usually Upstox API V2 doesn't give Intraday GEX directly.
        # But we can try to estimate it if we had prev_oi.
        
        if 'ce_oi' in df.columns and 'ce_prev_oi' in df.columns:
            df['ce_oi_chg'] = df['ce_oi'] - df['ce_prev_oi']
            df['pe_oi_chg'] = df['pe_oi'] - df['pe_prev_oi']
            
            # Temporary GEX calculation with Change
            spot_price = df['spot_price'].iloc[0]
            spot_sq = (spot_price ** 2) / 400
            df['ce_gex_chg'] = df['ce_gamma'] * df['ce_oi_chg'] * spot_sq
            df['pe_gex_chg'] = df['pe_gamma'] * df['pe_oi_chg'] * spot_sq * -1
            df['net_gex_chg'] = df['ce_gex_chg'] + df['pe_gex_chg']
            
            # Find flip on change
            # We'll use a local loop since calculate_flip_point expects specific column names
            # Actually, I'll just rename them for a moment
            temp = df.rename(columns={'net_gex_chg': 'net_strike_gex'})
            flip_chg = calculate_flip_point(temp)
            print(f"Intraday Flip Point (OI Change): {flip_chg}")
        else:
            print("Missing prev_oi data for intraday flip.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    asyncio.run(check_intraday_flip())

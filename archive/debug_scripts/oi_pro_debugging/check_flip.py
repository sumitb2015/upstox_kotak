import os, sys, asyncio
from dotenv import load_dotenv
load_dotenv()
from lib.core.authentication import get_access_token
from lib.api.option_chain import get_option_chain_dataframe, get_expiries
from lib.utils.greeks_helper import calculate_gex_for_chain, calculate_flip_point

async def check_crossover():
    try:
        token = get_access_token()
        symbol_key = 'NSE_INDEX|Nifty 50'
        expiries = get_expiries(token, symbol_key)
        if not expiries:
            print("No expiries found.")
            return
        expiry = expiries[0]
        df = get_option_chain_dataframe(token, symbol_key, expiry)
        
        if df is None or df.empty:
            print("No data found.")
            return
            
        print(f"Underlying: {df['underlying_key'].iloc[0]} | Spot: {df['spot_price'].iloc[0]}")
        
        df = calculate_gex_for_chain(df, 'NIFTY')
        df['net_gex'] = df['ce_gex'] + df['pe_gex']
        
        sub = df[(df['strike_price'] >= 25100) & (df['strike_price'] <= 25250)].sort_values('strike_price')
        print(f"GEX Components for strike 25100-25250 (Expiry {expiry}):")
        for _, row in sub.iterrows():
            print(f"Strike: {row['strike_price']} | CE OI: {row['ce_oi']:,.0f} | PE OI: {row['pe_oi']:,.0f} | Net: {row['net_gex']:,.0f}")
        
        flip = calculate_flip_point(df)
        print(f"\nCalculated Flip Point: {flip}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    asyncio.run(check_crossover())

import os, sys, asyncio
from dotenv import load_dotenv
load_dotenv()
from lib.core.authentication import get_access_token
from lib.api.option_chain import get_option_chain_dataframe, get_expiries
from lib.utils.greeks_helper import calculate_gex_for_chain, calculate_flip_point
import pandas as pd

async def check_total_market_crossover():
    try:
        token = get_access_token()
        symbol_key = 'NSE_INDEX|Nifty 50'
        
        # 1. Get all expiries
        expiries = get_expiries(token, symbol_key)
        if not expiries:
            print("No expiries found.")
            return
            
        print(f"Aggregating GEX across {len(expiries)} expiries...")
        
        # 2. Fetch and aggregate GEX per strike
        total_df = pd.DataFrame()
        
        for expiry in expiries[:5]: # Usually first 5-10 expiries dominate 99% of GEX
            print(f"  Fetching expiry: {expiry}")
            df = get_option_chain_dataframe(token, symbol_key, expiry)
            if df is None or df.empty:
                continue
            df = calculate_gex_for_chain(df, 'NIFTY')
            
            # Keep only necessary columns for aggregation
            strike_data = df[['strike_price', 'ce_gex', 'pe_gex']].copy()
            total_df = pd.concat([total_df, strike_data])
            
        # 3. Sum up GEX per strike
        market_gex = total_df.groupby('strike_price').sum().reset_index()
        market_gex['net_strike_gex'] = market_gex['ce_gex'] + market_gex['pe_gex']
        
        # Find values around 25000-25500
        sub = market_gex[(market_gex['strike_price'] >= 25100) & (market_gex['strike_price'] <= 25500)].sort_values('strike_price')
        print(f"\nAGGREGATE Market GEX (First 5 expiries):")
        for _, row in sub.iterrows():
            print(f"Strike: {row['strike_price']} | Net GEX: {row['net_strike_gex']:,.0f}")
            
        # Use our helper logic to find flip point on the aggregated data
        # We need to pass it strike_price and net_strike_gex columns
        flip = calculate_flip_point(market_gex)
        print(f"\nCalculated Aggregate Flip Point: {flip}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    asyncio.run(check_total_market_crossover())

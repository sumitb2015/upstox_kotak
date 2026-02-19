import os, sys, asyncio
import pandas as pd
from dotenv import load_dotenv
load_dotenv()

from lib.core.authentication import get_access_token
from lib.api.option_chain import get_option_chain_dataframe, get_expiries
from lib.utils.greeks_helper import calculate_gex_for_chain

async def debug_cumulative():
    token = get_access_token()
    symbol_key = 'NSE_INDEX|Nifty 50'
    expiries = get_expiries(token, symbol_key)
    df = get_option_chain_dataframe(token, symbol_key, expiries[0])
    df = calculate_gex_for_chain(df, 'NIFTY')
    
    df['net_strike_gex'] = df['ce_gex'] + df['pe_gex']
    df = df.sort_values('strike_price')
    df['cum_gex'] = df['net_strike_gex'].cumsum()
    
    # Print around spot
    spot = df['spot_price'].iloc[0]
    print(f"Spot: {spot}")
    
    # Filter for strikes around spot
    sub = df[(df['strike_price'] >= 23000) & (df['strike_price'] <= 26500)]
    print("\nCumulative GEX values:")
    for _, row in sub.iterrows():
        # Only print every 5th strike to keep it readable
        if row['strike_price'] % 250 == 0:
            print(f"Strike: {row['strike_price']} | Net GEX: {row['net_strike_gex']/1e7:,.2f} Cr | Cum GEX: {row['cum_gex']/1e7:,.2f} Cr")
            
    # Find zero crossing
    strikes = df['strike_price'].values
    cum = df['cum_gex'].values
    for i in range(len(cum)-1):
        if (cum[i] < 0 and cum[i+1] > 0) or (cum[i] > 0 and cum[i+1] < 0):
            print(f"\n>>> ZERO CROSSING DETECTED between {strikes[i]} and {strikes[i+1]}")

asyncio.run(debug_cumulative())

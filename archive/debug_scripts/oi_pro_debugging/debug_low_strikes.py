import os, sys, asyncio
import pandas as pd
from dotenv import load_dotenv
load_dotenv()

from lib.core.authentication import get_access_token
from lib.api.option_chain import get_option_chain_dataframe, get_expiries
from lib.utils.greeks_helper import calculate_gex_for_chain

async def debug_low_strikes():
    token = get_access_token()
    symbol_key = 'NSE_INDEX|Nifty 50'
    expiries = get_expiries(token, symbol_key)
    df = get_option_chain_dataframe(token, symbol_key, expiries[0])
    df = calculate_gex_for_chain(df, 'NIFTY')
    
    df['net_strike_gex'] = df['ce_gex'] + df['pe_gex']
    df = df.sort_values('strike_price')
    df['cum_gex'] = df['net_strike_gex'].cumsum()
    
    print("Low Strike Cumulative GEX:")
    sub = df[df['strike_price'] <= 24000]
    for _, row in sub.iterrows():
        print(f"Strike: {row['strike_price']} | Net: {row['net_strike_gex']:,.0f} | Cum: {row['cum_gex']:,.0f}")

asyncio.run(debug_low_strikes())

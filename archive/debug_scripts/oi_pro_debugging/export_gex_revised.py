import os, sys, asyncio
import pandas as pd
from dotenv import load_dotenv
load_dotenv()

from lib.core.authentication import get_access_token
from lib.api.option_chain import get_option_chain_dataframe, get_expiries
from lib.utils.greeks_helper import calculate_gex_for_chain, calculate_flip_point

async def export_gex_to_excel():
    try:
        print("Starting REVISED GEX Data Export Tool...")
        token = get_access_token()
        symbol_key = 'NSE_INDEX|Nifty 50'
        
        # 1. Get Expiries
        expiries = get_expiries(token, symbol_key)
        if not expiries:
            print("❌ No expiries found for NIFTY.")
            return
            
        expiry = expiries[0]
        print(f"✅ Fetching data for Expiry: {expiry}")
        
        # 2. Get Option Chain
        df = get_option_chain_dataframe(token, symbol_key, expiry)
        if df is None or df.empty:
            print("❌ No data found in option chain.")
            return
            
        # 3. Perform REVISED Calculations
        # Now uses DIVISOR = 400 AND LotSize = 65
        df = calculate_gex_for_chain(df, 'NIFTY')
        df['net_strike_gex'] = df['ce_gex'] + df['pe_gex']
        
        # Sort for cumulative calc
        df = df.sort_values('strike_price')
        df['cumulative_gex'] = df['net_strike_gex'].cumsum()
        
        # 4. Filter for relevant columns
        cols_to_keep = [
            'strike_price', 'spot_price', 
            'ce_oi', 'ce_gamma', 'ce_gex',
            'pe_oi', 'pe_gamma', 'pe_gex',
            'net_strike_gex', 'cumulative_gex'
        ]
        
        export_df = df[[c for c in cols_to_keep if c in df.columns]].copy()
        
        # 5. Global Metrics
        total_net_gex = df['net_strike_gex'].sum()
        flip_point = calculate_flip_point(df)
        spot_price = df['spot_price'].iloc[0]
        
        # 6. Save Excel
        file_name = "nifty_gex_revised_institutional.xlsx"
        with pd.ExcelWriter(file_name, engine='openpyxl') as writer:
            export_df.to_excel(writer, index=False, sheet_name='GEX Data')
            
            # Summary Metrics
            summary_data = {
                'Metric': ['Underlying', 'Expiry', 'Spot Price', 'Lot Size', 'Total Net GEX (Cr)', 'Cumulative Flip Point'],
                'Value': ['NIFTY', expiry, spot_price, 65, total_net_gex / 1e7, flip_point]
            }
            pd.DataFrame(summary_data).to_excel(writer, index=False, sheet_name='Summary')

        print(f"🚀 Revised data exported to: {os.path.abspath(file_name)}")
        print(f"📊 Summary: Net GEX (Cr) = {total_net_gex/1e7:.2f} | Flip Point = {flip_point}")

    except Exception as e:
        print(f"❌ Error during export: {e}")

if __name__ == '__main__':
    asyncio.run(export_gex_to_excel())

import os, sys, asyncio
import pandas as pd
from dotenv import load_dotenv
load_dotenv()

from lib.core.authentication import get_access_token
from lib.api.option_chain import get_option_chain_dataframe, get_expiries
from lib.utils.greeks_helper import calculate_gex_for_chain, calculate_flip_point

async def export_gex_to_excel():
    try:
        print("Starting GEX Data Export Tool...")
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
            
        # 3. Perform Calculations
        # We use the standardized helper which now uses DIVISOR = 400
        df = calculate_gex_for_chain(df, 'NIFTY')
        df['net_strike_gex'] = df['ce_gex'] + df['pe_gex']
        
        # 4. Filter for relevant columns to keep the Excel clean
        cols_to_keep = [
            'strike_price', 'spot_price', 
            'ce_oi', 'ce_gamma', 'ce_gex',
            'pe_oi', 'pe_gamma', 'pe_gex',
            'net_strike_gex'
        ]
        
        # Ensure all columns exist
        available_cols = [c for c in cols_to_keep if c in df.columns]
        export_df = df[available_cols].copy()
        export_df = export_df.sort_values('strike_price')
        
        # 5. Calculate Global Metrics
        total_net_gex = export_df['net_strike_gex'].sum()
        flip_point = calculate_flip_point(df)
        spot_price = export_df['spot_price'].iloc[0] if 'spot_price' in export_df.columns else 0
        
        # 6. Create Excel with multiple sheets
        file_name = "nifty_gex_calculations.xlsx"
        with pd.ExcelWriter(file_name, engine='openpyxl') as writer:
            # Sheet 1: Detailed Calculations
            export_df.to_sheet_name = 'Strike-wise Calculations'
            export_df.to_excel(writer, index=False, sheet_name='GEX Data')
            
            # Sheet 2: Summary Metrics
            summary_data = {
                'Metric': ['Underlying', 'Expiry', 'Spot Price', 'Total Net GEX (Units)', 'Total Net GEX (Cr)', 'Flip Point', 'Institutional Divider'],
                'Value': ['NIFTY', expiry, spot_price, total_net_gex, total_net_gex / 1e7, flip_point, 400]
            }
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, index=False, sheet_name='Summary')
            
            # Sheet 3: Formula Reference
            formula_data = {
                'Component': ['GEX Scaling', 'Call GEX', 'Put GEX', 'Net GEX'],
                'Formula': [
                    'S^2 / 400 (0.25% Move model)',
                    'Gamma * OI * Scaling',
                    'Gamma * OI * Scaling * -1',
                    'Call GEX + Put GEX'
                ],
                'Logic': [
                    'Institutional benchmark for daily expected move',
                    'Higher Gamma at ATM drives higher exposure',
                    'Puts contribute negative gamma for dealer positioning',
                    'Zero crossing determines the Flip Point'
                ]
            }
            formula_df = pd.DataFrame(formula_data)
            formula_df.to_excel(writer, index=False, sheet_name='Formula Reference')

        print(f"🚀 Successfully exported GEX data to: {os.path.abspath(file_name)}")
        print(f"📊 Summary: Net GEX = {total_net_gex/1e7:.2f} Cr | Flip Point = {flip_point}")

    except Exception as e:
        print(f"❌ Error during export: {e}")

if __name__ == '__main__':
    asyncio.run(export_gex_to_excel())

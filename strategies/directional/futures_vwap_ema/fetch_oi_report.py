
import sys
import os
import pandas as pd
from datetime import datetime

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from lib.api.market_data import download_nse_market_data, get_option_chain_atm
from lib.utils.instrument_utils import get_future_instrument_key
from lib.utils.expiry_cache import get_expiry_for_strategy
from lib.oi_analysis.cumulative_oi_analysis import CumulativeOIAnalyzer
from lib.core.authentication import check_existing_token, perform_authentication, save_access_token
from strategies.directional.futures_vwap_ema.config import CONFIG

def generate_oi_report():
    print("🚀 Starting OI Analysis Report Generation...")
    
    # 1. Authentication
    token_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'lib', 'core', 'accessToken.txt')
    try:
        with open(token_path, 'r') as f:
            access_token = f.read().strip()
    except Exception as e:
        print(f"❌ Failed to load token: {e}")
        return

    # 2. Setup
    underlying = CONFIG['underlying']
    radius = CONFIG['oi_strikes_radius']
    print(f"📋 Config: Underlying={underlying}, Radius={radius} (Total {radius*2+1} strikes)")

    # 3. Get Instrument Data (for dynamic step)
    nse_data = download_nse_market_data()
    future_key = get_future_instrument_key(underlying, nse_data)
    
    # Estimate strike step
    expiry = get_expiry_for_strategy(access_token, 'current_week', underlying)
    print(f"📅 Expiry: {expiry}")
    
    # Fetch Chain to determine step
    print("🔍 Determining strike step...")
    # Use Nifty Index key for chain (usually NSE_INDEX|Nifty 50)
    # The helper might need the exact index key, but let's try mapping manually or using what works in live.py
    # In live.py we used: futures_instrument_key.replace("NSE_FO", "NSE_INDEX") logic roughly
    # But get_future_instrument_key returns e.g. NSE_FO|... 
    # Let's trust CumulativeOIAnalyzer's key logic if possible, or build it.
    
    analyzer = CumulativeOIAnalyzer(access_token)
    # analyzer.underlying_key is usually Nifty 50 index key
    
    chain_df = get_option_chain_atm(access_token, analyzer.underlying_key, expiry, strikes_above=2, strikes_below=2)
     
    strike_step = 50 # Default
    if not chain_df.empty:
        strikes = sorted(chain_df['strike_price'].unique())
        if len(strikes) >= 2:
            strike_step = int(strikes[1] - strikes[0])
    
    print(f"📏 Strike Step: {strike_step}")
    
    # 4. Fetch Full Chain for Analysis
    # We optionally allow passing a custom price to center the strikes (like Futures)
    custom_spot = None # Set this to e.g. 25150 to match live log
    
    if custom_spot:
        print(f"🎯 Centering bucket on Custom Price: {custom_spot}...")
        atm_strike = round(custom_spot / strike_interval) * strike_interval
        full_chain = get_option_chain_atm(access_token, analyzer.underlying_key, expiry, strikes_above=radius, strikes_below=radius, strike_interval=strike_step)
        # Note: get_option_chain_atm internally uses index spot. 
        # To perfectly match live.py, we manually filter the chain if possible or 
        # just know that live.py calculates specific strikes.
    else:
        print(f"📥 Fetching Option Chain (Radius {radius}, based on Index Spot)...")
        full_chain = get_option_chain_atm(access_token, analyzer.underlying_key, expiry, strikes_above=radius, strikes_below=radius)
    
    if full_chain.empty:
        print("❌ Failed to fetch option chain.")
        return

    # 5. Extract Data
    report_data = []
    
    # Pivot logic: The chain returned is flat (CE and PE in separate rows)
    # We need to pivot it to Strike | CE_OI | PE_OI ...
    
    if 'CE_OI' not in full_chain.columns:
        print("ℹ️ Pivoting flattened chain data...")
        # Include 'prev_oi' for Change PCR calculation
        pivot_df = full_chain[['strike_price', 'type', 'oi', 'prev_oi', 'ltp']].copy()
        
        # Pivot
        pivoted = pivot_df.pivot(index='strike_price', columns='type', values=['oi', 'prev_oi', 'ltp'])
        pivoted.columns = [f'{col[1]}_{col[0]}'.upper() for col in pivoted.columns]
        full_chain = pivoted.reset_index()
        
        # Consistent Renaming to match CE/PE style
        full_chain = full_chain.rename(columns={
            'CALL_OI': 'CE_OI', 'PUT_OI': 'PE_OI',
            'CALL_PREV_OI': 'CE_PREV_OI', 'PUT_PREV_OI': 'PE_PREV_OI',
            'CALL_LTP': 'CE_LTP', 'PUT_LTP': 'PE_LTP'
        })
        
        print(f"Pivoted Columns: {full_chain.columns.tolist()}")

    # Calculate Totals
    total_ce_oi = full_chain['CE_OI'].sum()
    total_pe_oi = full_chain['PE_OI'].sum()
    total_pcr = total_pe_oi / total_ce_oi if total_ce_oi > 0 else 0
    
    # Calculate Change Totals (Current Day Buildup)
    total_ce_change = (full_chain['CE_OI'] - full_chain['CE_PREV_OI']).sum()
    total_pe_change = (full_chain['PE_OI'] - full_chain['PE_PREV_OI']).sum()
    change_pcr = total_pe_change / total_ce_change if total_ce_change > 0 else 0
    
    print(f"\n📊 Total OI PCR: {total_pcr:.2f}")
    print(f"🔥 Daily Change PCR: {change_pcr:.2f} (Matches Trending OI)")

    for _, row in full_chain.sort_values('strike_price').iterrows():
        strike = row['strike_price']
        ce_oi = row['CE_OI']
        pe_oi = row['PE_OI']
        pcr = pe_oi / ce_oi if ce_oi > 0 else 0
        
        report_data.append({
            'Strike': strike,
            'CE_OI': ce_oi,
            'PE_OI': pe_oi,
            'CE_PREV_OI': row.get('CE_PREV_OI', 0),
            'PE_PREV_OI': row.get('PE_PREV_OI', 0),
            'Strike_PCR': round(pcr, 2),
            'CE_LTP': row.get('CE_LTP', 0),
            'PE_LTP': row.get('PE_LTP', 0)
        })
        
    # 6. Export to CSV
    df = pd.DataFrame(report_data)
    
    # Add Summary Row
    summary_row = {
        'Strike': 'TOTAL',
        'CE_OI': total_ce_oi,
        'PE_OI': total_pe_oi,
        'CE_PREV_OI': full_chain['CE_PREV_OI'].sum(),
        'PE_PREV_OI': full_chain['PE_PREV_OI'].sum(),
        'Strike_PCR': round(total_pcr, 2),
        'CE_LTP': '',
        'PE_LTP': ''
    }
    df = pd.concat([df, pd.DataFrame([summary_row])], ignore_index=True)
    
    filename = f"oi_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    df.to_csv(filename, index=False)
    
    print(f"\n✅ Report generated: {filename}")
    print(df)

if __name__ == "__main__":
    generate_oi_report()

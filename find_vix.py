from lib.api.market_data import download_nse_market_data
import pandas as pd

def find_vix():
    df = download_nse_market_data()
    if df is None or df.empty:
        print("Failed to load DataFrame")
        return
        
    print(f"Columns: {df.columns.tolist()}")
    
    # Search for VIX in likely columns
    # Common columns: 'trading_symbol', 'name', 'instrument_key'
    
    mask = df['trading_symbol'].str.contains('VIX', case=False, na=False) | \
           df['name'].str.contains('VIX', case=False, na=False)
           
    matches = df[mask]
    
    if not matches.empty:
        print("Found Matches:")
        for _, row in matches.iterrows():
            print(f"Key: {row.get('instrument_key')} | Symbol: {row.get('trading_symbol')} | Name: {row.get('name')}")
    else:
        print("No VIX matches found.")

if __name__ == "__main__":
    find_vix()

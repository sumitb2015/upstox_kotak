
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
from lib.core.backtesting.engine import BacktestDataManager
from lib.core.authentication import get_access_token

def dump_day_data(date, symbol_key):
    access_token = get_access_token()
    dm = BacktestDataManager(access_token)
    
    df = dm.fetch_data(symbol_key, date, date, 'minute', 1)
    if df.empty:
        print(f"No data for {symbol_key} on {date}")
        return
    
    print(f"\n--- Data for {symbol_key} on {date} ---")
    
    # Entry area (9:29 to 9:32)
    entry_area = df[(df.index.time >= pd.Timestamp("09:29").time()) & 
                    (df.index.time <= pd.Timestamp("09:32").time())]
    print("\nEntry Window (9:29 - 9:32):")
    print(entry_area[['open', 'high', 'low', 'close']])
    
    # Exit area (15:14 to 15:16)
    exit_area = df[(df.index.time >= pd.Timestamp("15:14").time()) & 
                   (df.index.time <= pd.Timestamp("15:16").time())]
    print("\nExit Window (15:14 - 15:16):")
    print(exit_area[['open', 'high', 'low', 'close']])

if __name__ == "__main__":
    date = "2025-12-22"
    # We need to find the keys first. I'll use the ones I know from previous runs if possible, 
    # or just use Nifty Index to check ATM first.
    
    # Let's just hardcode the keys for 26150 CE/PE for 2025-12-22 if we can resolve them.
    access_token = get_access_token()
    dm = BacktestDataManager(access_token)
    ce_key = dm.get_instrument_key_for_date("NIFTY", 26150, "CE", date)
    pe_key = dm.get_instrument_key_for_date("NIFTY", 26150, "PE", date)
    
    dump_day_data(date, ce_key)
    dump_day_data(date, pe_key)

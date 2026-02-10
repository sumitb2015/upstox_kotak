import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def calculate_supertrend(df, period=10, multiplier=3):
    """
    Calculates Supertrend indicator.
    """
    # Calculate True Range (TR)
    df['H-L'] = df['High'] - df['Low']
    df['H-PC'] = abs(df['High'] - df['Close'].shift(1))
    df['L-PC'] = abs(df['Low'] - df['Close'].shift(1))
    df['TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
    
    # Calculate ATR (Average True Range)
    # Using RMA (Wilder's Smoothing) which is standard for Supertrend (e.g. TradingView)
    # pandas ewm with alpha=1/period approximates RMA
    df['ATR'] = df['TR'].ewm(alpha=1/period, adjust=False).mean()

    # Basic Bands
    df['basic_upper'] = (df['High'] + df['Low']) / 2 + multiplier * df['ATR']
    df['basic_lower'] = (df['High'] + df['Low']) / 2 - multiplier * df['ATR']

    # Initialize Final Bands
    df['final_upper'] = df['basic_upper']
    df['final_lower'] = df['basic_lower']
    df['supertrend'] = np.nan
    df['trend'] = np.nan # 1 for uptrend, -1 for downtrend

    # Iterate to calculate final bands and trend
    # We need to iterate because final bands depend on previous final bands
    for i in range(period, len(df)):
        # Final Upper Band
        if df['basic_upper'].iloc[i] < df['final_upper'].iloc[i-1] or \
           df['Close'].iloc[i-1] > df['final_upper'].iloc[i-1]:
            df.loc[df.index[i], 'final_upper'] = df['basic_upper'].iloc[i]
        else:
            df.loc[df.index[i], 'final_upper'] = df['final_upper'].iloc[i-1]

        # Final Lower Band
        if df['basic_lower'].iloc[i] > df['final_lower'].iloc[i-1] or \
           df['Close'].iloc[i-1] < df['final_lower'].iloc[i-1]:
            df.loc[df.index[i], 'final_lower'] = df['basic_lower'].iloc[i]
        else:
            df.loc[df.index[i], 'final_lower'] = df['final_lower'].iloc[i-1]

    # Calculate Trend and Supertrend
    for i in range(period, len(df)):
        if df['Close'].iloc[i] > df['final_upper'].iloc[i-1]:
            df.loc[df.index[i], 'trend'] = 1
        elif df['Close'].iloc[i] < df['final_lower'].iloc[i-1]:
            df.loc[df.index[i], 'trend'] = -1
        else:
            df.loc[df.index[i], 'trend'] = df['trend'].iloc[i-1]
            
        if df['trend'].iloc[i] == 1:
            df.loc[df.index[i], 'supertrend'] = df['final_lower'].iloc[i]
        else:
            df.loc[df.index[i], 'supertrend'] = df['final_upper'].iloc[i]

    # Clean up temp columns
    cols_to_drop = ['H-L', 'H-PC', 'L-PC', 'TR', 'basic_upper', 'basic_lower', 'final_upper', 'final_lower', 'trend']
    # Keeping ATR for reference might be useful, but let's drop it if needed. 
    # User just asked for supertrend appended.
    # df.drop(columns=cols_to_drop, inplace=True) 
    # Let's keep final_upper/lower internally but output cleaner. 
    # Actually, standard supertrend output is just the value and maybe direction.
    
    return df

def main():
    # Ticker for Nifty 50
    ticker = "^NSEI"
    
    print(f"Fetching data for {ticker}...")
    
    # Fetching 1 month of data to ensure indicators calculate correctly
    # '2 days' is too short for any indicator warmth
    end_date = datetime.now()
    start_date = end_date - timedelta(days=55) # Fetch 55 days to be safe (yfinance 60d limit for 5m)
    
    try:
        data = yf.download(ticker, start=start_date, end=end_date, interval='5m', progress=False)
        
        if data.empty:
            print("No data fetched. Check your internet connection or ticker symbol.")
            return

        # Flatten MultiIndex columns if necessary (common with newer yfinance versions)
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        print(f"Fetched {len(data)} rows.")
        
        # Calculate Supertrend
        # Standard settings: Period 10, Multiplier 3 (or 7, 3)
        # We will use 10, 3 as it's very common.
        data = calculate_supertrend(data, period=10, multiplier=3)
        
        # Filter for the last 2 days
        # We check the unique dates in the index
        unique_dates = np.unique(data.index.date)
        if len(unique_dates) >= 2:
            last_2_days = unique_dates[-2:]
            # Filter
            start_of_last_2_days = pd.Timestamp(last_2_days[0]).tz_localize(data.index.tz)
            result_df = data[data.index >= start_of_last_2_days].copy()
        else:
            result_df = data.copy()
            print("Warning: Less than 2 days of data available in the fetched range.")

        # Clean output
        # Keep OHLCV and Supertrend
        # Note: yfinance multi-index columns might need flattening if existing
        if isinstance(data.columns, pd.MultiIndex):
             # This happens if multiple tickers or yf version differences
             # But for single ticker usually it depends.
             # Flattening if necessary
             pass # usually fine for single ticker standard download

        output_file = "nifty_supertrend_last_2_days.csv"
        result_df.to_csv(output_file)
        print(f"Saved data with Supertrend to {output_file}")
        print(result_df[['Close', 'supertrend']].tail())

    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

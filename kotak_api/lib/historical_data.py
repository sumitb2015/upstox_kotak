"""
Historical data fetcher for indicators and backtesting.

Provides helpers for:
- Fetching historical OHLC data from yfinance
- Converting to candle format
- Warming up indicators
"""

import yfinance as yf
import pandas as pd
from collections import deque


def fetch_nifty_historical(period="5d", interval="1m"):
    """
    Fetch historical Nifty data from yfinance.
    
    Args:
        period (str, optional): Data period. Defaults to "5d".
            Options: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
        interval (str, optional): Data interval. Defaults to "1m".
            Options: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo
    
    Returns:
        DataFrame: Historical OHLC data with columns: Open, High, Low, Close, Volume
        Returns empty DataFrame if fetch fails.
    
    Example:
        >>> df = fetch_nifty_historical(period="5d", interval="1m")
        >>> print(len(df))  # Number of candles
    """
    try:
        print(f"  Fetching NIFTY historical data ({period}, {interval})...")
        df = yf.download("^NSEI", period=period, interval=interval, progress=False)
        
        if df.empty:
            print("  ⚠️ No historical data found")
            return pd.DataFrame()
        
        # Handle multi-level columns
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        print(f"  ✅ Fetched {len(df)} candles")
        return df
        
    except Exception as e:
        print(f"  ❌ Error fetching historical data: {e}")
        return pd.DataFrame()


def fetch_stock_historical(symbol, period="5d", interval="1m"):
    """
    Fetch historical data for any stock/index.
    
    Args:
        symbol (str): Yahoo Finance symbol (e.g., "^NSEI", "RELIANCE.NS", "AAPL")
        period (str, optional): Data period. Defaults to "5d".
        interval (str, optional): Data interval. Defaults to "1m".
    
    Returns:
        DataFrame: Historical OHLC data
    """
    try:
        print(f"  Fetching {symbol} historical data ({period}, {interval})...")
        df = yf.download(symbol, period=period, interval=interval, progress=False)
        
        if df.empty:
            print(f"  ⚠️ No data found for {symbol}")
            return pd.DataFrame()
        
        # Handle multi-level columns
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        print(f"  ✅ Fetched {len(df)} candles")
        return df
        
    except Exception as e:
        print(f"  ❌ Error fetching data for {symbol}: {e}")
        return pd.DataFrame()


def convert_df_to_candles(df, max_candles=60):
    """
    Convert DataFrame to list of candle dicts.
    
    Args:
        df (DataFrame): OHLC DataFrame from yfinance
        max_candles (int, optional): Maximum candles to return. Defaults to 60.
    
    Returns:
        deque: Candles as dicts with keys: open, high, low, close, timestamp
    
    Example:
        >>> df = fetch_nifty_historical()
        >>> candles = convert_df_to_candles(df)
        >>> print(candles[-1])  # Latest candle
        {'open': 24100.5, 'high': 24150.0, ...}
    """
    candles = deque(maxlen=max_candles)
    
    for idx, row in df.iterrows():
        try:
            candle = {
                'open': float(row['Open']),
                'high': float(row['High']),
                'low': float(row['Low']),
                'close': float(row['Close']),
                'timestamp': idx.to_pydatetime() if hasattr(idx, 'to_pydatetime') else idx
            }
            candles.append(candle)
        except Exception:
            continue
    
    return candles


def warm_up_indicators(period="5d", interval="1m", max_candles=60):
    """
    Fetch historical data and convert to candles for indicator warm-up.
    
    Convenience function that combines fetch + convert.
    
    Args:
        period (str, optional): Data period. Defaults to "5d".
        interval (str, optional): Data interval. Defaults to "1m".
        max_candles (int, optional): Maximum candles to keep. Defaults to 60.
    
    Returns:
        deque: Candles ready for indicator calculation
    
    Example:
        >>> candles = warm_up_indicators(period="5d", interval="1m")
        >>> closes = [c['close'] for c in candles]
        >>> ema9 = calculate_ema(closes, 9)
    """
    df = fetch_nifty_historical(period=period, interval=interval)
    
    if df.empty:
        print("  ⚠️ No historical data available for warm-up")
        return deque(maxlen=max_candles)
    
    return convert_df_to_candles(df, max_candles)


def get_latest_closes(candles):
    """
    Extract close prices from candles.
    
    Args:
        candles (list/deque): List of candle dicts
    
    Returns:
        list: Close prices in chronological order
    """
    return [c['close'] for c in candles if 'close' in c]


def get_previous_day_data(symbol="^NSEI"):
    """
    Get previous trading day's High, Low, Close for any symbol.
    
    Commonly used for PDH (Previous Day High), PDL (Previous Day Low),
    PDC (Previous Day Close) in trading strategies.
    
    Args:
        symbol (str, optional): Yahoo Finance symbol. Defaults to "^NSEI" (Nifty).
    
    Returns:
        dict: {'date': str, 'high': float, 'low': float, 'close': float}
              Returns None if data fetch fails.
    
    Example:
        >>> prev_day = get_previous_day_data()
        >>> print(f"PDH: {prev_day['high']}, PDL: {prev_day['low']}")
        PDH: 24250.5, PDL: 24100.0
    """
    try:
        # Fetch last 5 days to ensure we get previous completed trading day
        df = yf.download(symbol, period="5d", interval="1d", progress=False)
        
        if df.empty or len(df) < 2:
            print(f"  ⚠️ Insufficient data for {symbol}")
            return None
        
        # Handle multi-level columns
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        # Remove any incomplete data
        df = df.dropna()
        
        # Second to last row is the previous completed trading day
        # (Last row might be today if market is open)
        prev_day = df.iloc[-2]
        
        return {
            'date': prev_day.name.strftime('%Y-%m-%d'),
            'high': float(prev_day['High']),
            'low': float(prev_day['Low']),
            'close': float(prev_day['Close'])
        }
        
    except Exception as e:
        print(f"  ❌ Error fetching previous day data for {symbol}: {e}")
        return None

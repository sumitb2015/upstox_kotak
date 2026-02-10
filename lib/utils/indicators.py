"""
Technical Indicator Utilities using TA-Lib

Provides clean, tested indicator calculations for all strategies.
Eliminates duplicate manual calculations.
"""

import pandas as pd
import numpy as np


def calculate_ema(df: pd.DataFrame, period: int, price_column: str = 'close') -> float:
    """
    Calculate Exponential Moving Average using TA-Lib.
    
    Args:
        df: DataFrame with OHLCV data
        period: EMA period
        price_column: Column to use for calculation (default: 'close')
    
    Returns:
        float: Latest EMA value
    
    Raises:
        ValueError: If insufficient data or invalid period
    """
    import talib
    
    if df is None or df.empty:
        raise ValueError("DataFrame is empty")
    
    if len(df) < period:
        raise ValueError(f"Insufficient data: need {period} candles, got {len(df)}")
    
    if price_column not in df.columns:
        raise ValueError(f"Column '{price_column}' not found in DataFrame")
    
    # Use TA-Lib EMA
    ema_series = talib.EMA(df[price_column].values, timeperiod=period)
    
    # Return the last value
    return float(ema_series[-1])


def calculate_ema_series(df: pd.DataFrame, period: int, price_column: str = 'close') -> pd.Series:
    """
    Calculate Exponential Moving Average series using TA-Lib.
    
    Args:
        df: DataFrame with OHLCV data
        period: EMA period
        price_column: Column to use for calculation (default: 'close')
    
    Returns:
        pd.Series: EMA series
    """
    import talib
    
    if df is None or df.empty:
        raise ValueError("DataFrame is empty")
    
    if price_column not in df.columns:
        raise ValueError(f"Column '{price_column}' not found in DataFrame")
    
    # Use TA-Lib EMA
    ema_array = talib.EMA(df[price_column].values, timeperiod=period)
    return pd.Series(ema_array, index=df.index)


def calculate_vwap(df: pd.DataFrame) -> float:
    """
    Calculate Volume Weighted Average Price (Intraday VWAP).
    
    VWAP = Cumulative(Typical Price × Volume) / Cumulative(Volume)
    Typical Price = (High + Low + Close) / 3
    
    Args:
        df: DataFrame with OHLCV data (must be sorted by time, from session start)
    
    Returns:
        float: Current VWAP value
    
    Raises:
        ValueError: If insufficient data or missing columns
    """
    try:
        if df is None or df.empty:
            raise ValueError("DataFrame is empty")
        
        required_cols = ['high', 'low', 'close', 'volume']
        missing = [col for col in required_cols if col not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")
        
        # Calculate typical price
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        
        # Calculate VWAP
        pv = typical_price * df['volume']
        cumulative_pv = pv.cumsum()
        cumulative_volume = df['volume'].cumsum()
        
        vwap_series = cumulative_pv / cumulative_volume
        
        return float(vwap_series.iloc[-1])
        
    except Exception as e:
        raise ValueError(f"Error calculating VWAP: {e}")


def calculate_sma(df: pd.DataFrame, period: int, price_column: str = 'close') -> float:
    """
    Calculate Simple Moving Average using TA-Lib.
    
    Args:
        df: DataFrame with OHLCV data
        period: SMA period
        price_column: Column to use for calculation (default: 'close')
    
    Returns:
        float: Latest SMA value
    """
    import talib
    
    if df is None or df.empty:
        raise ValueError("DataFrame is empty")
    
    if len(df) < period:
        raise ValueError(f"Insufficient data: need {period} candles, got {len(df)}")
    
    if price_column not in df.columns:
        raise ValueError(f"Column '{price_column}' not found in DataFrame")
    
    # Use TA-Lib SMA
    sma_series = talib.SMA(df[price_column].values, timeperiod=period)
    return float(sma_series[-1])


def calculate_rsi(df: pd.DataFrame, period: int = 14, price_column: str = 'close') -> float:
    """
    Calculate Relative Strength Index using TA-Lib.
    
    Args:
        df: DataFrame with OHLCV data
        period: RSI period (default: 14)
        price_column: Column to use for calculation (default: 'close')
    
    Returns:
        float: Latest RSI value
    """
    import talib
    
    if df is None or df.empty:
        raise ValueError("DataFrame is empty")
    
    if len(df) < period + 1:
        raise ValueError(f"Insufficient data: need {period + 1} candles, got {len(df)}")
    
    if price_column not in df.columns:
        raise ValueError(f"Column '{price_column}' not found in DataFrame")
    
    # Use TA-Lib RSI
    rsi_series = talib.RSI(df[price_column].values, timeperiod=period)
    return float(rsi_series[-1])


def calculate_atr(df: pd.DataFrame, period: int = 14) -> float:
    """
    Calculate Average True Range using TA-Lib.
    """
    try:
        import talib
        if df is None or df.empty: raise ValueError("DataFrame is empty")
        
        # Use TA-Lib ATR
        atr_series = talib.ATR(
            df['high'].values, 
            df['low'].values, 
            df['close'].values, 
            timeperiod=period
        )
        return float(atr_series[-1])
    except Exception as e:
        raise ValueError(f"Error calculating ATR: {e}")


def calculate_adx(df: pd.DataFrame, period: int = 14) -> float:
    """
    Calculate Average Directional Index using TA-Lib.
    """
    try:
        import talib
        if df is None or df.empty: raise ValueError("DataFrame is empty")
        
        # Use TA-Lib ADX
        adx_series = talib.ADX(
            df['high'].values, 
            df['low'].values, 
            df['close'].values, 
            timeperiod=period
        )
        return float(adx_series[-1])
    except Exception as e:
        raise ValueError(f"Error calculating ADX: {e}")


def calculate_supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> tuple[float, float]:
    """
    Calculate SuperTrend indicator.
    
    Args:
        df: DataFrame with 'High', 'Low', 'Close' columns (case-insensitive)
        period: ATR Period (default 10)
        multiplier: Factor (default 3)
        
    Returns:
        tuple: (trend_direction, supertrend_value)
               trend_direction: 1 for Uptrend, -1 for Downtrend
               supertrend_value: The current supertrend line value
    """
    try:
        if df is None or df.empty:
            raise ValueError("DataFrame is empty")
            
        # Normalize column names to Title Case for internal consistency (High, Low, Close)
        data = df.copy()
        data.columns = [c.capitalize() for c in data.columns]
        
        required = ['High', 'Low', 'Close']
        if not all(col in data.columns for col in required):
            # Try lowercase check
             data.columns = [c.lower() for c in data.columns]
             if not all(col in data.columns for col in ['high', 'low', 'close']):
                 raise ValueError(f"Missing required columns: {required}")
             # Rename to Title Case for the logic below
             data.rename(columns={'high': 'High', 'low': 'Low', 'close': 'Close'}, inplace=True)

        # Calculate ATR using TA-Lib
        import talib
        data['ATR'] = talib.ATR(data['High'].values, data['Low'].values, data['Close'].values, timeperiod=period)
        
        # Handle initial NaNs from ATR
        data['ATR'] = data['ATR'].fillna(0)

        # Basic Bands
        data['basic_upper'] = (data['High'] + data['Low']) / 2 + multiplier * data['ATR']
        data['basic_lower'] = (data['High'] + data['Low']) / 2 - multiplier * data['ATR']

        # Initialize Final Bands
        data['final_upper'] = data['basic_upper']
        data['final_lower'] = data['basic_lower']
        data['supertrend'] = np.nan
        data['trend'] = 0 # 1 for uptrend, -1 for downtrend

        # Iterative calculation
        # Convert to numpy arrays for speed
        # using '0' for first row
        
        # We need to loop. Numba would be faster but for this scale (intraday) python loop is acceptable
        # Or fairly optimized loop
        
        # Pre-allocate arrays
        basic_upper = data['basic_upper'].values
        basic_lower = data['basic_lower'].values
        close = data['Close'].values
        final_upper = np.zeros(len(data))
        final_lower = np.zeros(len(data))
        trend = np.zeros(len(data))
        supertrend = np.zeros(len(data))

        # First valid index is 'period' (ATR warmup)
        # But we can start iterating from 1 safely if we handle nans/initials
        
        for i in range(1, len(data)):
            # Final Upper Band
            if basic_upper[i] < final_upper[i-1] or close[i-1] > final_upper[i-1]:
                final_upper[i] = basic_upper[i]
            else:
                final_upper[i] = final_upper[i-1]

            # Final Lower Band
            if basic_lower[i] > final_lower[i-1] or close[i-1] < final_lower[i-1]:
                final_lower[i] = basic_lower[i]
            else:
                final_lower[i] = final_lower[i-1]

            # Trend
            if close[i] > final_upper[i-1]:
                trend[i] = 1
            elif close[i] < final_lower[i-1]:
                trend[i] = -1
            else:
                trend[i] = trend[i-1]
                
            # Supertrend Value
            if trend[i] == 1:
                supertrend[i] = final_lower[i]
            else:
                supertrend[i] = final_upper[i]
                
        # Return latest values
        return float(trend[-1]), float(supertrend[-1])

    except Exception as e:
        raise ValueError(f"Error calculating SuperTrend: {e}")

def calculate_renko_ema(brick_closes: list[float] | pd.Series | np.ndarray, period: int) -> float:
    """
    Calculate Exponential Moving Average specifically for Renko bricks.
    
    Renko EMA is time-independent and based solely on brick closing prices.
    
    Args:
        brick_closes: List, Series, or Array of Renko brick closing prices
        period: EMA period (number of bricks)
        
    Returns:
        float: Latest EMA value
        
    Raises:
        ValueError: If insufficient data or empty input
    """
    import talib
    
    # Convert input to numpy array of floats
    if isinstance(brick_closes, pd.Series):
        values = brick_closes.values.astype(float)
    elif isinstance(brick_closes, list):
        values = np.array(brick_closes, dtype=float)
    elif isinstance(brick_closes, np.ndarray):
        values = brick_closes.astype(float)
    else:
        raise ValueError(f"Unsupported input type: {type(brick_closes)}")
        
    if len(values) == 0:
        raise ValueError("Input data is empty")
        
    if len(values) < period:
        raise ValueError(f"Insufficient brick data: need {period} bricks, got {len(values)}")
        
    # Calculate EMA using TA-Lib
    ema_series = talib.EMA(values, timeperiod=period)
    
    # Return the last valid EMA value
    return float(ema_series[-1])

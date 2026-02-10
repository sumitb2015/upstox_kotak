

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

"""
Core logic for Nifty Breakout Strategy.
Handles Supertrend calculation and Signal Generation.
"""

from lib.utils.indicators import calculate_supertrend

def process_market_data(df, period: int, multiplier: float):
    """
    Calculates Supertrend on the dataframe.
    
    Args:
        df: DataFrame with OHLCV data.
        period: ATR Period.
        multiplier: Factor.
        
    Returns:
        tuple: (trend_direction, supertrend_value, close_price)
    """
    if df is None or df.empty:
        return 0, 0.0, 0.0

    trend, st_value = calculate_supertrend(df, period, multiplier)
    close_price = df['close'].iloc[-1]
    
    return trend, st_value, close_price

def check_entry_signal(ltp: float, prev_high: float, prev_low: float, supertrend_trend: int) -> str:
    """
    Checks if current price breaks Yesterday's High/Low with Supertrend confirmation.
    
    Args:
        ltp: Last Traded Price.
        prev_high: Yesterday's High.
        prev_low: Yesterday's Low.
        supertrend_trend: 1 (Bullish) or -1 (Bearish).
        
    Returns:
        str: "BUY_CE" (Bullish Breakout), "BUY_PE" (Bearish Breakout), or None.
        Note: The strategy SELLS options based on direction.
        But signal is directional.
        Let's unify: Return "BULLISH" or "BEARISH".
    """
    signal = None
    
    # Bullish Scenario: Breakout above Prev High + Supertrend Positive
    if ltp > prev_high and supertrend_trend == 1:
        signal = "BULLISH"
        
    # Bearish Scenario: Breakdown below Prev Low + Supertrend Negative
    elif ltp < prev_low and supertrend_trend == -1:
        signal = "BEARISH"
        
    return signal

def calculate_strikes(ltp: float, offset: int, step: int = 50) -> tuple:
    """
    Calculates strike prices based on LTP and offset.
    For Selling: Select OTM (Out of The Money).
    
    Bullish (Sell PE): Strike < LTP (OTM Put) -> Round Down - (Offset * Step)
    Bearish (Sell CE): Strike > LTP (OTM Call) -> Round Up + (Offset * Step)
    
    Wait, user said: "the CE or PE should be OTM (2 strikes offset from ATM)"
    
    ATM is closest to LTP.
    If LTP = 24120 -> ATM = 24100.
    
    Sell PE (Bullish View): We want OTM Put (Lower Strike).
    ATM - (Offset * Step) = 24100 - (2 * 50) = 24000 PE.
    
    Sell CE (Bearish View): We want OTM Call (Higher Strike).
    ATM + (Offset * Step) = 24100 + (2 * 50) = 24200 CE.
    """
    # Round to nearest step (ATM)
    atm_strike = round(ltp / step) * step
    
    pe_strike = atm_strike - (offset * step)
    ce_strike = atm_strike + (offset * step)
    
    return ce_strike, pe_strike

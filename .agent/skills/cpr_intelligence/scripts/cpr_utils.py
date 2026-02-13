def calculate_cpr(high: float, low: float, close: float) -> dict:
    """
    Calculate Central Pivot Range (CPR) and standard Pivot levels.
    
    Args:
        high: Previous interval's high price
        low: Previous interval's low price
        close: Previous interval's close price
        
    Returns:
        dict: Containing P, TC, BC and R1, S1, R2, S2, R3, S3
    """
    pivot = (high + low + close) / 3
    bc = (high + low) / 2
    tc = (pivot - bc) + pivot
    
    # Standard Pivot Levels
    r1 = (2 * pivot) - low
    s1 = (2 * pivot) - high
    r2 = pivot + (high - low)
    s2 = pivot - (high - low)
    
    # R3 and S3
    r3 = high + 2 * (pivot - low)
    s3 = low - 2 * (high - pivot)
    
    return {
        'P': round(pivot, 2),
        'TC': round(tc, 2),
        'BC': round(bc, 2),
        'R1': round(r1, 2),
        'S1': round(s1, 2),
        'R2': round(r2, 2),
        'S2': round(s2, 2),
        'R3': round(r3, 2),
        'S3': round(s3, 2),
        # Helper for sorting
        'CPR_TOP': round(max(tc, bc), 2),
        'CPR_BOTTOM': round(min(tc, bc), 2)
    }

def get_weekly_ohlc(df_daily) -> tuple:
    """
    Helper to extract previous week's OHLC from daily candles.
    Assuming df_daily is sorted by date.
    """
    # This logic would depend on the dataframe structure
    # In a real scenario, we'd resample or extract based on ISO week
    pass

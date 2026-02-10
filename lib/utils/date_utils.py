from datetime import datetime, timedelta, time

def calculate_days_to_expiry(expiry_date: str) -> float:
    """
    Calculate days to expiry (including fractional days).
    Assumes expiry is at 15:30 on the given date (YYYY-MM-DD).
    """
    now = datetime.now()
    if isinstance(expiry_date, str):
        expiry_datetime = datetime.strptime(expiry_date, "%Y-%m-%d")
    else:
        expiry_datetime = expiry_date
        
    expiry_datetime = expiry_datetime.replace(hour=15, minute=30)
    time_diff = expiry_datetime - now
    days_to_expiry = time_diff.total_seconds() / (24 * 3600)
    return max(0.0, days_to_expiry)

def get_next_thursday(date: datetime = None) -> datetime:
    """
    Get the next Thursday from a given date.
    If the date is a Thursday, returns the *next* Thursday.
    """
    if date is None:
        date = datetime.now()
        
    days_ahead = 3 - date.weekday()
    if days_ahead <= 0: # Target day already happened this week
        days_ahead += 7
        
    return date + timedelta(days=days_ahead)

def get_last_thursday(year: int, month: int) -> datetime:
    """
    Get the last Thursday of a given month and year.
    Used for Monthly Expiry calculation.
    """
    import calendar
    
    # Get total days in month
    _, last_day = calendar.monthrange(year, month)
    
    # Start from last day and count back
    last_date = datetime(year, month, last_day)
    
    # 0 = Monday, ... 3 = Thursday
    offset = (last_date.weekday() - 3) % 7
    
    return last_date - timedelta(days=offset)

def is_market_open() -> bool:
    """
    Check if the market is currently open (NSE Equities/Derivatives).
    Returns True if Mon-Fri between 09:15 and 15:30.
    """
    now = datetime.now()
    
    # Check Weekday (Mon=0, Sun=6)
    if now.weekday() > 4:
        return False
        
    # Check Time (09:15 to 15:30)
    current_time = now.time()
    market_start = time(9, 15)
    market_end = time(15, 30)
    
    return market_start <= current_time <= market_end

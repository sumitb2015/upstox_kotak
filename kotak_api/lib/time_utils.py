"""
Time utilities for trading strategies.

Provides time-related helpers for:
- Market hours checking
- Trading window validation
- Auto-exit time checks
"""

from datetime import datetime, time as dt_time


def is_market_hours():
    """
    Check if current time is within market hours (9:15 AM - 3:30 PM IST).
    
    Returns:
        bool: True if within market hours, False otherwise
    """
    now = datetime.now()
    market_open = dt_time(9, 15)
    market_close = dt_time(15, 30)
    current_time = now.time()
    
    return market_open <= current_time <= market_close


def is_trading_time(start_time="09:20", end_time="15:15"):
    """
    Check if within custom trading window.
    
    Args:
        start_time (str): Start time in "HH:MM" format (24-hour)
        end_time (str): End time in "HH:MM" format (24-hour)
        
    Returns:
        bool: True if within trading window, False otherwise
    
    Example:
        >>> is_trading_time("09:20", "15:15")
        True  # If current time is 10:30 AM
    """
    try:
        current_time = datetime.now().time()
        start = datetime.strptime(start_time, "%H:%M").time()
        end = datetime.strptime(end_time, "%H:%M").time()
        
        return start <= current_time <= end
    except ValueError:
        print(f"⚠️ Invalid time format. Use HH:MM (24-hour)")
        return False


def should_auto_exit(exit_time="15:00"):
    """
    Check if auto-exit time has been reached.
    
    Args:
        exit_time (str): Exit time in "HH:MM" format (24-hour)
        
    Returns:
        bool: True if current time >= exit time, False otherwise
    
    Example:
        >>> should_auto_exit("15:00")
        True  # If current time is 3:05 PM
    """
    try:
        current_time = datetime.now().time()
        exit = datetime.strptime(exit_time, "%H:%M").time()
        
        return current_time >= exit
    except ValueError:
        print(f"⚠️ Invalid time format. Use HH:MM (24-hour)")
        return False


def time_until_market_close():
    """
    Calculate minutes remaining until market close (3:30 PM).
    
    Returns:
        int: Minutes until market close (negative if after close)
    """
    now = datetime.now()
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    
    diff = (market_close - now).total_seconds()
    return int(diff / 60)


def time_until(target_time="15:00"):
    """
    Calculate minutes until a target time.
    
    Args:
        target_time (str): Target time in "HH:MM" format (24-hour)
        
    Returns:
        int: Minutes until target time (negative if past target)
    """
    try:
        now = datetime.now()
        target = datetime.strptime(target_time, "%H:%M").time()
        target_dt = now.replace(hour=target.hour, minute=target.minute, second=0, microsecond=0)
        
        diff = (target_dt - now).total_seconds()
        return int(diff / 60)
    except ValueError:
        print(f"⚠️ Invalid time format. Use HH:MM (24-hour)")
        return 0


def get_current_time_str(format="%H:%M:%S"):
    """
    Get current time as formatted string.
    
    Args:
        format (str, optional): Time format. Defaults to "%H:%M:%S".
        
    Returns:
        str: Formatted time string
    """
    return datetime.now().strftime(format)


def is_near_market_close(minutes_before=15):
    """
    Check if we're near market close.
    
    Args:
        minutes_before (int, optional): Minutes before close to trigger. Defaults to 15.
        
    Returns:
        bool: True if within specified minutes of market close
    """
    minutes_left = time_until_market_close()
    return 0 <= minutes_left <= minutes_before

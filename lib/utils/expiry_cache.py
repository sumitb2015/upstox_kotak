"""
Expiry Cache Utility

Fetches, caches, and manages option expiry dates from Upstox API.
Classifies expiries as weekly or monthly for proper Kotak symbol generation.

Usage:
    from lib.utils.expiry_cache import get_expiry_for_strategy
    
    expiry_date = get_expiry_for_strategy(
        access_token=token,
        expiry_type="monthly",  # or "current_week", "next_week"
        instrument="NIFTY"
    )
"""

import os
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Literal
from calendar import monthrange

# Import Upstox API function
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from lib.api.option_chain import get_expiries


def get_data_dir() -> str:
    """Get or create data directory for expiry cache."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(base_dir, 'data', 'expiries')
    
    if not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)
    
    return data_dir


def is_cache_stale(instrument: str = "NIFTY", year: Optional[int] = None, max_age_days: int = 7) -> bool:
    """
    Check if cache file is stale (older than max_age_days).
    
    Args:
        instrument: Instrument name
        year: Year to check
        max_age_days: Maximum age in days before cache is considered stale
        
    Returns:
        True if cache is stale or doesn't exist, False otherwise
    """
    if year is None:
        year = datetime.now().year
    
    data_dir = get_data_dir()
    filename = f"{instrument.lower()}_expiries_{year}.csv"
    filepath = os.path.join(data_dir, filename)
    
    if not os.path.exists(filepath):
        return True
    
    try:
        file_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(filepath))
        return file_age.days > max_age_days
    except:
        return True


def fetch_and_cache_expiries(access_token: str, instrument: str = "NIFTY", year: Optional[int] = None) -> Optional[pd.DataFrame]:
    """
    Fetch all expiries from Upstox API and cache to CSV.
    
    Args:
        access_token: Upstox API access token
        instrument: Instrument name (default: "NIFTY")
        year: Year to cache (default: current year)
        
    Returns:
        DataFrame with columns: date, type, month, year
        None if fetch failed
        
    Raises:
        ValueError: If instrument is not supported
    """
    if year is None:
        year = datetime.now().year
    
    print(f"📅 Fetching {instrument} expiries from Upstox API for {year}...")
    
    # Validate instrument
    instrument_key_map = {
        "NIFTY": "NSE_INDEX|Nifty 50",
        "BANKNIFTY": "NSE_INDEX|Nifty Bank",
        "FINNIFTY": "NSE_INDEX|Nifty Fin Service"
    }
    
    instrument_upper = instrument.upper()
    if instrument_upper not in instrument_key_map:
        raise ValueError(f"Unsupported instrument: {instrument}. Supported: {list(instrument_key_map.keys())}")
    
    instrument_key = instrument_key_map[instrument_upper]
    
    # Fetch expiries from Upstox
    try:
        expiries_list = get_expiries(access_token, instrument_key)
    except Exception as e:
        print(f"❌ API error fetching expiries: {e}")
        return None
    
    if not expiries_list:
        print(f"❌ No expiries returned for {instrument}")
        return None
    
    # Filter for the specified year and group by month
    expiries_by_month = {}
    for expiry_str in expiries_list:
        try:
            # Handle both string and datetime object formats
            if isinstance(expiry_str, str):
                expiry_dt = datetime.strptime(expiry_str, "%Y-%m-%d")
            elif isinstance(expiry_str, datetime):
                expiry_dt = expiry_str
            else:
                # Try to convert to datetime if it's a date object
                expiry_dt = datetime.combine(expiry_str, datetime.min.time()) if hasattr(expiry_str, 'year') else None
                if expiry_dt is None:
                    print(f"⚠️ Skipping invalid date format: {expiry_str}")
                    continue
        except (ValueError, TypeError) as e:
            print(f"⚠️ Skipping invalid date format: {expiry_str} ({e})")
            continue
        
        if expiry_dt.year == year:
            month_key = expiry_dt.month
            if month_key not in expiries_by_month:
                expiries_by_month[month_key] = []
            # Store as string in YYYY-MM-DD format
            expiry_str_formatted = expiry_dt.strftime("%Y-%m-%d")
            expiries_by_month[month_key].append(expiry_str_formatted)
    
    if not expiries_by_month:
        print(f"⚠️ No expiries found for {instrument} in {year}")
        return None
    
    # Classify expiries: Last expiry of each month = Monthly
    expiries_data = []
    for month, month_expiries in expiries_by_month.items():
        # Sort expiries in the month
        month_expiries.sort()
        
        # All except last are weekly, last is monthly
        for i, expiry_str in enumerate(month_expiries):
            expiry_dt = datetime.strptime(expiry_str, "%Y-%m-%d")
            
            # Last expiry of the month = Monthly
            if i == len(month_expiries) - 1:
                expiry_type = "monthly"
            else:
                expiry_type = "weekly"
            
            expiries_data.append({
                'date': expiry_str,
                'type': expiry_type,
                'month': expiry_dt.month,
                'year': expiry_dt.year
            })
    
    # Create DataFrame and sort by date
    df = pd.DataFrame(expiries_data)
    df = df.sort_values('date').reset_index(drop=True)
    
    # Save to CSV
    data_dir = get_data_dir()
    filename = f"{instrument.lower()}_expiries_{year}.csv"
    filepath = os.path.join(data_dir, filename)
    
    try:
        df.to_csv(filepath, index=False)
        print(f"✅ Cached {len(df)} expiries to {filepath}")
        print(f"   Weekly: {len(df[df['type'] == 'weekly'])}, Monthly: {len(df[df['type'] == 'monthly'])}")
    except Exception as e:
        print(f"⚠️ Failed to save cache: {e}")
    
    return df


def load_expiries_from_cache(instrument: str = "NIFTY", year: Optional[int] = None) -> Optional[pd.DataFrame]:
    """
    Load expiries from cached CSV file.
    
    Args:
        instrument: Instrument name (default: "NIFTY")
        year: Year to load (default: current year)
        
    Returns:
        DataFrame with expiry data or None if cache doesn't exist
    """
    if year is None:
        year = datetime.now().year
    
    data_dir = get_data_dir()
    filename = f"{instrument.lower()}_expiries_{year}.csv"
    filepath = os.path.join(data_dir, filename)
    
    if not os.path.exists(filepath):
        return None
    
    try:
        df = pd.read_csv(filepath)
        print(f"📂 Loaded {len(df)} expiries from cache: {filename}")
        return df
    except Exception as e:
        print(f"⚠️ Error loading cache: {e}")
        return None


def get_expiry_by_type(
    expiries_df: pd.DataFrame,
    expiry_type: Literal["current_week", "next_week", "monthly"],
    reference_date: Optional[datetime] = None
) -> str:
    """
    Select expiry based on type.
    
    Args:
        expiries_df: DataFrame with expiry data
        expiry_type: Type of expiry to select
        reference_date: Reference date (default: now)
        
    Returns:
        Expiry date string in YYYY-MM-DD format
        
    Raises:
        ValueError: If expiry cannot be found
    """
    if reference_date is None:
        reference_date = datetime.now()
    
    ref_date = reference_date.date()
    
    # Convert date column to datetime
    expiries_df['date_dt'] = pd.to_datetime(expiries_df['date']).dt.date
    
    # Filter for future expiries
    future_expiries = expiries_df[expiries_df['date_dt'] >= ref_date].copy()
    
    if future_expiries.empty:
        raise ValueError(f"No future expiries found after {ref_date}")
    
    # Sort by date
    future_expiries = future_expiries.sort_values('date_dt').reset_index(drop=True)
    
    if expiry_type == "current_week":
        # Get nearest expiry (within next 7 days from today)
        # This handles case where monthly expiry is the only option in current week
        week_end = ref_date + timedelta(days=7)
        current_week_expiries = future_expiries[future_expiries['date_dt'] <= week_end]
        
        if current_week_expiries.empty:
            # No expiry in current week, fall back to nearest future expiry
            return future_expiries.iloc[0]['date']
        
        # Return nearest expiry in current week (could be weekly or monthly)
        return current_week_expiries.iloc[0]['date']
    
    elif expiry_type == "next_week":
        # Get second nearest expiry (skip the first one)
        if len(future_expiries) < 2:
            raise ValueError("Next week expiry not available")
        return future_expiries.iloc[1]['date']
    
    elif expiry_type == "monthly":
        # Get nearest monthly expiry (must be type='monthly')
        monthly = future_expiries[future_expiries['type'] == 'monthly']
        if monthly.empty:
            raise ValueError("No monthly expiries found")
        return monthly.iloc[0]['date']
    
    else:
        raise ValueError(f"Invalid expiry_type: {expiry_type}")


def get_expiry_for_strategy(
    access_token: str,
    expiry_type: Literal["current_week", "next_week", "monthly"],
    instrument: str = "NIFTY",
    force_refresh: bool = False,
    check_staleness: bool = True
) -> str:
    """
    Main function to get expiry for a strategy.
    
    This function:
    1. Tries to load from cache
    2. If cache doesn't exist, is stale, or force_refresh=True, fetches from API
    3. Returns the selected expiry based on type
    
    Args:
        access_token: Upstox API access token
        expiry_type: Type of expiry ("current_week", "next_week", "monthly")
        instrument: Instrument name (default: "NIFTY")
        force_refresh: Force refresh from API (default: False)
        check_staleness: Check if cache is stale (default: True)
        
    Returns:
        Expiry date string in YYYY-MM-DD format
        
    Raises:
        ValueError: If expiry cannot be determined or instrument not supported
    """
    current_date = datetime.now()
    year = current_date.year
    
    # Handle year rollover: If we're in December and looking for next week/monthly,
    # we might need next year's expiries too
    years_to_check = [year]
    if current_date.month == 12:
        years_to_check.append(year + 1)
    
    # Try loading from cache
    expiries_df = None
    if not force_refresh:
        # Check if cache is stale
        if check_staleness and is_cache_stale(instrument, year):
            print(f"⚠️ Cache is stale, will refresh from API")
        else:
            expiries_df = load_expiries_from_cache(instrument, year)
            
            # If in December, also load next year's cache if available
            if current_date.month == 12:
                next_year_df = load_expiries_from_cache(instrument, year + 1)
                if next_year_df is not None:
                    expiries_df = pd.concat([expiries_df, next_year_df], ignore_index=True) if expiries_df is not None else next_year_df
    
    # If cache doesn't exist or force refresh, fetch from API
    if expiries_df is None or expiries_df.empty:
        for yr in years_to_check:
            yr_df = fetch_and_cache_expiries(access_token, instrument, yr)
            if yr_df is not None:
                expiries_df = pd.concat([expiries_df, yr_df], ignore_index=True) if expiries_df is not None else yr_df
        
        if expiries_df is None or expiries_df.empty:
            raise ValueError(f"Failed to fetch expiries for {instrument}")
    
    # Select expiry based on type
    expiry_date = get_expiry_by_type(expiries_df, expiry_type)
    
    return expiry_date


# Convenience function for debugging
def print_expiry_calendar(instrument: str = "NIFTY", year: Optional[int] = None):
    """Print formatted expiry calendar for debugging."""
    df = load_expiries_from_cache(instrument, year)
    
    if df is None:
        print(f"No cache found for {instrument}")
        return
    
    print(f"\n{instrument} Expiry Calendar - {year or datetime.now().year}")
    print("=" * 60)
    
    for month in range(1, 13):
        month_expiries = df[df['month'] == month]
        if not month_expiries.empty:
            print(f"\n{datetime(2000, month, 1).strftime('%B')}:")
            for _, row in month_expiries.iterrows():
                print(f"  {row['date']} - {row['type'].upper()}")

def get_monthly_expiry(access_token, instrument="NIFTY"):
    """
    Convenience function to get the nearest monthly expiry.
    """
    return get_expiry_for_strategy(access_token, expiry_type="monthly", instrument=instrument)

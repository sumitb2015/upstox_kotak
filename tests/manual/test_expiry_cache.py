"""
Test script for expiry cache library

This script tests the expiry cache functionality:
1. Fetches expiries from Upstox API
2. Caches them to CSV
3. Tests expiry classification (weekly vs monthly)
4. Tests expiry selection for different types
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from lib.utils.expiry_cache import (
    get_expiry_for_strategy,
    print_expiry_calendar,
    load_expiries_from_cache,
    fetch_and_cache_expiries
)
from lib.core.authentication import check_existing_token, perform_authentication, save_access_token


def test_expiry_cache():
    """Test expiry cache functionality."""
    
    print("=" * 60)
    print("Testing Expiry Cache Library")
    print("=" * 60)
    
    # 1. Get access token
    print("\n1️⃣ Getting access token...")
    if not check_existing_token():
        try:
            token = perform_authentication()
            save_access_token(token)
        except Exception as e:
            print(f"❌ Authentication failed: {e}")
            return
    
    with open("lib/core/accessToken.txt", "r") as f:
        token = f.read().strip()
    
    print("✅ Access token loaded")
    
    # 2. Test fetching and caching
    print("\n2️⃣ Testing fetch and cache...")
    try:
        df = fetch_and_cache_expiries(token, instrument="NIFTY", year=2026)
        if df is not None:
            print(f"✅ Fetched and cached {len(df)} expiries")
            print(f"   Weekly: {len(df[df['type'] == 'weekly'])}")
            print(f"   Monthly: {len(df[df['type'] == 'monthly'])}")
        else:
            print("❌ Failed to fetch expiries")
            return
    except Exception as e:
        print(f"❌ Error: {e}")
        return
    
    # 3. Test loading from cache
    print("\n3️⃣ Testing cache loading...")
    try:
        df = load_expiries_from_cache(instrument="NIFTY", year=2026)
        if df is not None:
            print(f"✅ Loaded {len(df)} expiries from cache")
        else:
            print("❌ Failed to load from cache")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # 4. Test expiry selection
    print("\n4️⃣ Testing expiry selection...")
    
    test_cases = [
        ("current_week", "Current Week"),
        ("next_week", "Next Week"),
        ("monthly", "Monthly")
    ]
    
    for expiry_type, label in test_cases:
        try:
            expiry = get_expiry_for_strategy(
                access_token=token,
                expiry_type=expiry_type,
                instrument="NIFTY",
                force_refresh=False
            )
            print(f"✅ {label}: {expiry}")
        except Exception as e:
            print(f"❌ {label} failed: {e}")
    
    # 5. Print calendar
    print("\n5️⃣ Expiry Calendar:")
    print_expiry_calendar(instrument="NIFTY", year=2026)
    
    print("\n" + "=" * 60)
    print("✅ All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    test_expiry_cache()

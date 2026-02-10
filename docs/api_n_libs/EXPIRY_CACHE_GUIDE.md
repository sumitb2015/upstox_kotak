"""
Expiry Cache Library - Quick Start Guide

This library provides a simple, plug-and-play solution for managing option expiries
across all trading strategies.

## Basic Usage

```python
from utils.expiry_cache import get_expiry_for_strategy

# In your strategy's __init__:
self.expiry_type = "monthly"  # or "current_week", "next_week"

# In your strategy's initialize():
expiry_date = get_expiry_for_strategy(
    access_token=self.access_token,
    expiry_type=self.expiry_type,
    instrument="NIFTY"  # or "BANKNIFTY", "FINNIFTY"
)

# Use the expiry date
self.expiry_date = expiry_date
self.expiry_date_datetime = datetime.strptime(expiry_date, "%Y-%m-%d")
```

## Features

✅ **Automatic Caching**: Fetches once, uses cache for 7 days
✅ **Weekly/Monthly Classification**: Last expiry of month = monthly
✅ **Year Rollover Handling**: Automatically handles December → January
✅ **Staleness Check**: Refreshes cache if older than 7 days
✅ **Error Handling**: Graceful fallbacks and clear error messages
✅ **Multi-Instrument**: Supports NIFTY, BANKNIFTY, FINNIFTY

## Advanced Options

```python
# Force refresh from API (ignore cache)
expiry_date = get_expiry_for_strategy(
    access_token=token,
    expiry_type="monthly",
    instrument="NIFTY",
    force_refresh=True  # Bypass cache
)

# Disable staleness check (use cache even if old)
expiry_date = get_expiry_for_strategy(
    access_token=token,
    expiry_type="current_week",
    instrument="NIFTY",
    check_staleness=False  # Don't check age
)
```

## Expiry Types

- **`current_week`**: Nearest weekly expiry (excludes monthly)
- **`next_week`**: Second weekly expiry (excludes monthly)
- **`monthly`**: Nearest monthly expiry (last expiry of month)

## Cache Location

Expiries are cached in: `data/expiries/<instrument>_expiries_<year>.csv`

Example: `data/expiries/nifty_expiries_2026.csv`

## Error Handling

The library raises `ValueError` in these cases:
- Unsupported instrument
- No expiries found
- API fetch failed
- Invalid expiry type

Always wrap in try-except:

```python
try:
    expiry_date = get_expiry_for_strategy(
        access_token=token,
        expiry_type="monthly",
        instrument="NIFTY"
    )
except ValueError as e:
    print(f"Failed to get expiry: {e}")
    return False
```

## Complete Strategy Example

```python
from utils.expiry_cache import get_expiry_for_strategy
from datetime import datetime

class MyStrategy:
    def __init__(self, access_token, expiry_type="current_week"):
        self.access_token = access_token
        self.expiry_type = expiry_type
        self.expiry_date = None
        
    def initialize(self):
        # Get expiry using the library
        try:
            expiry_str = get_expiry_for_strategy(
                access_token=self.access_token,
                expiry_type=self.expiry_type,
                instrument="NIFTY"
            )
            
            self.expiry_date = expiry_str
            self.expiry_date_datetime = datetime.strptime(expiry_str, "%Y-%m-%d")
            
            print(f"✅ Selected {self.expiry_type} expiry: {expiry_str}")
            return True
            
        except ValueError as e:
            print(f"❌ Expiry selection failed: {e}")
            return False
```

## Testing

Run the test script to verify:

```bash
python test_expiry_cache.py
```

This will:
1. Fetch expiries from Upstox
2. Cache to CSV
3. Test all expiry types
4. Display expiry calendar

## Debugging

Print the expiry calendar:

```python
from utils.expiry_cache import print_expiry_calendar

print_expiry_calendar(instrument="NIFTY", year=2026)
```

Output:
```
NIFTY Expiry Calendar - 2026
============================================================

January:
  2026-01-20 - WEEKLY
  2026-01-27 - MONTHLY

February:
  2026-02-03 - WEEKLY
  2026-02-10 - WEEKLY
  2026-02-17 - WEEKLY
  2026-02-24 - MONTHLY
...
```
"""

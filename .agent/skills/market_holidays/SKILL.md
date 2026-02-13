---
name: Market Holidays Skill
description: Instructions for checking market trading holidays using the Upstox API.
---

# Market Holidays Skill

This skill details how to fetch and interpret market holiday data to prevent trading on closed days.

## 📊 1. Core Concepts
Use the `lib.api.market_data` module to fetch the list of trading holidays for the current year.

- **Purpose**: Check if today is a trading holiday before initializing strategies.
- **Data Source**: Upstox API `/v2/market/holidays` endpoint.

## 🛠️ 2. Library Usage

### Fetching Market Holidays
```python
from lib.api.market_data import get_market_holidays

# Get list of holidays for the current year
holidays = get_market_holidays(access_token)

if holidays:
    print(f"Found {len(holidays)} holidays.")
    for h in holidays:
        # Note: The SDK object attributes may vary (e.g., _date vs date)
        # Use getattr for safety
        date = getattr(h, 'date', getattr(h, '_date', None))
        desc = getattr(h, 'description', getattr(h, '_description', 'Unknown'))
        
        print(f"Holiday: {date} - {desc}")
```

### Checking for Specific Date
To check if a specific date (e.g., today) is a holiday:

```python
import datetime

def is_trading_holiday(token):
    today = datetime.date.today()
    holidays = get_market_holidays(token)
    
    if holidays:
        for h in holidays:
            h_date = getattr(h, 'date', getattr(h, '_date', None))
            # Ensure h_date is a date object or comparable
            if isinstance(h_date, datetime.datetime):
                h_date = h_date.date()
                
            if h_date == today:
                description = getattr(h, 'description', getattr(h, '_description', 'Unknown'))
                return True, description
                
    return False, None

# Usage
is_holiday, reason = is_trading_holiday(access_token)
if is_holiday:
    print(f"Today is a holiday: {reason}")
else:
    print("Market is OPEN")
```

## 🚨 3. Key Notes
- **Attribute Access**: The `HolidayData` object returned by the SDK might use underscored attributes (`_date`, `_description`) instead of public ones. Always use `getattr` with a fallback or inspect the object structure during debugging.
- **Date Handling**: The API returns dates as `datetime` objects (usually with midnight time). Compare using `.date()` to match strictly by day.
- **Caching**: Holidays don't change often. You can fetch this once at startup and cache it.

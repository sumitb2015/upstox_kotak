"""
Test the fixed expiry selection logic
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from datetime import datetime
import pandas as pd
from lib.utils.expiry_cache import get_expiry_by_type

# Create test dataframe with current cache data
test_data = {
    'date': ['2026-01-20', '2026-01-27', '2026-02-03', '2026-02-10'],
    'type': ['weekly', 'monthly', 'weekly', 'weekly'],
    'month': [1, 1, 2, 2],
    'year': [2026, 2026, 2026, 2026]
}

df = pd.DataFrame(test_data)

# Test with different reference dates
test_scenarios = [
    ("2026-01-22", "Current date (22nd Jan)"),  # Today
    ("2026-01-20", "Expiry day (20th Jan)"),
    ("2026-01-21", "Day after expiry (21st Jan)"),
    ("2026-01-26", "Day before monthly (26th Jan)"),
    ("2026-01-27", "Monthly expiry day (27th Jan)"),
    ("2026-01-28", "Day after monthly (28th Jan)"),
]

print("=" * 80)
print("EXPIRY SELECTION TEST - FIXED LOGIC")
print("=" * 80)

print("\nAvailable Expiries:")
for _, row in df.iterrows():
    print(f"  {row['date']} - {row['type'].upper()}")

print("\n" + "=" * 80)
print("TEST RESULTS")
print("=" * 80)

for test_date_str, description in test_scenarios:
    test_date = datetime.strptime(test_date_str, "%Y-%m-%d")
    
    print(f"\n{description} ({test_date_str}):")
    print("-" * 80)
    
    try:
        current_week = get_expiry_by_type(df.copy(), "current_week", test_date)
        print(f"  current_week: {current_week}")
    except Exception as e:
        print(f"  current_week: ERROR - {e}")
    
    try:
        next_week = get_expiry_by_type(df.copy(), "next_week", test_date)
        print(f"  next_week:    {next_week}")
    except Exception as e:
        print(f"  next_week:    ERROR - {e}")
    
    try:
        monthly = get_expiry_by_type(df.copy(), "monthly", test_date)
        print(f"  monthly:      {monthly}")
    except Exception as e:
        print(f"  monthly:      ERROR - {e}")

print("\n" + "=" * 80)
print("EXPECTED BEHAVIOR FOR TODAY (2026-01-22):")
print("=" * 80)
print("""
current_week should return: 2026-01-27 (monthly)
  Reason: It's the nearest expiry within 7 days, even though labeled 'monthly'
  
next_week should return: 2026-02-03 (weekly)
  Reason: Second nearest expiry after skipping 2026-01-27

monthly should return: 2026-01-27 (monthly)
  Reason: Nearest expiry with type='monthly'
""")

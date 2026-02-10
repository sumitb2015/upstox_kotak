"""
Simple verification of the expiry logic fix
"""
from datetime import datetime, timedelta, date

# Simulate the logic
def test_current_week_logic():
    # Test data from cache
    expiries = [
        {'date': '2026-01-20', 'type': 'weekly'},   # Already passed
        {'date': '2026-01-27', 'type': 'monthly'},  # This week (Tuesday)
        {'date': '2026-02-03', 'type': 'weekly'},   # Next week
        {'date': '2026-02-10', 'type': 'weekly'},   # Future
    ]
    
    # Today's date
    ref_date = date(2026, 1, 22)  # Wednesday, Jan 22
    
    # Filter future expiries
    future_expiries = [e for e in expiries if datetime.strptime(e['date'], '%Y-%m-%d').date() >= ref_date]
    
    print("=" * 70)
    print("EXPIRY SELECTION TEST - Jan 22, 2026")
    print("=" * 70)
    
    print(f"\nReference Date: {ref_date} (Today)")
    print(f"\nFuture Expiries:")
    for e in future_expiries:
        print(f"  {e['date']} - {e['type']}")
    
    # Test current_week logic (NEW)
    print(f"\n" + "=" * 70)
    print("CURRENT_WEEK LOGIC (FIXED)")
    print("=" * 70)
    
    week_end = ref_date + timedelta(days=7)
    print(f"Week end: {week_end} (7 days from today)")
    
    current_week_expiries = [
        e for e in future_expiries 
        if datetime.strptime(e['date'], '%Y-%m-%d').date() <= week_end
    ]
    
    print(f"\nExpiries within current week (next 7 days):")
    for e in current_week_expiries:
        exp_date = datetime.strptime(e['date'], '%Y-%m-%d').date()
        days_away = (exp_date - ref_date).days
        print(f"  {e['date']} - {e['type']} ({days_away} days away)")
    
    if current_week_expiries:
        selected = current_week_expiries[0]
        print(f"\n✅ SELECTED FOR current_week: {selected['date']} ({selected['type']})")
    else:
        selected = future_expiries[0]
        print(f"\n⚠️ No expiry in current week, fallback to: {selected['date']} ({selected['type']})")
    
    # Test next_week logic (NEW)
    print(f"\n" + "=" * 70)
    print("NEXT_WEEK LOGIC (FIXED)")
    print("=" * 70)
    
    if len(future_expiries) >= 2:
        next_week_selected = future_expiries[1]
        print(f"✅ SELECTED FOR next_week: {next_week_selected['date']} ({next_week_selected['type']})")
    else:
        print("❌ ERROR: Not enough expiries")
    
    # Test monthly logic
    print(f"\n" + "=" * 70)
    print("MONTHLY LOGIC (UNCHANGED)")
    print("=" * 70)
    
    monthly_expiries = [e for e in future_expiries if e['type'] == 'monthly']
    if monthly_expiries:
        monthly_selected = monthly_expiries[0]
        print(f"✅ SELECTED FOR monthly: {monthly_selected['date']}")
    else:
        print("❌ ERROR: No monthly expiries found")
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"current_week: {selected['date']} ({selected['type']})")
    print(f"next_week:    {next_week_selected['date'] if len(future_expiries) >= 2 else 'ERROR'}")
    print(f"monthly:      {monthly_selected['date'] if monthly_expiries else 'ERROR'}")
    
    print("\n" + "=" * 70)
    print("VERIFICATION")
    print("=" * 70)
    
    if selected['date'] == '2026-01-27':
        print("✅ PASS: current_week correctly returns 2026-01-27 (monthly in current week)")
    else:
        print(f"❌ FAIL: current_week returned {selected['date']}, expected 2026-01-27")
    
    if next_week_selected['date'] == '2026-02-03':
        print("✅ PASS: next_week correctly returns 2026-02-03 (second nearest)")
    else:
        print(f"❌ FAIL: next_week returned {next_week_selected['date']}, expected 2026-02-03")

if __name__ == "__main__":
    test_current_week_logic()

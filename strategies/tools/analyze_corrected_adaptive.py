"""
CORRECTED Adaptive Threshold Analysis - Hybrid Approach
INVERTED LOGIC: Lower % far from expiry, higher % near expiry
"""

def get_max_point_loss_for_dte(dte, max_high=20.0, max_low=10.0):
    """Calculate max point loss for given DTE (inverted logic)"""
    if dte >= 7:
        return max_high
    elif dte >= 3:
        range_start = max_high
        range_end = (max_high + max_low) / 2
        return range_start - ((range_start - range_end) * (7 - dte) / 4)
    elif dte >= 1:
        range_start = (max_high + max_low) / 2
        range_end = max_low + 2
        return range_start - ((range_start - range_end) * (3 - dte) / 2)
    else:
        return max_low + (2 * dte)

def calculate_adaptive_threshold(dte, premium, iv=0.15, max_high=20.0, max_low=10.0):
    """Calculate adaptive threshold with CORRECTED inverted logic"""
    # Get max point loss
    max_point_loss = get_max_point_loss_for_dte(dte, max_high, max_low)
    
    # Calculate required percentage
    if premium > 0:
        calculated_pct = max_point_loss / premium
    else:
        calculated_pct = 0.08
    
    # Premium multiplier (inverted)
    if premium < 30:
        premium_mult = 1.2
    elif premium < 50:
        premium_mult = 1.1
    elif premium < 100:
        premium_mult = 1.0
    else:
        premium_mult = 1.0
    
    # IV multiplier (inverted)
    if iv > 0.25:
        iv_mult = 0.95
    elif iv > 0.12:
        iv_mult = 1.0
    else:
        iv_mult = 1.05
    
    adjusted_pct = calculated_pct * premium_mult * iv_mult
    
    # Clamp
    min_pct = 0.08
    max_pct = 0.25
    final_pct = max(min_pct, min(max_pct, adjusted_pct))
    
    return final_pct, max_point_loss

print("=" * 110)
print("CORRECTED ADAPTIVE THRESHOLD - HYBRID APPROACH ANALYSIS")
print("INVERTED LOGIC: Lower % far from expiry (limit losses), Higher % near expiry (reduce adjustments)")
print("=" * 110)

print("\n" + "=" * 110)
print("COMPARISON: OLD FIXED 15% vs NEW ADAPTIVE (Target: 20pt max far from expiry)")
print("=" * 110)
print(f"{'DTE':<8} {'Premium':<10} {'Fixed 15%':<15} {'Adaptive %':<15} {'Point Cap':<12} {'Actual Loss':<12} {'Benefit':<20}")
print("-" * 110)

scenarios = [
    (10, 250),
    (7, 200),
    (5, 140),
    (4, 100),
    (3, 90),
    (2, 60),
    (1, 45),
    (0.5, 30),
    (0.1, 20),
]

for dte, premium in scenarios:
    fixed_loss = premium * 0.15
    adaptive_pct, point_cap = calculate_adaptive_threshold(dte, premium)
    
    # Hybrid: use lower of percentage or point cap
    pct_loss = premium * adaptive_pct
    actual_loss = min(pct_loss, point_cap)
    
    difference = actual_loss - fixed_loss
    if difference < 0:
        benefit = f"BETTER ({difference:+.1f}pts)"
    elif difference > 0:
        benefit = f"Higher (+{difference:.1f}pts)"
    else:
        benefit = "SAME"
    
    print(f"{dte:<8.1f} {premium:<10.0f} {fixed_loss:<15.1f} {adaptive_pct*100:<15.1f}% {point_cap:<12.1f} {actual_loss:<12.1f} {benefit:<20}")

print("\n" + "=" * 110)

# Detailed scenarios
print("\n" + "=" * 110)
print("DETAILED SCENARIOS WITH CALCULATIONS")
print("=" * 110)

detailed_scenarios = [
    {"name": "Far from Expiry (10 DTE), High Premium", "dte": 10, "premium": 250, "iv": 0.18},
    {"name": "Mid-Range (5 DTE), Medium Premium", "dte": 5, "premium": 140, "iv": 0.16},
    {"name": "Near Expiry (1 DTE), Low Premium", "dte": 1, "premium": 45, "iv": 0.14},
    {"name": "Expiry Day (0.5 DTE), Very Low Premium", "dte": 0.5, "premium": 30, "iv": 0.12},
]

for scenario in detailed_scenarios:
    dte = scenario["dte"]
    premium = scenario["premium"]
    iv = scenario["iv"]
    
    adaptive_pct, point_cap = calculate_adaptive_threshold(dte, premium, iv)
    
    fixed_loss = premium * 0.15
    pct_loss = premium * adaptive_pct
    actual_loss = min(pct_loss, point_cap)
    trigger = premium + actual_loss
    
    print(f"\n{scenario['name']}")
    print(f"  Parameters: DTE={dte} days | Premium={premium} | IV={iv*100:.0f}%")
    print(f"  Point Cap for this DTE: {point_cap:.1f} points")
    print(f"  Calculated %: {adaptive_pct*100:.1f}%")
    print(f"  ")
    print(f"  OLD (Fixed 15%):")
    print(f"    - Loss before adjustment: {fixed_loss:.1f} points")
    print(f"    - Trigger at: {premium + fixed_loss:.1f}")
    print(f"  ")
    print(f"  NEW (Adaptive Hybrid):")
    print(f"    - % would give: {pct_loss:.1f} points")
    print(f"    - Point cap: {point_cap:.1f} points")
    print(f"    - ACTUAL loss (lower of both): {actual_loss:.1f} points")
    print(f"    - Trigger at: {trigger:.1f}")
    print(f"  ")
    print(f"  IMPROVEMENT: {fixed_loss - actual_loss:+.1f} points ({((fixed_loss - actual_loss)/fixed_loss*100):+.1f}%)")

print("\n" + "=" * 110)

# Premium progression
print("\n" + "=" * 110)
print("PREMIUM PROGRESSION EXAMPLE (10 DTE, Starting Premium = 250)")
print("=" * 110)
print(f"{'Current CP':<12} {'Fixed Trig':<15} {'Adaptive Trig':<18} {'Status':<20}")
print("-" * 70)

base_premium = 250
dte = 10

adaptive_pct, point_cap = calculate_adaptive_threshold(dte, base_premium)
pct_loss = base_premium * adaptive_pct
actual_loss = min(pct_loss, point_cap)

fixed_trigger = base_premium * 1.15
adaptive_trigger = base_premium + actual_loss

for increase in [0, 10, 15, 20, 25, 30, 35, 40]:
    current = base_premium + increase
    
    if current >= adaptive_trigger:
        status = "[ADJUST]"
    elif current >= fixed_trigger:
        status = "[OLD WOULD ADJUST]"
    else:
        status = "[SAFE]"
    
    print(f"{current:<12.0f} {fixed_trigger:<15.1f} {adaptive_trigger:<18.1f} {status:<20}")

print(f"\nFixed 15% triggers at: {base_premium} + {base_premium*0.15:.1f} = {fixed_trigger:.1f}")
print(f"Adaptive triggers at: {base_premium} + {actual_loss:.1f} = {adaptive_trigger:.1f}")
print(f"BENEFIT: {actual_loss - base_premium*0.15:+.1f} points less loss before adjustment")

print("\n" + "=" * 110)

# Point cap progression
print("\n" + "=" * 110)
print("POINT CAP PROGRESSION BY DTE")
print("=" * 110)
print(f"{'DTE':<10} {'Point Cap':<15} {'Purpose':<50}")
print("-" * 80)

for dte in [10, 7, 5, 4, 3, 2, 1, 0.5, 0.1]:
    point_cap = get_max_point_loss_for_dte(dte)
    
    if dte >= 7:
        purpose = "Far from expiry: Tight control on high premiums"
    elif dte >= 3:
        purpose = "Mid-range: Balanced control"
    elif dte >= 1:
        purpose = "Near expiry: Moderate control"
    else:
        purpose = "Expiry day: Looser (premiums are low anyway)"
    
    print(f"{dte:<10.1f} {point_cap:<15.1f} {purpose:<50}")

print("\n" + "=" * 110)

# Configuration guide
print("\n" + "=" * 110)
print("CONFIGURATION GUIDE")
print("=" * 110)

configs = [
    {
        "name": "CONSERVATIVE (Tight Control)",
        "max_high": 15,
        "max_low": 8,
        "desc": "Smaller losses, more frequent adjustments, higher transaction costs"
    },
    {
        "name": "BALANCED (Recommended)",
        "max_high": 20,
        "max_low": 10,
        "desc": "Good balance between loss control and transaction costs"
    },
    {
        "name": "AGGRESSIVE (Looser Control)",
        "max_high": 25,
        "max_low": 12,
        "desc": "Larger acceptable losses, fewer adjustments, lower transaction costs"
    },
]

for config in configs:
    print(f"\n{config['name']}:")
    print(f"  max_loss_points_dte_high = {config['max_high']}")
    print(f"  max_loss_points_dte_low = {config['max_low']}")
    print(f"  Impact: {config['desc']}")
    
    # Show example
    premium_10d = 250
    premium_1d = 45
    
    pct_10d, cap_10d = calculate_adaptive_threshold(10, premium_10d, max_high=config['max_high'], max_low=config['max_low'])
    loss_10d = min(premium_10d * pct_10d, cap_10d)
    
    pct_1d, cap_1d = calculate_adaptive_threshold(1, premium_1d, max_high=config['max_high'], max_low=config['max_low'])
    loss_1d = min(premium_1d * pct_1d, cap_1d)
    
    print(f"  Example: 10 DTE, 250 premium => {loss_10d:.1f} pts loss (vs 37.5 fixed)")
    print(f"  Example: 1 DTE, 45 premium => {loss_1d:.1f} pts loss (vs 6.75 fixed)")

print("\n" + "=" * 110)

# Key takeaways
print("\n" + "=" * 110)
print("KEY TAKEAWAYS")
print("=" * 110)

takeaways = [
    "1. INVERTED LOGIC (Corrected):",
    "   - Far from expiry (10 DTE): 8% threshold, 20pt cap => 20 pts loss (vs 37.5 old)",
    "   - Near expiry (0.5 DTE): 25% threshold, 10pt cap => 7.5 pts loss (vs 4.5 old)",
    "",
    "2. HYBRID APPROACH:",
    "   - Uses LOWER of: percentage-based OR point cap",
    "   - Ensures absolute rupee loss never exceeds configured limits",
    "",
    "3. BENEFIT FAR FROM EXPIRY:",
    "   - 250 premium: OLD 37.5pts => NEW 20pts = 47% REDUCTION in loss",
    "   - 200 premium: OLD 30pts => NEW 20pts = 33% REDUCTION in loss",
    "",
    "4. TRADE-OFF NEAR EXPIRY:",
    "   - Slightly higher point losses BUT fewer adjustments",
    "   - Saves on transaction costs (no adjustment for every 4-5pt move)",
    "",
    "5. CONFIGURABLE:",
    "   - Set your acceptable point loss (max_loss_points_dte_high)",
    "   - System automatically calculates optimal percentages",
]

for takeaway in takeaways:
    print(takeaway)

print("\n" + "=" * 110)

"""
Adaptive Threshold Comparison - Text-based Analysis
"""

def calculate_dte_factor(dte):
    """Calculate DTE-based threshold factor"""
    if dte >= 7:
        return 0.30
    elif dte >= 3:
        return 0.15 + (0.15 * (dte - 3) / 4)
    elif dte >= 1:
        return 0.10 + (0.05 * (dte - 1) / 2)
    else:
        return 0.08 + (0.02 * dte)

def get_premium_multiplier(premium):
    """Get premium-based multiplier"""
    if premium > 150:
        return 1.10
    elif premium > 100:
        return 1.05
    elif premium > 50:
        return 1.00
    elif premium > 30:
        return 0.95
    else:
        return 0.90

def get_iv_multiplier(iv):
    """Get IV-based multiplier"""
    if iv > 0.25:
        return 1.15
    elif iv > 0.18:
        return 1.05
    elif iv > 0.12:
        return 1.00
    else:
        return 0.95

def calculate_adaptive_threshold(dte, premium, iv):
    """Calculate adaptive threshold percentage"""
    dte_factor = calculate_dte_factor(dte)
    p_mult = get_premium_multiplier(premium)
    v_mult = get_iv_multiplier(iv)
    
    adaptive_pct = dte_factor * p_mult * v_mult
    adaptive_pct = min(0.30, max(0.08, adaptive_pct))
    
    return adaptive_pct

# Create comparison table
print("=" * 100)
print("ADAPTIVE THRESHOLD COMPARISON TABLE")
print("=" * 100)
print(f"{'DTE':<8} {'Fixed':<10} {'Adaptive':<12} {'High P+IV':<15} {'Low P+IV':<15} {'Benefit':<25}")
print("-" * 100)

for dte in [10, 7, 5, 3, 2, 1, 0.5, 0.1]:
    fixed = 0.15
    adaptive = calculate_dte_factor(dte)
    high_piv = min(0.30, max(0.08, adaptive * 1.10 * 1.15))
    low_piv = min(0.30, max(0.08, adaptive * 0.90 * 0.95))
    
    if adaptive > fixed:
        benefit = "UP: Fewer adjustments"
    elif adaptive < fixed:
        benefit = "DOWN: Tighter control"
    else:
        benefit = "SAME"
    
    print(f"{dte:<8.1f} {fixed*100:<10.1f}% {adaptive*100:<12.1f}% {high_piv*100:<15.1f}% {low_piv*100:<15.1f}% {benefit:<25}")

print("=" * 100)

# Detailed scenarios
print("\n" + "=" * 100)
print("DETAILED EXAMPLE SCENARIOS")
print("=" * 100)

scenarios = [
    {
        "name": "Scenario 1: Far from Expiry, High Premium, High Volatility",
        "dte": 10,
        "premium": 250,
        "iv": 0.28,
        "description": "Weekly options on Monday, high IV event (earnings, Fed meeting)"
    },
    {
        "name": "Scenario 2: Mid-Range, Medium Premium, Normal Volatility",
        "dte": 4,
        "premium": 80,
        "iv": 0.16,
        "description": "Weekly options on Tuesday, normal market conditions"
    },
    {
        "name": "Scenario 3: Near Expiry, Low Premium, Low Volatility",
        "dte": 0.5,
        "premium": 25,
        "iv": 0.10,
        "description": "Expiry day afternoon, low volatility range-bound market"
    },
    {
        "name": "Scenario 4: Monthly Expiry, Very High Premium",
        "dte": 15,
        "premium": 350,
        "iv": 0.22,
        "description": "Monthly options, 2+ weeks to expiry"
    },
]

for scenario in scenarios:
    dte = scenario["dte"]
    premium = scenario["premium"]
    iv = scenario["iv"]
    
    # Calculate adaptive threshold
    adaptive_pct = calculate_adaptive_threshold(dte, premium, iv)
    
    # Calculate threshold points
    fixed_threshold_pts = premium * 0.15
    adaptive_threshold_pts = min(30, premium * adaptive_pct)
    
    # Calculate multipliers for breakdown
    dte_factor = calculate_dte_factor(dte)
    p_mult = get_premium_multiplier(premium)
    v_mult = get_iv_multiplier(iv)
    
    print(f"\n{scenario['name']}")
    print(f"  Context: {scenario['description']}")
    print(f"  Parameters: DTE={dte:.1f} days | Premium={premium} | IV={iv*100:.1f}%")
    print(f"\n  Calculation Breakdown:")
    print(f"    - DTE Factor: {dte_factor*100:.1f}%")
    print(f"    - Premium Multiplier: {p_mult:.2f}x")
    print(f"    - IV Multiplier: {v_mult:.2f}x")
    print(f"    - Combined: {dte_factor*100:.1f}% × {p_mult:.2f} × {v_mult:.2f} = {adaptive_pct*100:.1f}%")
    print(f"\n  Threshold Comparison:")
    print(f"    - Fixed (15%): {fixed_threshold_pts:.1f} points")
    print(f"    - Adaptive ({adaptive_pct*100:.1f}%): {adaptive_threshold_pts:.1f} points")
    print(f"    - Difference: {adaptive_threshold_pts - fixed_threshold_pts:+.1f} points ({((adaptive_threshold_pts/fixed_threshold_pts - 1)*100):+.1f}%)")
    
    if adaptive_threshold_pts > fixed_threshold_pts:
        print(f"  [+] Impact: Fewer adjustments, reduced transaction costs, more room for market noise")
    else:
        print(f"  [+] Impact: Tighter control, better risk management, faster response to moves")

print("\n" + "=" * 100)

# Premium progression analysis
print("\n" + "=" * 100)
print("PREMIUM PROGRESSION ANALYSIS (Fixed vs Adaptive)")
print("=" * 100)

print("\nExample: Starting premium = 200, DTE = 5 days, Normal IV = 15%")
print("\nAs premium increases due to market move:")
print(f"{'Premium':<12} {'Fixed Trigger':<18} {'Adaptive Trigger':<20} {'Status':<15}")
print("-" * 70)

base_premium = 200
dte = 5
iv = 0.15

for increase in [0, 10, 20, 30, 40, 50, 60, 70]:
    current_premium = base_premium + increase
    
    fixed_trigger = base_premium * 1.15  # 15% increase
    
    adaptive_pct = calculate_adaptive_threshold(dte, base_premium, iv)
    adaptive_trigger = base_premium + min(30, base_premium * adaptive_pct)
    
    if current_premium >= adaptive_trigger:
        status = "[ADJUST]"
    elif current_premium >= fixed_trigger:
        status = "[FIXED ONLY]"
    else:
        status = "[SAFE]"
    
    print(f"{current_premium:<12} {fixed_trigger:<18.1f} {adaptive_trigger:<20.1f} {status:<15}")

print("\n[SAFE]: No adjustment needed")
print("[FIXED ONLY]: Old system would adjust, new system waits")
print("[ADJUST]: Both systems trigger adjustment")

print("\n" + "=" * 100)

# DTE progression analysis
print("\n" + "=" * 100)
print("DTE PROGRESSION ANALYSIS (Same Premium)")
print("=" * 100)

print("\nExample: Constant premium = 100, Normal IV = 15%")
print("Shows how threshold tightens as expiry approaches:")
print(f"\n{'DTE':<10} {'Adaptive %':<15} {'Trigger At':<15} {'Tightening':<20}")
print("-" * 65)

premium = 100
iv = 0.15

prev_trigger = None
for dte in [10, 7, 5, 3, 2, 1, 0.5, 0.1]:
    adaptive_pct = calculate_adaptive_threshold(dte, premium, iv)
    trigger = premium + min(30, premium * adaptive_pct)
    
    if prev_trigger:
        tightening = f"{prev_trigger - trigger:+.1f} pts"
    else:
        tightening = "Baseline"
    
    print(f"{dte:<10.1f} {adaptive_pct*100:<15.1f}% {trigger:<15.1f} {tightening:<20}")
    prev_trigger = trigger

print("\n" + "=" * 100)

# Summary
print("\n" + "=" * 100)
print("KEY INSIGHTS")
print("=" * 100)

insights = [
    "1. FAR FROM EXPIRY (7+ days):",
    "   - Threshold: 25-30% (vs fixed 15%)",
    "   - Benefit: Avoids premature adjustments on high-premium options",
    "   - Example: 250 premium → 325 trigger (vs 287 fixed) = 38 more points of buffer",
    "",
    "2. NEAR EXPIRY (0-2 days):",
    "   - Threshold: 8-12% (vs fixed 15%)",
    "   - Benefit: Tighter control when theta decay accelerates",
    "   - Example: 30 premium → 32.4 trigger (vs 34.5 fixed) = 2.1 points tighter",
    "",
    "3. HIGH VOLATILITY PERIODS:",
    "   - Multiplier: +15% on threshold",
    "   - Benefit: Avoids adjusting on noise during volatile markets",
    "   - Example: 20% base → 23% actual (more room for swings)",
    "",
    "4. LOW VOLATILITY PERIODS:",
    "   - Multiplier: -5% on threshold",
    "   - Benefit: Catches real moves faster in range-bound markets",
    "   - Example: 15% base → 14.25% actual (tighter control)",
    "",
    "5. PREMIUM-BASED ADAPTATION:",
    "   - High premiums (>150): +10% threshold (more absolute noise)",
    "   - Low premiums (<30): -10% threshold (less room for error)",
    "   - Prevents over-adjustment on low-value options",
]

for insight in insights:
    print(insight)

print("\n" + "=" * 100)
print("CONFIGURATION RECOMMENDATIONS")
print("=" * 100)

recommendations = [
    "CONSERVATIVE (Lower Risk, More Adjustments):",
    "  min_adjustment_pct = 0.06  # 6% near expiry",
    "  max_adjustment_pct = 0.25  # 25% far from expiry",
    "  max_adjustment_points = 25 # Tighter cap",
    "",
    "BALANCED (Default, Recommended):",
    "  min_adjustment_pct = 0.08  # 8% near expiry",
    "  max_adjustment_pct = 0.30  # 30% far from expiry",
    "  max_adjustment_points = 30 # Standard cap",
    "",
    "AGGRESSIVE (Higher Risk, Fewer Adjustments):",
    "  min_adjustment_pct = 0.10  # 10% near expiry",
    "  max_adjustment_pct = 0.35  # 35% far from expiry",
    "  max_adjustment_points = 40 # Wider cap",
]

for rec in recommendations:
    print(rec)

print("\n" + "=" * 100)

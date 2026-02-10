import matplotlib.pyplot as plt
import numpy as np

# Simulate DTE progression
dte_values = np.linspace(0, 10, 100)

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

# Calculate thresholds for different scenarios
fixed_threshold = [0.15] * len(dte_values)  # Old fixed 15%
adaptive_base = [calculate_dte_factor(dte) for dte in dte_values]

# Scenario 1: High Premium (>150), High IV (>25%)
adaptive_high_premium_high_iv = [calculate_dte_factor(dte) * 1.10 * 1.15 for dte in dte_values]
adaptive_high_premium_high_iv = [min(0.30, max(0.08, val)) for val in adaptive_high_premium_high_iv]

# Scenario 2: Low Premium (<30), Low IV (<12%)
adaptive_low_premium_low_iv = [calculate_dte_factor(dte) * 0.90 * 0.95 for dte in dte_values]
adaptive_low_premium_low_iv = [min(0.30, max(0.08, val)) for val in adaptive_low_premium_low_iv]

# Scenario 3: Medium Premium (50-100), Normal IV (12-18%)
adaptive_medium = [calculate_dte_factor(dte) * 1.00 * 1.00 for dte in dte_values]

# Create visualization
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))

# Plot 1: Threshold Percentage vs DTE
ax1.plot(dte_values, [x*100 for x in fixed_threshold], 'r--', linewidth=2, label='Fixed 15% (Old)', alpha=0.7)
ax1.plot(dte_values, [x*100 for x in adaptive_base], 'b-', linewidth=2.5, label='Adaptive Base (DTE Only)')
ax1.plot(dte_values, [x*100 for x in adaptive_high_premium_high_iv], 'g-', linewidth=2, label='High Premium + High IV', alpha=0.8)
ax1.plot(dte_values, [x*100 for x in adaptive_low_premium_low_iv], 'm-', linewidth=2, label='Low Premium + Low IV', alpha=0.8)
ax1.plot(dte_values, [x*100 for x in adaptive_medium], 'c-', linewidth=2, label='Medium Premium + Normal IV', alpha=0.8)

ax1.axhline(y=8, color='gray', linestyle=':', alpha=0.5, label='Min Threshold (8%)')
ax1.axhline(y=30, color='gray', linestyle=':', alpha=0.5, label='Max Threshold (30%)')
ax1.fill_between(dte_values, 8, 30, alpha=0.1, color='gray')

ax1.set_xlabel('Days to Expiry (DTE)', fontsize=12, fontweight='bold')
ax1.set_ylabel('Adjustment Threshold (%)', fontsize=12, fontweight='bold')
ax1.set_title('Adaptive Adjustment Threshold vs Days to Expiry', fontsize=14, fontweight='bold')
ax1.legend(loc='upper left', fontsize=10)
ax1.grid(True, alpha=0.3)
ax1.set_xlim(0, 10)
ax1.set_ylim(5, 35)

# Add annotations for key zones
ax1.annotate('Expiry Day\n(Tight Control)', xy=(0.5, 9), xytext=(1.5, 5),
            arrowprops=dict(arrowstyle='->', color='red', lw=1.5),
            fontsize=10, color='red', fontweight='bold')
ax1.annotate('Mid-Range\n(Balanced)', xy=(5, 20), xytext=(6.5, 25),
            arrowprops=dict(arrowstyle='->', color='blue', lw=1.5),
            fontsize=10, color='blue', fontweight='bold')
ax1.annotate('Far from Expiry\n(Avoid Noise)', xy=(8, 30), xytext=(7, 33),
            arrowprops=dict(arrowstyle='->', color='green', lw=1.5),
            fontsize=10, color='green', fontweight='bold')

# Plot 2: Absolute Threshold Points for Different Premium Levels
premium_levels = [250, 150, 80, 40, 25]
colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A', '#98D8C8']

for i, premium in enumerate(premium_levels):
    if premium > 150:
        multiplier = 1.10
    elif premium > 100:
        multiplier = 1.05
    elif premium > 50:
        multiplier = 1.00
    elif premium > 30:
        multiplier = 0.95
    else:
        multiplier = 0.90
    
    threshold_points = [premium * calculate_dte_factor(dte) * multiplier for dte in dte_values]
    # Apply 30-point cap
    threshold_points = [min(30, val) for val in threshold_points]
    
    ax2.plot(dte_values, threshold_points, linewidth=2.5, label=f'Premium = {premium}', color=colors[i])

ax2.axhline(y=30, color='red', linestyle='--', linewidth=2, alpha=0.7, label='Max Points Cap (30)')
ax2.set_xlabel('Days to Expiry (DTE)', fontsize=12, fontweight='bold')
ax2.set_ylabel('Adjustment Threshold (Points)', fontsize=12, fontweight='bold')
ax2.set_title('Absolute Threshold Points vs DTE (with 30-point cap)', fontsize=14, fontweight='bold')
ax2.legend(loc='upper left', fontsize=10)
ax2.grid(True, alpha=0.3)
ax2.set_xlim(0, 10)
ax2.set_ylim(0, 80)

# Add shaded region for capped zone
ax2.fill_between(dte_values, 30, 80, alpha=0.15, color='red', label='Capped Region')

plt.tight_layout()
plt.savefig('c:/algo/upstox/strategies/hybrid/adaptive_threshold_visualization.png', dpi=300, bbox_inches='tight')
print("✅ Visualization saved: adaptive_threshold_visualization.png")

# Create comparison table
print("\n" + "="*80)
print("ADAPTIVE THRESHOLD COMPARISON TABLE")
print("="*80)
print(f"{'DTE':<8} {'Fixed':<10} {'Adaptive':<12} {'High P+IV':<12} {'Low P+IV':<12} {'Benefit':<20}")
print("-"*80)

for dte in [10, 7, 5, 3, 2, 1, 0.5, 0.1]:
    fixed = 0.15
    adaptive = calculate_dte_factor(dte)
    high_piv = min(0.30, max(0.08, adaptive * 1.10 * 1.15))
    low_piv = min(0.30, max(0.08, adaptive * 0.90 * 0.95))
    
    if adaptive > fixed:
        benefit = "↑ Fewer adjustments"
    elif adaptive < fixed:
        benefit = "↓ Tighter control"
    else:
        benefit = "= Same"
    
    print(f"{dte:<8.1f} {fixed*100:<10.1f}% {adaptive*100:<12.1f}% {high_piv*100:<12.1f}% {low_piv*100:<12.1f}% {benefit:<20}")

print("="*80)

# Example scenarios
print("\n" + "="*80)
print("EXAMPLE SCENARIOS")
print("="*80)

scenarios = [
    {"name": "Far Expiry, High Premium", "dte": 10, "premium": 250, "iv": 0.28},
    {"name": "Mid Expiry, Medium Premium", "dte": 4, "premium": 80, "iv": 0.16},
    {"name": "Near Expiry, Low Premium", "dte": 0.5, "premium": 25, "iv": 0.10},
]

for scenario in scenarios:
    dte = scenario["dte"]
    premium = scenario["premium"]
    iv = scenario["iv"]
    
    # Calculate multipliers
    if premium > 150:
        p_mult = 1.10
    elif premium > 100:
        p_mult = 1.05
    elif premium > 50:
        p_mult = 1.00
    elif premium > 30:
        p_mult = 0.95
    else:
        p_mult = 0.90
    
    if iv > 0.25:
        v_mult = 1.15
    elif iv > 0.18:
        v_mult = 1.05
    elif iv > 0.12:
        v_mult = 1.00
    else:
        v_mult = 0.95
    
    dte_factor = calculate_dte_factor(dte)
    adaptive_pct = min(0.30, max(0.08, dte_factor * p_mult * v_mult))
    
    fixed_threshold_pts = premium * 0.15
    adaptive_threshold_pts = min(30, premium * adaptive_pct)
    
    print(f"\n{scenario['name']}:")
    print(f"  DTE: {dte} days | Premium: {premium} | IV: {iv*100:.1f}%")
    print(f"  Fixed Threshold: 15% = {fixed_threshold_pts:.1f} points")
    print(f"  Adaptive Threshold: {adaptive_pct*100:.1f}% = {adaptive_threshold_pts:.1f} points")
    print(f"  Difference: {adaptive_threshold_pts - fixed_threshold_pts:+.1f} points")
    print(f"  Impact: {'Fewer adjustments, less transaction cost' if adaptive_threshold_pts > fixed_threshold_pts else 'Tighter control, better risk management'}")

print("\n" + "="*80)

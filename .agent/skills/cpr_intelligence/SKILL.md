---
name: CPR Intelligence
description: Standardized logic for calculating Daily and Weekly Central Pivot Range (CPR) levels.
---

# 📐 CPR Intelligence Skill

This skill provides the standardized formulas and scripts for calculating **Central Pivot Range (CPR)** and associated **Pivot Points** (S1-R3) for different intervals.

## 🧮 Calculation Formulas

The CPR consists of three levels based on the **Previous Interval's** High, Low, and Close prices.

| Level | Calculation | Description |
| :--- | :--- | :--- |
| **Pivot (P)** | `(High + Low + Close) / 3` | The central anchor point |
| **Bottom Central (BC)** | `(High + Low) / 2` | Midpoint of the range |
| **Top Central (TC)** | `(Pivot - BC) + Pivot` | Mirror image of BC across Pivot |

**Important**: In UI/Charts, usually `TC` is displayed as the top and `BC` as the bottom, but mathematically `BC` can sometimes be higher than `TC`. Use `max(BC, TC)` and `min(BC, TC)` for range plotting.

### Standard Pivot Levels (Classic)
- **R1**: `(2 * Pivot) - Low`
- **S1**: `(2 * Pivot) - High`
- **R2**: `Pivot + (High - Low)`
- **S2**: `Pivot - (High - Low)`
- **R3**: `High + 2 * (Pivot - Low)`
- **S3**: `Low - 2 * (High - Pivot)`

## 📅 Supported Intervals

1. **Daily CPR**: Calculated using the **Previous Day's** High, Low, and Close.
2. **Weekly CPR**: Calculated using the **Previous Week's** High, Low, and Close.

## 🛠️ Usage

### Python Implementation
Always use the utility function to ensure consistency:

```python
from .agent.skills.cpr_intelligence.scripts.cpr_utils import calculate_cpr

# Get Daily CPR
daily_cpr = calculate_cpr(prev_high, prev_low, prev_close)

# Access levels
print(f"Pivot: {daily_cpr['P']}")
print(f"Range: {daily_cpr['TC']} - {daily_cpr['BC']}")
```

## 📝 Best Practices
- **Data Warmup**: For Weekly CPR, ensure you have fetched data covering at least the last 14 days to identify the previous week's boundaries correctly.
- **Expiry Handling**: When using CPR on options, ensure the levels are derived from the **Underlying (Spot or Future)**, not the option premium.
- **Trend Bias**:
    - **Narrow CPR**: Indicates low volatility and potential for a breakout move.
    - **Wide CPR**: Indicates high volatility and potential for a range-bound day.
    - **Price Location**: 
        - Above TC = Bullish
        - Below BC = Bearish
        - Inside CPR = Neutral/No-Trade Zone

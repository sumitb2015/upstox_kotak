---
name: Risk Management Skill
description: Instructions for implementing Hybrid Gated Stop Loss, Trailing SL, Pyramiding, and Step-Locking logic.
---

# Risk Management Skill - Algorithmic Trading

This skill provides the logic and patterns for advanced safety mechanisms used in the Upstox/Kotak trading systems.

## 🛡️ 1. Hybrid Gated Stop Loss
Prevents premature exits due to noise while protecting against directional crashes.

**Concept**:
- **Gate (Closed)**: If `Combined_P&L < 15%` loss, ignore individual leg SLs.
- **Gate (Open)**: If `Combined_P&L >= 15%` loss, trigger individual leg SLs at `20%`.
- **Override**: If any leg hits `30%` loss, exit immediately regardless of the gate.

### Implementation Pattern:
```python
combined_loss_pct = (ce_pnl + pe_pnl) / total_premium_entry
gate_open = combined_loss_pct >= 0.15

if gate_open:
    if leg_loss >= 0.20: exit_leg()
elif leg_loss >= 0.30:
    exit_leg() # Hard stop
```

## 📈 2. Pyramiding Logic (Trending Positions)
Adding lots to profitable trending legs.

**Guidelines**:
- **Trigger**: Add 1 lot for every 10% increase in profit relative to the previous entry.
- **Max Lots**: Cap at 3 additions.
- **TSL Tightening**: When pyramided, tighten TSL buffer from 20% to **10%**.

## 🔒 3. Step-Locking (Profit Protection)
Locks the Stop Loss to previous "rungs" of profit.

- When `Pyramid 1` is added, the SL for the entire position is locked at the **Break-even** price of `Entry 1`.
- When `Pyramid 2` is added, the SL is locked at the `Entry 1` profit level (the price where Pyramid 1 was triggered).

## 🚪 4. Dynamic Re-entry Recovery
Filters re-entries based on the expected "Gamma" or volatility of the day.

| DTE | Recovery % Required |
| :--- | :--- |
| **0 (Expiry)** | **20%** (Strong filter for high gamma) |
| **1 (Wed)** | **15%** |
| **2 (Tue)** | **10%** |
| **3+ (Mon/Fri)** | **5%** |

**Logic**: Re-enter only if the price crosses the mid-point of the `Entry Price` and `SL Exit Price`.

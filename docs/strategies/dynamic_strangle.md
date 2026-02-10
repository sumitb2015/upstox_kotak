# Dynamic Strangle Strategy

## 📝 Overview
**Type**: Non-Directional (Adaptive Strangle)  
**Instrument**: NIFTY Options (Short Strangle)  
**Logic Source**: `strategies/non_directional/dynamic_strangle/`

A robust "fire and forget" strategy designed for volatile markets. It starts with a standard Short Strangle but uses a unique **Hybrid Adjustment Mechanism** to survive big moves.

---

## ⚙️ Core Logic

### 1. Entry
- **Timing**: 9:20 AM
- **Selection**: Scans option chain for a pair (CE & PE) with **Delta ~0.30**.
- **Matching**: Uses a scoring algorithm to find the pair with minimal price difference (minimizing structural skew).

### 2. Adaptive Adjustment (The "Secret Sauce")
Instead of fixed adjustments, it uses a **Hybrid Threshold**:
- **Point Cap**: Far from expiry, it tolerates ~20 pts loss. Near expiry, ~10 pts.
- **Percentage**: Calculates a dynamic % threshold based on DTE and IV.
- **Action**:
    - If `Combined Premium` swells beyond the threshold -> **Trigger Adjustment**.
    - **Risk-ON (Converge)**: If not a Straddle, bring the winning leg CLOSER to the losing leg to collect more premium.
    - **Risk-OFF (Defend)**: If already a Straddle, roll the tested leg OUT to reduce delta.

### 3. Metric Adjustment
- It identifies the **Tested Leg** (Losing) and **Untested Leg** (Winning).
- Balances the trade by shifting the Untested Leg to match the premium of the Tested Leg.

---

## 🛡️ Risk Management

### Stop Loss
- **Ratcheting SL**: Starts at 60% of collected premium.
- **Logic**: Every time Net Credit increases (profit), the SL tightens. **It never loosens.**
- **Hard Cap**: Optional fixed rupee stop loss.

### Protection Guards
- **Skew Guard**: If one leg becomes > 2x the other (`ratio < 0.5`), it forces an adjustment even if PnL is fine.
- **Cooldown**: 5-minute cooldown after a Stop Loss hit before re-entering (to avoid choppy whipsaws).

---

## 📂 File Structure
- `live.py`: Contains the entire monolithic logic (Class `DynamicStrangleStrategy`).

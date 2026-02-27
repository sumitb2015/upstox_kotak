# Dynamic Strangle Strategy

## 📈 Strategy Overview
This is a sophisticated non-directional option selling strategy that initiates a light-delta strangle (~0.2 to 0.3 Delta) and manages risk through adaptive thresholds. It uses a hybrid adjustment approach (Percentage + Point Caps) that scales based on Days to Expiry (DTE).

---

## 🎯 Details

### 1. 🟢 Entry Conditions
- **Time Check**: Starts at **09:20 AM**.
- **Strike Selection**: Scans for a pair of CE and PE strikes that have balanced premiums and an average delta closest to the target (**~0.20**).
- **Match Filter**: Minimizes the difference between CE and PE premiums to ensure a delta-neutral start.

### 2. ⚖️ Adjustment Logic (Metric Balancing)
The strategy monitors the **Combined Premium (CP)** of the strangle.
- **Adaptive Threshold**: Calculates a trigger based on DTE. 
    - Far from expiry: Tight Control (**~8-10%** CP increase).
    - Near expiry: Looser Control (**~20-25%** CP increase).
- **Point Cap Guard**: Limits absolute point losses (e.g., 20 points far from expiry vs 10 points near expiry).
- **Phase 1 (Risk-ON)**: If CP hits the threshold, it closes the "untested" (winning) leg and moves it inward to a higher premium strike, converging towards a Straddle.
- **Phase 2 (Risk-OFF)**: If already in a straddle and CP hits the threshold, it moves the "tested" (losing) leg outward to defend the position.

### 3. 🔴 Exit Conditions
- **Profit Target**: **60%** of collected premium.
- **Initial Stop Loss**: **60%** of collected premium.
- **Time Exit**: Intraday square-off at **15:18**.

### 4. 🔒 Trailing Stop Loss (TSL)
- **Trigger**: Starts trailing at **50%** of the Profit Target.
- **Action**: Locks **50% of the Peak P&L** dynamically.
- **Ratcheting SL**: The stop loss is updated every time new premium is collected or rolled, always tightening, never loosening.

---

## 🚀 Overall Strategy Example
1. **09:20 AM**: Nifty at 24,000. Strategy sells 24,300 CE (₹30) and 23,700 PE (₹28). Total Ref CP = ₹58.
2. **11:00 AM**: Nifty rallies to 24,150. CE spikes to ₹65, PE decays to ₹10. Total CP = ₹75.
3. **Trigger**: Combined Premium has increased beyond the adaptive threshold (+15 pts). 
4. **Action (Risk-ON)**: Close 23,700 PE (₹10). Sell 23,900 PE (₹45) to match the CE premium. The position is now a narrower Strangle/Straddle.
5. **14:00 PM**: Theta decay sets in. Both legs decay. P&L hits the 60% Target.
6. **Exit**: All positions closed via Market orders.

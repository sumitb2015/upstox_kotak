# Dynamic Strangle Directional Strategy

## 📈 Strategy Overview
This strategy takes a directional stance using asymmetric OTM Strangles. It dynamically adjusts strikes and quantities based on the market's trend, volatility (IV), and time to expiry (DTE), aiming to capture premium while defending against sharp directional moves.

---

## 🎯 Details

### 1. 🟢 Entry Conditions
- **Trend Detection**: Uses EMA(20) and VWAP to determine market bias.
- **Initial Setup**: Sells an OTM Strangle (CE and PE).
- **Asymmetry**:
    - **Bullish Bias**: Closer (higher delta) PE and further (lower delta) CE.
    - **Bearish Bias**: Closer (higher delta) CE and further (lower delta) PE.

### 2. 🪜 Dynamic Adjustments
- **Thresholds**: Adjusts when the delta of one leg becomes 2x the other.
- **Risk-ON (Converge)**: Moves the winning leg closer to ATM to collect more premium during stable trends.
- **Risk-OFF (Defend)**: Moves the losing leg further OTM or adds a hedge if deltas expand too rapidly.
- **Adaptive**: Thresholds for adjustments tighten as DTE (Days to Expiry) decreases.

### 3. 🪜 Pyramiding logic
- **Trigger**: Profit locking at 20% of initial premium.
- **Action**: Adds lots to the winning side once the initial position is "risk-free" via trailing.

### 4. 🔴 Exit Conditions
- **Hard SL**: 20% of net premium collected.
- **TSL**: Trailing from 50% profit peak.
- **Time Square-off**: 15:15 PM.

### 5. ⚖️ Risk Management
- **Skew Guard**: Prevents taking a trade if the CE/PE premium imbalance is > 3:1 (avoids chasing).
- **Margin Guard**: Continuous fund validation for all adjustments.

---

## 🚀 Overall Strategy Example
1. **Bias**: Nifty is above VWAP (Bullish).
2. **Entry**: Sells 24,200 CE (Delta 0.2) and 23,900 PE (Delta 0.35). (Asymmetric Strangle).
3. **Trend Continuation**: Nifty moves up to 24,100.
   - PE Delta drops to 0.15 | CE Delta rises to 0.35.
4. **Adjustment**: Moves the 23,900 PE to 24,000 PE (Converge) to maintain delta balance and collect more premium.
5. **Exit**: Nifty hits target or reaches 15:15 PM.

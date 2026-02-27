# Delta-Neutral Strategy (Legacy)

## 📈 Strategy Overview
A legacy implementation of the delta-neutral option selling strategy. It focuses on core delta hedging mechanics, using real-time Greeks to maintain a market-neutral profile while collecting theta from ATM straddles.

---

## 🎯 Details

### 1. 🟢 Entry Conditions
- **Time Check**: Starts at **09:20 AM**.
- **Strike Selection**: Identifies and sells the ATM Straddle (CE + PE) for the nearest weekly expiry.
- **Initial Setup**: Records total premium collected to set P&L targets.

### 2. ⚖️ Adjustment Logic (Delta Hedging)
Maintains delta neutrality using a progressive threshold system:
- **Base Trigger**: Portfolio Delta > **15.0**.
- **Target Threshold**: Portfolio Delta < **5.0** (Target for rebalancing).
- **Progressive Filter**: Each adjustment round increases the threshold by **1.5x** to avoid over-trading in trending markets.
- **Hedging Action**: 
    - Sells additional CE if Delta < -Trigger (Negative/Bearish).
    - Sells additional PE if Delta > Trigger (Positive/Bullish).
- **Rolling Logic**: If max rounds (3) or max lots are hit, it rolls the deepest ITM position 100 points OTM.

### 3. 🔴 Exit Conditions
- **Profit Target**: **50%** of collected premium.
- **Stop Loss**: **30%** of collected premium (initial).
- **Gamma Control**: Emergency exit if portfolio **Gamma >= 0.50**.
- **Time Exit**: Intraday square-off at **15:15**.

### 4. 🔒 Trailing Stop Loss (TSL)
- **Activation**: Starts trailing once P&L reaches **25%** of the target.
- **Locking**: Locks **50% of peak P&L**.

---

## 🚀 Overall Strategy Example
1. **09:20 AM**: Strategy starts and sells Nifty 24,000 Straddle (1 lot CE/PE). Delta is near zero.
2. **10:15 AM**: Nifty drops to 23,920. Delta becomes -18.0 (Negative threshold 15 breached).
3. **Adjustment**: Sells 1 additional 24,000 CE. Delta neutralized to -4.5.
4. **12:00 PM**: Theta decay benefits the position. P&L hits ₹2,000. Peak P&L tracked.
5. **14:00 PM**: P&L hits ₹5,000. Profit Target reached.
6. **Exit**: All positions closed via market orders.

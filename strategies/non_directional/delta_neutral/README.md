# Delta-Neutral Option Selling Strategy

## 📈 Strategy Overview
This is a market-neutral strategy that sells ATM straddles and maintains delta neutrality through automatic hedging and rolling of positions. It combines high-probability option selling with robust mathematical risk management to capture theta while minimizing directional exposure.

---

## 🎯 Details

### 1. 🟢 Entry Conditions
- **Time Check**: Starts at **09:20 AM** (after morning volatility).
- **ADX Filter**: 
    - Safe if **ADX < 25** (Sideways/Weak trend).
    - If **25 < ADX < 40**, enters only if ADX is **Falling** (Cooling trend).
    - No entry if **ADX >= 40**.
- **OI PCR Check**: ATM PCR must be balanced between **0.5 and 2.0**.
- **Skew Check**: Straddle premium difference must be **< 20%** of total premium.

### 2. ⚖️ Adjustment Logic (Delta Hedging)
Matches portfolio delta to zero using a threshold-based approach:
- **Trigger Threshold**: Portfolio Delta > **12.0** (Adjusted progressively).
- **Target Threshold**: Portfolio Delta < **6.0** (Hysteresis target).
- **Hedging Action**: 
    - If Positive Delta (Bullish): Sell additional Call (add negative delta).
    - If Negative Delta (Bearish): Sell additional Put (add positive delta).
- **Rolling Logic**: If max adjustments (5) or max lots are reached, the strategy rolls the losing ITM leg to a further OTM strike.

### 3. 🔴 Exit Conditions
- **Profit Target**: **50%** of collected premium.
- **Stop Loss**: **30%** of collected premium (initial), updated dynamically.
- **Gamma Guard**: Emergency exit if portfolio **Gamma >= 0.5**.
- **Time Exit**: Intraday square-off at **15:18**.

### 4. 🔒 Trailing Stop Loss (TSL)
- **Trigger**: Once P&L reaches **25%** of the Profit Target.
- **Action**: Lock **50% of the Peak P&L** as the new dynamic Stop Loss.

---

## 🚀 Overall Strategy Example
1. **09:20 AM**: Strategy checks ADX (Value 22) and PCR (Value 0.8). Conditions passed.
2. **Entry**: Sells Nifty ATM Straddle (e.g., 24,000 CE/PE at ₹100 each). Total Premium = ₹200.
3. **10:45 AM**: Nifty rallies to 24,100. Call price spikes, Put price decays. Portfolio Delta hits 15.0.
4. **Adjustment**: Sells additional 24,000 CE to neutralize delta until portfolio delta falls below 6.0.
5. **13:30 AM**: P&L reaches ₹4,000 (Peak). Target is ₹5,000. TSL is triggered and locks ₹2,000.
6. **14:45 AM**: Market reversals, P&L drops to ₹2,000. TSL hit. **Exit All Positions**.

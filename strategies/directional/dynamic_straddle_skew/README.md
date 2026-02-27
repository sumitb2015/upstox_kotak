# Dynamic Straddle Skew Strategy

## 📈 Strategy Overview
This strategy begins with a neutral **ATM Straddle** and dynamically transforms into a **Skewed Straddle** based on market movement. It scales into the winning (decaying) leg and reduces exposure on the losing (expanding) leg, capturing directional bias while benefiting from theta decay.

---

## 🎯 Details

### 1. 🟢 Entry Conditions
- **Time**: Trades start at 9:20 AM.
- **Initial Setup**: Sells 1 lot of ATM Call and 1 lot of ATM Put (Neutral Straddle).

### 2. 🪜 Skew & Pyramiding Logic
- **Monitoring**: The strategy monitors the premium ratio between CE and PE.
- **Skew Trigger**: If one leg's premium becomes **> 1.5x** the other, a directional bias is identified.
- **Scaling Up**: Adds **1 lot** to the winning side (the leg with decreasing premium).
- **Decay Factor**: Subsequent pyramid lots are added every 10% move in favorably skewed premium.

### 3. 📉 Reduction Logic (Defensive)
- **Monitoring**: If price reverses, the strategy reduces the "winning" leg lots one-by-one to maintain a balanced risk profile.
- **Buffer**: A 5% retracement from the local profit peak triggers a reduction.

### 4. 🔴 Exit Conditions
- **Hard SL**: Global P&L loss reach 1.5% of total capital.
- **Profit Target**: Global P&L profit reaches 2.5% of capital.
- **Time Square-off**: All positions closed at 15:15 PM.

### 5. ⚖️ Risk Management
- **Maximum Lots**: Capped at 5 lots per side to prevent over-leveraging.
- **Margin Guard**: Pre-trade validation of available funds before every pyramiding step.

---

## 🚀 Overall Strategy Example
1. **09:20 AM**: Nifty at 24,000. Sells 24,000 CE (₹100) and 24,000 PE (₹100).
2. **10:00 AM**: Nifty rises to 24,100. 
   - CE (₹160) | PE (₹60).
   - Skew Ratio: 160 / 60 = 2.6x (> 1.5x threshold).
3. **Action**: Market is Bullish. Strategy sells **1 more lot of PE** (Winning side).
4. **Pyramiding**: PE drops to ₹50 -> Strategy sells **another lot of PE**. Total Pos: 1 CE, 3 PE.
5. **Reversal**: Nifty drops to 24,050. PE rises to ₹70.
6. **Reduction**: Strategy buys back 1 PE lot to reduce exposure. Total Pos: 1 CE, 2 PE.
7. **15:15 PM**: Exit remaining positions.

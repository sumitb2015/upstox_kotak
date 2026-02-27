# Supertrend Multi-Timeframe Strategy

## 📈 Strategy Overview
This strategy aligns the global trend of the Index with the local technical weakness of an Option Premium. It only sells options when the Nifty trend is favorable AND the option premium itself has entered a definitive technical downtrend, maximizing the probability of a successful short trade.

---

## 🎯 Details

### 1. 🟢 Entry Conditions
- **Step A: Index Bias (Nifty)**:
    - Analyzes Supertrend (10, 2) on a 3-minute Nifty Index chart.
    - **Bullish Bias**: Nifty ST is Green. -> **Focus: Sell PE**.
    - **Bearish Bias**: Nifty ST is Red. -> **Focus: Sell CE**.
- **Step B: Strike Selection**:
    - Scans for the OTM strike with premium closest to ₹60.
- **Step C: Option Trend Confirmation**:
    - Analyzes Supertrend (10, 2) on the **Option's 3-minute chart**.
    - **Trigger**: The Option price must be below its own Supertrend (Trend is Red).
    - *Logic*: We short the option only when its premium is already falling technically.

### 2. 🪜 Dynamic Management
- **LTP Monitoring**: Continuously tracks option LTP via WebSocket for immediate SL triggers.
- **REST Fallback**: Automatically switches to REST API if WebSocket data for a specific option becomes stale.

### 3. 🔴 Exit Conditions
- **Option Trend Flip**: Exit immediately if the Option Supertrend turns Green (Bullish move).
- **Price Breach**: Exit if Option LTP crosses above the Supertrend value.
- **Nifty Reversal**: Exit if the Nifty Index Supertrend flips against the trade bias.
- **Profit Locking**: Hardened absolute profit locking (e.g., locks 50% of profit once ₹2000 gain is reached).

### 4. ⚖️ Risk Management
- **Warmup**: Seeding 5 days of historical data for both Nifty and Option charts for accurate indicator calculation.
- **Time Check**: Prevents new entries after 14:45 PM and forced square-off at 15:15 PM.

---

## 🚀 Overall Strategy Example
1. **Bias (10:00 AM)**: Nifty Supertrend turns Red (Bearish).
2. **Setup**: Scanner selects 24,300 CE trading at ₹62.
3. **Confirmation**: 24,300 CE Supertrend is also Red (Price ₹62 < ST ₹66).
4. **Action**: Sell 24,300 CE.
5. **Trade**: Nifty stays bearish. CE premium drops to ₹45. CE ST is at ₹52.
6. **Reversal**: Nifty rallies slightly. CE premium spikes to ₹53 (Breached ST of ₹52).
7. **Exit**: Price Breach detected. Position squared off.

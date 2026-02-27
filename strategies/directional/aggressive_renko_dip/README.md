# Aggressive Renko Dip Strategy

## 📈 Strategy Overview
This is an aggressive trend-following strategy designed for Nifty, utilizing high-frequency Renko bricks and RSI momentum filters. It specializes in capturing intraday "dips" in strong trends using specific brick patterns and dynamic option premium tracking.

---

## 🎯 Details

### 1. 🟢 Entry Conditions
- **Time Check**: Active during market hours until 15:15.
- **Signal Renko**: 5-point bricks on Nifty Spot/Futures.
- **Trend Confirmation**: 
    - **Bullish (Sell PE)**: 2 consecutive Green Bricks + RSI > 50 + Price > EMA(10).
    - **Bearish (Sell CE)**: 2 consecutive Red Bricks + RSI < 50 + Price < EMA(10).
- **Regime Filter**: Max 40% reversal frequency allowed in the last 20 bricks (ensures trending market).

### 2. 🪜 Pyramiding logic
- **Trigger**: Adds **1 lot** every time a single RED brick forms on the **Option Renko** chart (moving in profit direction).
- **Limit**: Max 3 lots total (Initial + 2 Pyramids).
- **Safety**: Only triggers if available funds > required margin.

### 3. 🔴 Exit Conditions
- **TSL (Option Renko)**: Staircase trailing updates ONLY when a full RED brick forms on the Option Renko.
- **Reversal Exit**: Close position if 3 consecutive bricks form against the trade direction on the Option chart.
- **Profit Target**: Fixed exit after 6 Option Bricks of favorable movement.
- **Time Exit**: Hard square-off at **15:15 PM**.

### 4. ⚖️ Risk Management
- **Brick-Based Stops**: Exits are determined by structural reversals (brick color changes) rather than just percentage hits.
- **Wait for Close**: Signal evaluations are performed at the close of 1-minute candles to filter noise.

---

## 🚀 Overall Strategy Example
1. **10:00 AM**: Nifty creates two Green 5-pt bricks; RSI is 65; EMA(10) is below price.
2. **Entry**: Sell 1 lot of ATM PE.
3. **Trend Move**: Nifty moves up; Option premium drops. A 5% RED brick forms on the Option Renko.
4. **Pyramiding**: Strategy sells 1 more lot of same PE.
5. **Reversal**: Nifty stalls. Option premium rises and forms 3 GREEN bricks (approx 15% rise).
6. **Exit**: Strategy hits TSL and closes both lots.

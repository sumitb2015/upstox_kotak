# Dual Renko Dip Strategy

## 📈 Strategy Overview
The Dual Renko Dip strategy is a robust trend-following system that utilizes two sets of Renko bricks (Macro & Micro) to identify high-probability trend entries and exits. It aligns the macro regime with short-term momentum to sell options in trending markets.

---

## 🎯 Details

### 1. 🟢 Entry Conditions
- **Regime Alignment (Mega Renko)**: Macro trend must be confirmed by 20-point "Mega" bricks.
- **Micro Timing (Signal Renko)**: Entry triggered on reversal or continuation of 5-point bricks.
- **Filters**:
    - **Bullish (Sell PE)**: Mega Green + Signal Green (2 bricks) + RSI(14) > 60.
    - **Bearish (Sell CE)**: Mega Red + Signal Red (2 bricks) + RSI(14) < 40.

### 2. 🪜 Pyramiding logic
- **Scaling**: Adds units on resumption of the main trend after a minor pullback.
- **Trigger**: New Signal Renko brick in the direction of the Mega Trend.
- **Max Units**: 3 levels total.

### 3. 🔴 Exit Conditions
- **Mega Reversal**: Immediate exit if the Mega Renko flips color.
- **TSL (Option Renko)**: Dynamic trailing stop loss based on Option Premium 5% bricks.
- **Hybrid Stop Loss**: Combined Spot price breach + 20% Option SL safety net.
- **Time Square-off**: 15:15 PM.

### 4. ⚖️ Risk Management
- **Correlation Filter**: Only takes Longs if PCR > 1.1 or Shorts if PCR < 0.9.
- **Liquidity Check**: Ensures spread between Bid-Ask is < 1% before entry.

---

## 🚀 Overall Strategy Example
1. **Trend Start**: Nifty Mega Renko turns Green.
2. **Setup**: RSI reaches 62, and Signal Renko forms its 2nd Green brick.
3. **Action**: Strategy sells 1 lot of Nifty ATM Put.
4. **Follow-through**: Price trends up; TSL moves up every time Option Premium drops by 5 points.
5. **Reversal**: Signal Renko turns Red (pulldown); Macro stays Green.
6. **Recovery**: Signal Renko turns Green again -> **Pyramiding step added**.
7. **Trend End**: Mega Renko turns Red -> **All positions closed**.

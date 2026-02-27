# Synthetic Future CPR Scalper

## 📈 Strategy Overview
This strategy scalps Nifty using **Synthetic Futures** (ATM CE + PE). It uses Central Pivot Range (CPR) levels to identify breakouts/breakdowns and VWAP to filter the trend. By using synthetic futures, the strategy mimics future price action while utilizing the options market for leverage and ease of execution.

---

## 🎯 Details

### 1. 🟢 Entry Conditions
- **Trend Filter**: Continuous monitoring of VWAP (1-minute basis).
- **Signal**: Breakout or Breakdown of any CPR Level (Pivot, TC, BC, R1-3, S1-3).
- **Execution Rules**:
    - **Bullish (Buy Synthetic)**: Price > VWAP AND Price crosses above a Resistance/Pivot level.
    - **Bearish (Sell Synthetic)**: Price < VWAP AND Price crosses below a Support/Pivot level.
- **Instrument Construction**:
    - **Long Synthetic Future**: Buy ATM CE + Sell ATM PE.
    - **Short Synthetic Future**: Buy ATM PE + Sell ATM CE.

### 2. 🪜 Trade Management
- **Initial Risk**: Fixed 20-point stop loss on the underlying price basis.
- **Target**: Next available CPR/Pivot level.
- **Trailing Stop Loss**: 
    - **Trigger**: Once the profit reaches **10 points** in the favorable direction.
    - **Action**: Slaps a **10-point trailing stop** (e.g., if profit is 15 pts, SL is locked at +5 pts).

### 3. 🔴 Exit Conditions
- **SL Trigger**: Underlying price moves 20 points against the entry basis.
- **TSL Trigger**: Profit retraces by 10 points after the trailing threshold is met.
- **Time Square-off**: Forced exit at 15:15 PM.

### 4. ⚖️ Risk Management
- **Future Reference**: Signals are derived from **Nifty Futures** (preferred) or Spot price.
- **Atomic Execution**: Trades both legs of the synthetic future simultaneously using Kotak Order Manager to minimize basis risk.

---

## 🚀 Overall Strategy Example
1. **CPR Levels**: Pivot at 24,000 | R1 at 24,080. VWAP is 24,010.
2. **Setup (11:00 AM)**: Nifty is at 24,020 (Above VWAP).
3. **Signal**: Nifty rallies and crosses 24,080 (R1 Breakout).
4. **Action**: Bullish Signal.
   - Buy 24,100 CE @ ₹70.
   - Sell 24,100 PE @ ₹60.
5. **Initial SL**: 24,060 (Entry 24,080 - 20 pts).
6. **Move**: Nifty goes to 24,095 (Profit 15 pts).
7. **Trailing**: TSL starts. New SL is 24,085 (High 24,095 - 10 pts).
8. **Exit**: Nifty hits target at R2 or hits the trailing SL.

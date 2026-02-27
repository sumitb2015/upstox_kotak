# Futures Breakout Strategy

## 📈 Strategy Overview
This strategy monitors Nifty Futures for breakouts above or below key structural levels (Yesterday's High/Low or Round Number Strikes). Breakouts are validated by **Volume Spikes** and **EMA Alignment** before selling OTM options to capture the momentum and theta.

---

## 🎯 Details

### 1. 🟢 Entry Conditions
- **Reference**: Nifty Futures Price.
- **Breakout Level**: Yesterday's High, Yesterday's Low, or significant round-number strikes (e.g., 24,500).
- **Validation**: 
    - **Volume**: Current 1-min volume must be > 1.5x of the average volume of the last 10 candles.
    - **Trend**: Price must be above EMA(20) for Bullish and below for Bearish.
- **Action**:
    - **Bullish Breakout (Above Resistance)**: Sell 2 Strikes OTM Put (PE).
    - **Bearish Breakdown (Below Support)**: Sell 2 Strikes OTM Call (CE).

### 2. 🪜 Pyramiding logic
- **Trigger**: Every 50-point move in Nifty Futures in the breakout direction.
- **Scaling**: Adds 1 lot of the same option.
- **Max Lots**: 3 lots total.

### 3. 🔴 Exit Conditions
- **Failure**: Price closes back inside the breakout level (Fake Breakout).
- **Hard SL**: 20% on the option premium.
- **Target**: 30% profit or next major pivot level.
- **Time Square-off**: 15:15 PM.

### 4. ⚖️ Risk Management
- **LTP Sync**: Uses Upstox for fast Future price tracking and Kotak for reliable option execution.
- **Slippage Control**: Uses Limit orders for entry but Market orders for緊急 exits.

---

## 🚀 Overall Strategy Example
1. **Scenario**: Yesterday's high was 24,120. Average volume is 50k.
2. **Breakout**: 11:15 AM - Nifty Futures hits 24,125 with 120k volume.
3. **Action**: Bullish signal confirmed. Sells 24,000 PE (2 strikes OTM).
4. **Follow-through**: Nifty moves to 24,175.
5. **Pyramiding**: Adds 1 more 24,000 PE.
6. **Fakeout**: Nifty drops back to 24,110.
7. **Exit**: Fakeout detected. Strategy closes all PE positions immediately.

# ORB Break-and-Retest Strategy

## 📈 Strategy Overview
The Opening Range Breakout (ORB) with Retest is a disciplined directional system. Unlike standard ORB strategies that "chase" breakouts, this system waits for a price retest of the broken level and a strong confirmation candle to filter out fake breakouts.

---

## 🎯 Details

### 1. 🟢 Pattern Logic
- **Opening Range**: First 5-minute candle of the day (09:15 - 09:20 AM).
- **OR Range**: Must be between 20 and 150 points (prevents trading on extremely narrow or wide days).

### 2. 🪜 Execution Flow
1. **Breakout**: A 5-minute candle closes outside the Initial Range High or Low.
2. **Retest**: The price returns to the breakout level (High for Longs, Low for Shorts).
3. **Confirmation**: A strong 1-minute candle (Bullish for Longs, Bearish for Shorts) forms at the retest level.
4. **Action**:
    - **Bullish Retest (Bounces off High)**: Sell ATM-100 PE. (Buying CE also supported).
    - **Bearish Retest (Rejected off Low)**: Sell ATM+100 CE.

### 3. 🔴 Exit Conditions
- **Stop Loss (Spot Based)**:
    - **Long Trade**: Mother Low - 10 points.
    - **Short Trade**: Mother High + 10 points.
- **Target**: 2x Risk (Risk-Reward Ratio of 2.0).
- **Retest Timeout**: If a retest doesn't happen within 30 minutes of the breakout, the trade is voided.
- **Time Square-off**: 15:15 PM.

### 4. ⚖️ Risk Management
- **Confirmation Check**: Uses body-to-wick ratio to ensure the bounce candle is "strong".
- **Instrument Mapping**: Dynamically resolves Kotak symbols for current-week options.

---

## 🚀 Overall Strategy Example
1. **09:20 AM**: Nifty 5-min candle is 24,100 (High) to 24,050 (Low).
2. **Breakout (09:35)**: 5-min candle closes at 24,110. (BULLISH BREAKOUT).
3. **Wait**: Price goes to 24,125 then starts dropping.
4. **Retest (09:42)**: Price touches 24,103 and then forms a strong 1-minute Green candle.
5. **Action**: BULLISH RETEST CONFIRMED. Sell 24,050 PE.
6. **Spot SL**: 24,040 (Mother Low 24,050 - 10).
7. **Target**: Price goes to 24,250 (Target 2:1 hit). Trade closed.

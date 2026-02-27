# VWAP Theta Straddle Strategy

## 📈 Strategy Overview
A high-probability intraday strategy that sells ATM straddles when the Combined Premium (CP) is trading at "value" relative to the volume-weighted average price (VWAP) and previous day ranges.

---

## 🎯 Details

### 1. 🟢 Entry Conditions
- **Time Check**: Starts at **09:20 AM**.
- **Value Logic**:
    - **Condition A**: Combined Premium (CE + PE) < **Previous Day Combined Low**.
    - **Condition B**: Combined Premium < **Combined VWAP**.
- **Skew Filter**: Initial width between CE and PE must be **< 20%** of the total premium (Avoids one-sided market gaps).
- **Timeframe**: 3-minute or 5-minute candle closes for indicator signals.

### 2. ⚖️ Monitoring
- **Combined VWAP**: A custom synthetic indicator calculated as `sum(CP * Total_Volume) / sum(Total_Volume)` across both legs.
- **Real-time Monitoring**: Uses WebSockets to poll premium prices every 15 seconds for emergency Stop Loss checks between candle closes.

### 3. 🔴 Exit Conditions
- **VWAP Reversal**: Exit if Combined Premium crosses **Above Combined VWAP** (indicates decay has reversed or volatility is spiking).
- **Stop Loss**: Hit if CP > **Entry Price + 30 Points**.
- **Skew Exit**: Exit if one leg diverges significantly from the other (**> 55-60% skew**).
- **Time Exit**: Automatic square-off at **15:15**.

### 4. 🧊 Cooldown Logic
- If the strategy exits due to SL or VWAP reversal, it enters a **2-minute cooldown** before allowing any re-entry, preventing whipsaws in high-volatility markets.

---

## 🚀 Overall Strategy Example
1. **09:20 AM**: ATM Strike identified as 24,000. Prev Day CP Low was ₹220.
2. **09:33 AM**: Current CP is ₹215 (below Prev Low) and Combined VWAP is ₹218. Conditions passed.
3. **Entry**: Short 24,000 CE and PE at ₹107.5 each. Total Entry CP = ₹215. Target SL = ₹245.
4. **11:00 AM**: Combined Premium decays steadily to ₹190. Trades stay below VWAP.
5. **12:30 PM**: Sudden market spike. CP jumps to ₹210, then crosses above the falling VWAP line (₹208).
6. **Action**: Signal detected at candle close. Strategy exits all positions to protect remaining Theta profit.

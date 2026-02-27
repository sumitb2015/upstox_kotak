# VWAP Straddle Strategy v2

## 📈 Strategy Overview
An enhanced version of the VWAP Straddle strategy featuring atomic order execution, real-time tick-based Trailing Stop Loss, and robust profit locking mechanisms. It treats the ATM straddle as a single synthetic unit.

---

## 🎯 Details

### 1. 🟢 Entry Conditions
- **Time Check**: Starts at **09:20 AM**.
- **Market Sentiment**:
    - **Condition 1**: Combined Premium (CP) < **Previous Day Combined Low**.
    - **Condition 2**: Combined Premium < **Combined VWAP**.
- **Atomic Execution**: Places both legs nearly simultaneously. If one leg fails, the other is automatically rolled back (closed) to prevent naked exposure.

### 2. ⚖️ Monitoring
- **Combined VWAP**: Intraday volume-weighted average of the sum of CE and PE premiums.
- **Tick Monitoring**: Polls prices every 1 second via WebSockets for precision P&L and TSL tracking.

### 3. 🔴 Exit Conditions
- **VWAP Crossover**: Exit if CP crosses back **Above VWAP** on a candle close.
- **Fixed Stop Loss**: CP > **Entry Price + 30 Points**.
- **Skew Divergence**: Exit if individual leg divergence > **60%** (One side spiking uncontrollably).
- **Time Exit**: Intraday square-off at **15:15**.

### 4. 🔒 Trailing Stop Loss (TSL)
- **Trailing Logic**: Tracks the **Lowest CP** reached since entry.
- **Activation**: If CP rises **20 points** above its lowest recorded level, the TSL is triggered.
- **Benefit**: Locks in profit as the straddle decays; if a reversal occurs, it exits quickly before profit evaporates.

---

## 🚀 Overall Strategy Example
1. **09:20 AM**: Strategy identifies Nifty ATM (e.g. 24,000). Combined VWAP is ₹205.
2. **09:25 AM**: CP drops to ₹200. Entry conditions met.
3. **Entry**: Sells CE and PE. Actual execution gives Entry CP = ₹201. SL is ₹231.
4. **11:30 AM**: CP decays to ₹160 (Lowest CP). TSL target is now ₹180 (160 + 20).
5. **13:00 PM**: Market reverses slightly. CP rises from ₹160 to ₹181. 
6. **Trigger**: Tick monitoring detects CP (181) > TSL Level (180). 
7. **Action**: Immediate Exit via Kotak Neo Market orders.

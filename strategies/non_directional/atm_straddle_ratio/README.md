# ATM Straddle Ratio Strategy

## 📈 Strategy Overview
This is a non-directional option selling strategy that initiates a Short Straddle (Sell ATM CE + PE) when volatility is favorable and manages the position dynamically based on the premium ratio between the two legs.

---

## 🛠️ Logic Breakdown

### 1. 🟢 Entry Logic
The strategy waits for two conditions to be met before entering:

1.  **Time Check**: Current Time >= `ENTRY_TIME` (Default: **09:20 AM**).
2.  **VIX Filter (Volatility Check)**:
    *   **Indicator**: Supertrend(10, 3) on India VIX (5-minute timeframe).
    *   **Condition A**: VIX Close < Supertrend Value (VIX is in a downtrend).
    *   **Condition B**: VIX Close < VIX Open (Current VIX candle is Red/Falling).
    *   *Why?* We want to sell premiums when volatility is cooling off to benefit from Vega decay.

**Example:**
> It is 09:23 AM.
> *   India VIX is 13.5. Supertrend(10,3) value is 14.2. (Condition A Met)
> *   Current 5-min VIX candle: Open=13.6, Close=13.5. (Condition B Met)
> *   **Action**: Fetch Nifty Spot (e.g., 24,000). Sell 24,000 CE and 24,000 PE.

---

### 2. ⚖️ Adjustment Logic (Ratio Balancing)
Once in a trade, the strategy monitors the **Premium Ratio** between CE and PE every 60 seconds.

*   **Formula**: `Ratio = Min(CE_LTP, PE_LTP) / Max(CE_LTP, PE_LTP)`
*   **Threshold**: If `Ratio < 0.6` (Configurable), it implies one side has decayed significantly or the other has spiked (Trend emerging).

**Scenario A: Strong Trend (ATM Shift)**
*   **Condition**: Adjustment triggered AND Spot Price has moved **≥ 50 points** from Entry Strike.
*   **Action**: **Switch ATM**.
    *   Close current Straddle.
    *   Enter NEW Straddle at current ATM.

**Scenario B: Premium Drift (Balancing)**
*   **Condition**: Adjustment triggered BUT Spot Price is within 50 points.
*   **Action**: **Add to Winner**.
    *   Identify the profitable leg (the one whose price has dropped more).
    *   Sell **1 additional lot** of that profitable leg to collect more premium.

---

### 3. 🔴 Exit Logic (Stop Loss & Target)
The strategy monitors the **Global P&L** (Sum of all legs).

1.  **Profit Target**:
    *   If Total P&L ≥ `PROFIT_TARGET` (Default: **₹5,000**).
    *   **Action**: Square off all positions immediately.

2.  **Stop Loss**:
    *   If Total P&L ≤ `STOP_LOSS` (Default: **-₹3,000**).
    *   **Action**: Square off all positions immediately.

3.  **Time Exit**:
    *   At `FORCE_EXIT_TIME` (Default: **15:18**).
    *   **Action**: Square off all positions to avoid carry-forward.

---

## 📝 Configuration Examples

| Parameter | Value | Description |
| :--- | :--- | :--- |
| `ENTRY_TIME` | "09:20" | Start checking conditions. |
| `RATIO_THRESHOLD` | 0.6 | Trigger adjust if premiums diverge by 40%. |
| `PROFIT_TARGET` | 5000 | Lock profit at ₹5k MTM. |
| `STOP_LOSS` | -3000 | Max loss accepted. |
| `LOT_SIZE` | 1 | Base quantity (multiplied by broker lot size). |

## 🚀 Execution Flow (Step-by-Step)
1.  **09:15**: Strategy starts, connects to WebSocket.
2.  **09:20**: Checks VIX.
    *   *VIX rising?* -> **WAIT**.
    *   *VIX falling & below Supertrend?* -> **ENTER** (Sell ATM CE/PE).
3.  **10:30**: Market rallies.
    *   CE Price rises to 150. PE Price drops to 60.
    *   Ratio = 60/150 = **0.40**. (Below 0.6 threshold).
    *   Spot moved > 50 pts? **Yes**.
    *   **Action**: Close current straddle. Open new straddle at new ATM.
4.  **14:00**: Choppy market.
    *   P&L hits +₹5,100.
    *   **Action**: Exit All. Happy Trading!

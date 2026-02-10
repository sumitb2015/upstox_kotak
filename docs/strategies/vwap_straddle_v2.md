# VWAP Straddle V2

## 📝 Overview
**Type**: Non-Directional (Intraday Straddle)  
**Instrument**: NIFTY Options (Short Straddle)  
**Logic Source**: `strategies/non_directional/vwap_straddle_v2/`

An intelligent Straddle strategy that treats the **Combined Premium (CE+PE)** as a single instrument. It uses VWAP on this combined chart to determine if premiums are "fair" or "expensive".

---

## ⚙️ Core Logic

### 1. The "Combined Premium" Concept
Instead of watching CE and PE separately, this strategy sums them up:
$$CP = Price(CE) + Price(PE)$$
It also calculates a **Volume Weighted Average Price (VWAP)** for this synthetic CP instrument.

### 2. Entry Conditions
The strategy enters a Short Straddle ONLY when premiums are "cheap" relative to the day's trend but "expensive" enough to sell.
*Wait, standard logic is usually selling when above VWAP (expensive), but looking at `core.py`:*

**Actual Code Logic**:
1.  **Trend Filter**: `CP < VWAP` (We want to sell when premium is *below* VWAP? This implies Momentum/Breakdown logic or specific condition in V2. *Correction based on code reading*: `if not (cp < prev_low and cp < vwap): return False`.
    - It enforces selling when the premium has **broken down** (is below VWAP and Previous Day Low). This is a **Trend Following Short** on premium (betting on crush/decay).
2.  **Skew Check**: `abs(CE - PE) / CP < 20%`. Ensures the straddle is somewhat centered.

### 3. Adjustments / Management
- **No manual re-centering** in the V2 core logic shown. It relies on the initial entry quality.
- Focus is on **Exit** logic.

---

## 🛡️ Risk Management

### Exits (Priority Order)
1.  **Stop Loss**: Fixed points stop loss on standard combined premium.
2.  **Trailing SL**: Tracks the **Lowest CP**. If CP rises by `trailing_sl_points` from the low, Exit.
    - *Logic*: "I have 50 points profit, now I give back 20, I leave."
3.  **VWAP Reversal**: If `CP > VWAP`, the trend of "decay" has broken. Exit.
4.  **Skew Exit (Runtime)**: If one leg explodes and skew > 60%, exit to avoid delta blowup.

---

## 📂 File Structure
- `core.py`: Shared logic for Backtest and Live.
- `live.py`: Execution wrapper.
- `backtest.py`: Fast validation module.

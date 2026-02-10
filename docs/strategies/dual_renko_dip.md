# Dual Renko Dip Strategy

## 📝 Overview
**Type**: Directional (Momentum / Dip Buying)  
**Instrument**: NIFTY Options  
**Logic Source**: `strategies/directional/dual_renko_dip/`

A sophisticated trend-following strategy that uses **Renko Charts** to strip out noise and identify clear trends. It uses a "Dual Layer" approach: one layer for the Macro Trend and another for Entry Timing.

---

## ⚙️ Core Logic

### 1. Indicators
- **Mega Renko (60 pts)**: Determines the **Macro Trend**.
    - Green = Bullish
    - Red = Bearish
- **Signal Renko (5 pts)**: Determines **Entry Timing**.
    - Used to spot "Dips" (Pullbacks) within the macro trend.
- **RSI (14)**: Momentum filter to avoid entering overextended moves.

### 2. Entry Triggers (The "Dip")
The strategy looks for a specific pattern: **Trend -> Pullback -> Resumption**.

- **Bullish Entry (Sell PE)**:
    1.  **Macro**: Mega Mean (60) is Green.
    2.  **Dip**: Signal Renko (5) showed a Red brick (Pullback).
    3.  **Resumption**: Signal Renko forms **3 Green Bricks** in a row.
    4.  **RSI**: Between 50 and 80.

- **Bearish Entry (Sell CE)**:
    1.  **Macro**: Mega Mean (60) is Red.
    2.  **Dip**: Signal Renko (5) showed a Green brick (Pullback).
    3.  **Resumption**: Signal Renko forms **3 Red Bricks** in a row.
    4.  **RSI**: Between 20 and 50.

---

## 🛡️ Risk Management

### Exits
1.  **Macro Reversal**: If the Mega Renko flips color (Train changes direction), exit immediately.
2.  **Option Trailing SL**: A separate Renko chart runs on the **Option Premium**.
    - If the premium rises (reverses) by ~22% from its lows (3 bricks of 7.5%), exit.
3.  **Hard Stop**: Emergency percentage stop loss.

### Pyramiding
- Adds to winners if the Signal Renko shows another "Dip & Resume" pattern while the Macro Trend holds.

---

## 📂 File Structure
- `core.py`: Renko calculation logic (Classic/ATR bricks).
- `live.py`: Real-time candle syncing and brick construction.
- `STRATEGY.md`: detailed design notes.

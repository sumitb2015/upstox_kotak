# Futures VWAP EMA Strategy

## 📝 Overview
**Type**: Directional (Option Selling)  
**Instrument**: NIFTY Options  
**Logic Source**: `strategies/directional/futures_vwap_ema/`

This strategy sells Options (CE or PE) based on the trend of the NIFTY Futures. It uses VWAP as the primary regime filter and EMA(20) as the trigger.

---

## ⚙️ Core Logic

### 1. Regime Filter (VWAP)
- **Bullish Regime**: Futures Price > VWAP
- **Bearish Regime**: Futures Price < VWAP

### 2. Entry Triggers
- **Sell PE (Bullish)**:
    - Price is in Bullish Regime (> VWAP)
    - **Trigger**: Price crosses **ABOVE EMA(20)** OR (Price > EMA and PCR Trend is Bullish)
    - **Strike**: ATM - 150 (OTM Put)
    
- **Sell CE (Bearish)**:
    - Price is in Bearish Regime (< VWAP)
    - **Trigger**: Price crosses **BELOW EMA(20)** OR (Price < EMA and PCR Trend is Bearish)
    - **Strike**: ATM + 150 (OTM Call)

### 3. Filters
- **PCR Filter**: Checks Daily Change in PCR to confirm trend strength.
    - Bullish: Change > 1.05
    - Bearish: Change < 0.95

---

## 🛡️ Risk Management

### Stop Loss
- **Trailing Stop Loss (TSL)**: Calculated on the Option Premium.
- **Base TSL**: 20% from the **Lowest Price** (since we are shorting, low price = max profit).
- The TSL creates a "ceiling" that moves down as the premium decays.

### Pyramiding (Scaling In)
- If the trade is profitable (Unrealized Profit > 10%), the strategy adds more lots.
- **Max Levels**: 2 additional levels (Total 3 lots max).
- **TSL Tightening**: As you pyramid, the TSL % tightens (20% -> 15% -> 10%) to protect gains.

### Exits
1.  **TSL Hit**: Premium crosses above the Trailing Stop.
2.  **Trend Reversal**: Futures Price crosses VWAP (Structural failure).
3.  **Time**: Intraday square-off at 15:15.

---

## 📂 File Structure
- `strategy_core.py`: Contains the logic for crossovers, VWAP calculation, and signal generation.
- `live.py`: Handles Upstox API connection, live data fetching, and order placement via Kotak.
- `STRATEGY_RULES.md`: Original rules document.

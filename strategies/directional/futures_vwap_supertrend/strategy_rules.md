# Futures VWAP Supertrend Strategy Rules

This document outlines the core trading logic, risk management, and execution rules for the Futures VWAP Supertrend Options Selling strategy.

## 1. Strategy Overview
- **Instrument**: NIFTY Index Options
- **Underlying Reference**: NIFTY Futures (for Price/VWAP) & NIFTY Index (for PCR/Spot)
- **Timeframe**: 3-minute candles (configurable)
- **Trade Type**: Option Selling (Shorting)
- **Expiry**: Current Week / Next Week (configurable)

---

## 2. Entry Strategy
The strategy looks for a confluence of **Price Action**, **Trend**, and **Market Sentiment**. Entries are checked tick-by-tick based on static indicators.

### CE Sell (Bearish Signal)
- **VWAP Filter**: Futures Price must be **Below VWAP**.
- **Supertrend Filter**: Supertrend must be in **Downtrend (Red)** and price must be below the Supertrend band.
- **VWAP Distance Filter**: Price must be within **0.2%** of VWAP (Prevent late entry/chasing).
- **Strike Selection (Short Buildup Scan)**:
  - Scans for OTM strikes with a **Price Decrease >= 20%** and **OI Increase >= 25%**.
  - Enforces a minimum **100 points OTM** from ATM.
- **Sentiment Filter (Optional)**: PCR < 0.95 (Currently disabled).

### PE Sell (Bullish Signal)
- **VWAP Filter**: Futures Price must be **Above VWAP**.
- **Supertrend Filter**: Supertrend must be in **Uptrend (Green)** and price must be above the Supertrend band.
- **VWAP Distance Filter**: Price must be within **0.2%** of VWAP.
- **Strike Selection (Short Buildup Scan)**:
  - Scans for OTM strikes with a **Price Decrease >= 20%** and **OI Increase >= 25%**.
  - Enforces a minimum **100 points OTM** from ATM.
- **Sentiment Filter (Optional)**: PCR > 1.05 (Currently disabled).

---

## 3. Stop Loss & Trailing Strategy (TSL)
The strategy uses a **Low-Watermark Trailing Stop Loss** monitored tick-by-tick.

- **Base TSL**: 10% trailing from the lowest achieved option price.
- **Dynamic Tightening**: The TSL percentage reduces as you add pyramid levels:
  - **Level 0 (Initial Entry)**: 10% TSL
  - **Level 1 (Pyramid 1)**: 5% TSL
- **Calculation**: $TSL Price = LowestLTP \times (1 + TSL\%)$

---

## 4. Pyramiding Logic
The strategy scales into winning trades to maximize profit.
- **Trigger**: Add 1 lot when any existing position has an Unrealized Profit **>= 10%**.
- **Maximum Levels**: 2 pyramid levels (Total of 3 lots per trade).
- **Strike**: Same strike as the initial entry.

---

## 5. Exit Strategy
Trades are exited automatically if any of the following occur:
1. **TSL Triggered**: Option LTP crosses above the calculated TSL Price (**Real-time check**).
2. **Trend Reversal (Candle Close)**:
   - **For CE Sell**: Exit if Futures Price crosses **Above VWAP** OR **Supertrend turns Bullish**.
   - **For PE Sell**: Exit if Futures Price crosses **Below VWAP** OR **Supertrend turns Bearish**.
3. **Time Square-off**: Force exit all positions at **15:15**.

---

## 6. Sentiment Filter (PCR)
The strategy can use **Daily Change PCR** to confirm the trend, though it is currently optional.
- **NIFTY**: Centers analysis on ATM ± 4 strikes.
- **Update Frequency**: Refreshed from live market data every candle iteration.

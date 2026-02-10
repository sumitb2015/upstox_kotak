# Futures VWAP EMA Strategy Rules

This document outlines the core trading logic, risk management, and execution rules for the Futures VWAP EMA Options Selling strategy.

## 1. Strategy Overview
- **Instrument**: NIFTY Index Options
- **Underlying Reference**: NIFTY Futures (for Price/EMA) & NIFTY Index (for PCR)
- **Timeframe**: 1-minute or 3-minute candles (configurable)
- **Trade Type**: Option Selling (Shorting)
- **Expiry**: Current Week / Next Week (configurable)

---

## 2. Entry Strategy
The strategy looks for a confluence of **Price Action**, **Trend**, and **Market Sentiment**.

### CE Sell (Bearish Signal)
- **Price Filter**: Futures Price must be **Below VWAP**.
- **Trend Trigger** (Either):
   1. **Crossover**: Futures Price crosses **Below EMA (20)**.
   2. **Trend continuation**: Price is already below EMA (PCR check currently disabled).
- **Strike Selection**: ATM + 150 Points.

### PE Sell (Bullish Signal)
- **Price Filter**: Futures Price must be **Above VWAP**.
- **Trend Trigger** (Either):
   1. **Crossover**: Futures Price crosses **Above EMA (20)**.
   2. **Trend continuation**: Price is already above EMA (PCR check currently disabled).
- **Strike Selection**: ATM - 150 Points.

---

## 3. Stop Loss & Trailing Strategy (TSL)
The strategy uses a **Low-Watermark Trailing Stop Loss** calculated from the lowest price (LTP) the option has reached since entry.

- **Base TSL**: 20% trailing from the lowest achieved option price.
- **Dynamic Tightening**: The TSL percentage reduces as you add pyramid levels:
  - **Level 0 (Initial Entry)**: 20% TSL
  - **Level 1 (Pyramid 1)**: 15% TSL
  - **Level 2 (Pyramid 2)**: 10% TSL
- **Calculation**: $TSL Price = LowestLTP \times (1 + TSL\%)$

---

## 4. Pyramiding Logic
The strategy scale into winning trades to maximize profit.
- **Trigger**: Add 1 lot when any existing position has an Unrealized Profit **>= 10%**.
- **Maximum Levels**: 2 pyramid levels (Total of 3 lots per trade).
- **Strike**: Same strike as the initial entry.

---

## 5. Exit Strategy
Trades are exited automatically if any of the following occur:
1. **TSL Triggered**: Option LTP crosses above the calculated TSL Price.
2. **Trend Reversal (VWAP)**:
   - **For CE Sell**: Exit all if Futures Price crosses **Above VWAP**.
   - **For PE Sell**: Exit all if Futures Price crosses **Below VWAP**.
3. **Time Square-off**: Force exit all positions at **15:15**.
4. **Manual Override**: If the script is stopped (Ctrl+C), it will attempt to exit all open positions for safety.

---

## 6. Sentiment Filter (PCR - Currently Disabled)
The strategy uses the **Daily Change PCR** (Trending OI) which is more sensitive than Total PCR.
- **NIFTY**: Centers analysis on ATM ± 4 strikes (Total 9 strikes).
- **Update Frequency**: Refreshed every 3 minutes from live market data.

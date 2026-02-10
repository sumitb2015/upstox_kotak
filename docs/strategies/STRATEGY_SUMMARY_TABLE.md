# 📊 Strategy Comparison Matrix

This document provides a side-by-side comparison of all active strategies to help you choose the right one for the current market condition.

## 🚀 Quick Decision Guide

| Market Condition | Recommended Strategy | Risk Profile |
| :--- | :--- | :--- |
| **Trending (Strong Trend)** | `Futures VWAP EMA` | Medium-High |
| **Trending (Correction/Dip)** | `Dual Renko Dip` | Medium |
| **Volatile / Sideways** | `Dynamic Strangle` | Low-Medium |
| **Rangebound / Decay** | `VWAP Straddle V2` | Low |
| **Morning Open (9:15)** | `ORB Retest` | High |

---

## ⚔️ Detailed Strategy Comparison

| Strategy | Type | Capital Usage | Risk / Reward | Best Time | Worst Time |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Futures VWAP EMA** | Directional | High (Option Selling) | High Win Rate, Big Wins | Clean Trends | Choppy / Whipsaw Markets |
| **Dual Renko Dip** | Directional | High | High Precision, Quick Exits | Pullbacks in Trend | Deep V-Shape Reversals |
| **Dynamic Strangle** | Non-Directional | Medium | Consistent Small Gains | High IV, Wild Swings | One-Way Runaway Trends (without pullback) |
| **VWAP Straddle V2** | Non-Directional | Medium | Steady Decay | Dull/Flat Days | Sudden Gamma Spikes |
| **ORB Retest** | Directional | Medium | Fast Scalp | 9:15 - 10:00 AM | Mid-Day Chop |

---

## ⚙️ Technical Mechanics Summary

| Strategy | Entry Trigger | Stop Loss Type | Key Indicators | Management Style |
| :--- | :--- | :--- | :--- | :--- |
| **Futures VWAP EMA** | Price crosses EMA(20) + Regime Check | **Trailing (Low Watermark)** | VWAP, EMA(20), PCR | Pyramiding (Adds to winners) |
| **Dual Renko Dip** | Renko Pattern (Pullback -> Resume) | **Renko Reversal** + Premium SL | Renko (60/5), RSI | Pyramiding (Trend Following) |
| **Dynamic Strangle** | Delta Matching (~0.30) | **Ratcheting % SL** (Tightens only) | Delta, IV, Combined Premium | Active Adjusting (Shifts legs) |
| **VWAP Straddle V2** | Prem < VWAP + Skew Check | **Trailing Prem SL** | VWAP (Premium), Skew | Passive (Let it decay) |

---

## 🛡️ Risk Controls at a Glance

| Strategy | Max Pyramid Layers | Trailing Mechanism | Hard Stop Available? | Skew/Delta Guard? |
| :--- | :--- | :--- | :--- | :--- |
| **Futures VWAP EMA** | 2 Levels (3 Lots Max) | Yes (Starts @ 20%, tightens to 10%) | No (Rely on TSL) | N/A |
| **Dual Renko Dip** | 2 Levels | Yes (Option Renko Brick) | Yes (Hybrid Monitor) | N/A |
| **Dynamic Strangle** | N/A (Adjusts existing) | Yes (Tightens on Profit) | **Yes (Fixed Amount)** | **Yes (Delta/Ratio Guard)** |
| **VWAP Straddle V2** | None | Yes (Premium Based) | Yes | Yes (Runtime Skew > 60%) |

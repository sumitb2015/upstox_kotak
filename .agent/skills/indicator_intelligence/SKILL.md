---
name: Indicator Intelligence Skill
description: Deep dive into TA-Lib usage, custom formulas for Supertrend/Renko, and avoiding repaint issues.
---

# Indicator Intelligence Skill

This skill provides the exact specifications for calculating technical indicators in the Upstox ecosystem.

## 📏 1. Golden Rule: TA-Lib First
Always use `lib.utils.indicators` which wraps TA-Lib.
- **Why?** TA-Lib uses Wilder's Smoothing for RSI/ATR, which matches trading platforms (TradingView/ChartIQ).
- **Standard Periods**:
    - **RSI**: 14 periods.
    - **EMA**: 20, 50, 200 periods.
    - **ATR**: 14 periods.

## 📈 2. Custom Supertrend Formula
The standard Supertrend is NOT in TA-Lib. Use our custom implementation in `lib.utils.indicators.calculate_supertrend`.

**Logic**:
1. Calculate `Basic Upper/Lower Band`: `(High + Low) / 2 +/- (Multiplier * ATR)`.
2. Calculate `Final Upper/Lower Band`: Restrict bands from moving against the trend.
3. Determine Trend: Switch when Close crosses the opposite band.

```python
from lib.utils.indicators import calculate_supertrend
trend, value = calculate_supertrend(df, period=10, multiplier=3.0)
# trend: 1 (Uptrend), -1 (Downtrend)
```

## 🧱 3. Renko Bricks & EMA
Renko charts are time-independent.
- **Brick Size**: Calculated explicitly via ATR or fixed value (e.g., `10`).
- **Renko EMA**: Calculated on the *series of Brick Closes*, NOT time-based closes.
- **Function**: `lib.utils.indicators.calculate_renko_ema`.

## 🚫 4. Avoiding Repainting (Look-ahead Bias)
- **Problem**: Calculating indicators on the *current* incomplete candle (`-1`).
- **Solution**:
    1. Always use `get_intraday_data_v3` to fetch up to the *previous* minute.
    2. If using real-time tick data, aggregate ticks into a "tentative" candle.
    3. **Action Signal**: Confirm signals only on **Candle Close** (when the timestamp shifts).

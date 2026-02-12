---
name: Market Data Strategy Skill
description: Best practices for merging historical and intraday data to ensure accurate, non-repainting indicators.
---

# Market Data Strategy Skill

This skill defines the critical "Merged Data Pattern" required for accurate indicator calculation in the Upstox/Kotak ecosystem.

## 🚨 The Problem: Repainting
Using only API snapshots often leads to incomplete candles.
Using only historical API calls misses the current live candle.

## ✅ The Solution: Merged Data Pattern

### 1. The Recipe
To derive accurate indicators (RSI, EMA, Supertrend), you MUST:
1.  **Fetch History**: Get 5 days of 1-minute candles.
2.  **Fetch Live**: Get today's 1-minute candles (up to the last complete minute).
3.  **Merge**: Concatenate them, dropping duplicates.
4.  **Resample**: Convert the 1-minute series to your target timeframe (e.g., 5min, 15min).

### 2. Implementation Guide
```python
from lib.api.historical import get_intraday_data_v3
from lib.utils.indicators import resample_candles

def get_merged_data(token, key, timeframe):
    # 1. Get History (Last 5 days)
    history_df = get_historical_data(token, key, days=5)

    # 2. Get Intraday (Today)
    intraday_df = get_intraday_data_v3(token, key, "minute", 1)

    # 3. Merge
    full_df = pd.concat([history_df, intraday_df]).drop_duplicates(subset='timestamp')

    # 4. Resample
    resampled_df = resample_candles(full_df, timeframe)

    return resampled_df
```

### 3. Critical Rules
- **Lookback Period**: Ensure you fetch enough history for the indicator's warmup period (e.g., EMA-200 needs 200+ candles).
- **Timezone**: Ensure all timestamps are consistent (usually `Asia/Kolkata`).
- **NaN Handling**: Always fill or drop NaNs resulting from indicator calculations before making logic decisions.

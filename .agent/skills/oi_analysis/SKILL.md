---
name: OI Analysis Skill
description: Instructions for interpreting Option Interest (OI) data, sensing market sentiment, and calculating confidence scores.
---

# OI Analysis Skill

This skill details how to interpret Open Interest (OI) data to confirm trends and filter strategy entries.

## 📊 1. Core Concepts
- **PCR (Put-Call Ratio)**: `Total PE OI / Total CE OI`.
    - `> 1.0`: Bullish (More Puts sold).
    - `< 0.7`: Bearish (More Calls sold).
- **Sentiment Scoring**:
    - **Bullish**: PCR > 1.2 AND Price > VWAP.
    - **Bearish**: PCR < 0.6 AND Price < VWAP.
    - **Neutral**: PCR between 0.8 and 1.1.
- **OI Change from Open (Normalization)**:
    - `Current OI - OI at 9:15 AM (or first data point)`.
    - This reflects the **net accumulation** of positions during the current session.
    - **Interpretation**:
        - Positive & Rising: New positions being built (Strong conviction).
        - Negative/Falling from Peak: Positions being unwound (Profit booking or Panic).

## 🛠️ 2. Library Usage
Use `lib.utils.indicators` and `lib.oi_analysis` modules. **Do NOT** calculate PCR manually.

### Fetching OI Data
```python
from lib.oi_analysis.cumulative_oi_analysis import get_cumulative_oi

# Get systematic analysis
oi_data = get_cumulative_oi(token, expiry)
sentiment = oi_data.get('sentiment')  # 'BULLISH', 'BEARISH', 'NEUTRAL'
confidence = oi_data.get('confidence') # 0-100 score
```

## 📉 3. Interpreting Option Chain
When analyzing the full chain (via `lib.api.option_chain`):
- **Short Build-up**: Price Drop + OI Rise (Strong Bearish).
- **Long Build-up**: Price Rise + OI Rise (Strong Bullish).
- **Short Covering**: Price Rise + OI Drop (Bullish Reversal).
- **Long Unwinding**: Price Drop + OI Drop (Bearish Reversal).
- **OH (Open = High)**: Indicates a strike opened and immediately saw selling pressure (Bearish for that strike).
- **OL (Open = Low)**: Indicates a strike opened and immediately saw buying support (Bullish for that strike).

## 🚦 4. Confidence Thresholds
For a strategy to take a trade based on OI:
- **Directional Trades**: Require `confidence > 70` and matching sentiment.

## 🎯 5. Strike-Wise PCR Analysis
For granular analysis of specific deviations, use the `get_strike_pcr_structure` method in `CumulativeOIAnalyzer`.

### Features
- **ATM Detection**: Automatically identifies the At-The-Money strike.
- **Offset Filtering**: Returns data for a specific range (e.g., +/- 600 points).
- **Per-Strike Data**: Provides PCR, CE OI, and PE OI for every strike in the range.

### Usage Pattern
```python
from lib.oi_analysis.cumulative_oi_analysis import CumulativeOIAnalyzer

analyzer = CumulativeOIAnalyzer(access_token)
pcr_data = analyzer.get_strike_pcr_structure(offset=600)

# Check ATM PCR
atm = pcr_data['atm']
atm_pcr = pcr_data['pcr_map'].get(atm, 0)

if atm_pcr > 1.5:
    print("Strong Put Support at ATM")
```

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

## 🚦 4. Confidence Thresholds
For a strategy to take a trade based on OI:
- **Directional Trades**: Require `confidence > 70` and matching sentiment.
- **Non-Directional (Straddles)**: Require `confidence < 40` (Market indecision).

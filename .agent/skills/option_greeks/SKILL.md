---
name: Option Greeks Skill
description: Instructions for fetching and using Option Greeks (Delta, Gamma, Theta, Vega, IV) from the Upstox API.
---

# Option Greeks Skill

This skill details how to fetch and utilize Option Greeks for advanced analysis and strategy decision-making.

## 📊 1. Core Concepts
Use the `lib.api.market_quotes` module to fetch analytical data for option contracts.

- **Delta**: Sensitivity to underlying price change. range: 0 to 1 (Call), -1 to 0 (Put).
- **Theta**: Time decay per day.
- **Gamma**: Rate of change of Delta.
- **Vega**: Sensitivity to volatility change.
- **IV**: Implied Volatility.

## 🛠️ 2. Library Usage

### Fetching Greeks for a Single Instrument
```python
from lib.api.market_quotes import get_option_greek

# Get Greeks for a specific instrument key
# Returns a dict with 'delta', 'gamma', 'theta', 'vega', 'iv', etc.
greeks = get_option_greek(access_token, "NSE_FO|48203")

if greeks:
    data = greeks['data']['NSE_FO|48203']
    print(f"Delta: {data.get('delta')}")
    print(f"IV: {data.get('iv')}")
```

### Fetching Greeks for Multiple Instruments
```python
from lib.api.market_quotes import get_multiple_option_greeks

keys = ["NSE_FO|48203", "NSE_FO|48204"]
greeks = get_multiple_option_greeks(access_token, keys)

for key, data in greeks['data'].items():
    print(f"{key} -> Vega: {data.get('vega')}")
```

## 🚨 3. Key Notes
- **Instrument Keys**: Must use the full key (e.g., `NSE_FO|...`).
- **Data Availability**: Greeks may be null or 0 if the option is illiquid or deep OTM. Always check for `None`.
- **Latency**: This is a REST API call. Do not use inside a high-frequency tick loop. Use it for periodic updates (e.g., every 1-5 minutes or partially on candle close).

## 💡 4. Strategy Applications
- **Delta Hedging**: Calculate net portfolio delta and hedge with Futures.
- **Theta Decay**: Monitor theta to ensure positive time decay in selling strategies.
- **IV Rank**: Use IV to decide between debit (low IV) and credit (high IV) strategies.

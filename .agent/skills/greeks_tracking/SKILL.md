# Greeks Tracking Skill

This skill provides standardized logic for calculating and tracking Option Greeks, specifically Gamma Exposure (GEX), across the application.

## 🧮 GEX Calculation Standard

**Formula**: `GEX = Gamma * OI * LotSize * (SpotPrice^2) * 0.01`
- **Calls**: Positive GEX (Bullish bias / volatility suppression)
- **Puts**: Negative GEX (Bearish bias / volatility amplification)

### Lot Sizes (Standard 2026)
| Symbol | Lot Size |
| :--- | :--- |
| **NIFTY** | 65 |
| **BANKNIFTY** | 30 |
| **FINNIFTY** | 65 |
| **MIDCPNIFTY** | 50 |
| **SENSEX** | 10 |

## 📂 Core Components

- **`greeks_helper.py`**: Contains the `calculate_gex` function and historical cache management logic.
- **Background Worker**: Recommended polling interval is **1 minute** for active indices.

## 🚀 Usage Example

```python
from lib.utils.greeks_helper import calculate_net_gex

# In your FastAPI background task
df = get_option_chain_dataframe(token, sym_key, expiry)
net_gex = calculate_net_gex(df, symbol)
```

## 🔒 Safety Standards
- Always ensure `SpotPrice` is valid (greater than zero) before squaring.
- Handle missing `gamma` or `oi` columns gracefully by returning 0 GEX.
- Cache history using `(symbol, expiry)` tuples to prevent memory leaks across sessions.

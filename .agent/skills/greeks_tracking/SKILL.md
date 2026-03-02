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

## 💾 Persistence (Redis & CSV Storage)

Option Greeks are persisted using a dual-layer approach for speed and historical trend analysis.

- **Primary Cache (Speed)**: Redis Lists `redis_wrapper.push_json_list()`. Keys are suffixed with `symbol:expiry:date`.
- **Secondary Storage**: Daily CSV files appended via pandas.
- **Storage Class**: `lib.utils.greeks_storage.greeks_storage`
- **Location**: `c:/algo/upstox/data/greeks_history/`
- **File Format**: `greeks_[SYMBOL]_[YYYY-MM-DD].csv`
- **Fields**: `timestamp`, `strike_price`, `ce_delta`, `pe_delta`, `ce_gamma`, `pe_gamma`, `ce_vega`, `pe_vega`, `ce_theta`, `pe_theta`, `ce_gex`, `pe_gex`, `ce_oi`, `pe_oi`, `spot_price`, `expiry`.

### Data Flow
1. **Polling**: `poll_major_greeks` in `main.py` fetches data every 60s.
2. **Serializing**: Ensure any Pandas Timestamps or complex objects are stringified or handled safely before saving to Redis to prevent `Object of type Timestamp is not JSON serializable` errors.
3. **Saving**: Data is saved via `greeks_storage.save_snapshot(symbol, expiry, snapshot_df)`. This pushes to Redis list (capped at max length) and appends to CSV.
4. **Retrieving**: Use `greeks_storage.get_strike_history(symbol, expiry, strike)` which instantly returns cached Redis data if available, falling back to CSV.

## 📊 Strike-wise Historical Tracking

This feature allows plotting specific strike Greeks over time.

- **API Endpoint**: `/api/strike-greeks-history`
- **Frontend Page**: `strike_greeks.html` (Accessible via sidebar).

## 📂 Core Components

- **`greeks_helper.py`**: Calculation logic (GEX, snapshots).
- **`greeks_storage.py`**: Persistent storage management (CSV).
- **`strike_greeks.html`**: Plotly-based historical visualization.

## 🚀 Usage Example

### Saving Snapshot
```python
from lib.utils.greeks_storage import greeks_storage
# After calculating Greeks snapshot_df
greeks_storage.save_snapshot("NIFTY", "2026-02-26 15:30:00", snapshot_df)
```

### Retrieving History
```python
df_history = greeks_storage.get_strike_history("NIFTY", "2026-02-26 15:30:00", 25000.0)
```

## 🔒 Safety Standards
- **Inf/NaN Handling**: Always replace `inf` and `NaN` with 0 before serving to frontend.
- **Expiry Normalization**: Replace `T` characters in date strings if coming from frontend pickers.
- **Thread Safety**: Use `run_in_threadpool` for heavy CSV read operations in FastAPI.

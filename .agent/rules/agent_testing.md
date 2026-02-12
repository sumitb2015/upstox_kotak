---
trigger: always_on
---

# Agent Testing & Debugging Guide - Upstox Algorithmic Trading System

This guide covers **Unit Testing, Manual Verification, and TradingView Validation**.

---

## 🤖 1. Unit Testing (Deployment Check)

The system includes a comprehensive unit test suite in the `tests/` directory. Future agents MUST run these tests before declaring a complex refactor complete.

**Running the Suite:**
```bash
python -m unittest discover tests
```

**Key Test Files:**
- `tests/test_lib_utils.py`: Verifies correct instrument key, lot size, and expiry resolution.
- `tests/test_lib_indicators.py`: Validates TA-Lib wrappers (RSI, EMA, Supertrend) against mathematical proofs.
- `tests/test_strategy_core.py`: Verifies complex strategy logic (Pyramiding, Skew, Profit Locking) without API dependencies.

**Manual Integration Testing:**
For verifying live API calls (Market Depth, Full Quotes, Orders) without mocking:
```bash
python tests/manual/test_integration_suite.py
```
*Use this script to verify `get_full_market_quote` and other real-time data features.*

---

## 🤖 2. Testing & Debugging Strategy

### Quick testing
- Use `quick_help/upstox_api_reference.ipynb` for API exploration
- Run `debug_*.py` scripts for isolated testing
- Enable `dry_run=True` in strategy configs

### Debugging WebSocket
- Check connection status in logs
- Verify instrument keys are correct format
- Use `mode="full"` to see all available fields
- **Choose right WebSocket mode**: `ltpc` for price-only, `full` for complete data

### Testing Checklist
Before deploying any strategy:

- [ ] Test with `dry_run=True` for full day
- [ ] Verify VWAP calculation matches exchange
- [ ] **Validate indicators against TradingView** (see methodology below)
- [ ] Confirm lot sizes are correct
- [ ] Test WebSocket reconnection
- [ ] Validate market hours logic
- [ ] Test stop-loss triggers
- [ ] Check order placement in paper trading
- [ ] Verify position tracking accuracy
- [ ] Test error recovery (API failures)

---

## 👤 3. TradingView Validation Methodology (For Developers)

**Why validate against TradingView?**
- TradingView is the industry standard for charting
- Ensures your indicators match what traders see
- Catches calculation errors early
- Validates timeframe handling

### Method 1: Manual Spot Check (Quick)

1. **Open TradingView Chart**
   - Go to https://www.tradingview.com/chart/
   - Symbol: `NIFTY1!` (Nifty Futures) or `NIFTY` (Spot)
   - Timeframe: Match your strategy (1min, 3min, 5min)

2. **Add Indicators**
   - EMA: Add "Moving Average Exponential"
   - VWAP: Add "VWAP"
   - Volume: Already visible
   - RSI: Add "Relative Strength Index"

3. **Compare Values at Specific Times**
   ```python
   # In your strategy, log indicator values with timestamps
   logger.info(f"[{timestamp}] EMA(20): {ema:.2f} | VWAP: {vwap:.2f} | RSI: {rsi:.2f}")
   
   # Example output:
   # [2026-01-23 10:30:00] EMA(20): 25125.50 | VWAP: 25201.08 | RSI: 45.32
   ```

4. **Verify on TradingView**
   - Hover over the candle at 10:30:00
   - Check EMA value: Should be ~25125.50
   - Check VWAP value: Should be ~25201.08
   - Check RSI value: Should be ~45.32

**Acceptable Tolerance:**
- EMA/SMA: ±0.5 points (rounding differences)
- VWAP: ±1-2 points (calculation method differences)
- RSI: ±0.5 (rounding)
- Volume: Exact match

### Method 2: Export & Compare (Thorough)

1. **Export TradingView Data**
   ```
   TradingView Chart → Right-click → Export chart data
   Save as CSV
   ```

2. **Export Your Strategy Data**
   ```python
   # In your strategy
   df_1min.to_csv('strategy_data.csv', index=False)
   ```

3. **Compare in Excel/Python**
   ```python
   import pandas as pd
   
   tv_data = pd.read_csv('tradingview_export.csv')
   strategy_data = pd.read_csv('strategy_data.csv')
   
   # Merge on timestamp
   merged = pd.merge(tv_data, strategy_data, on='timestamp', suffixes=('_tv', '_strategy'))
   
   # Calculate differences
   merged['ema_diff'] = abs(merged['ema_tv'] - merged['ema_strategy'])
   merged['vwap_diff'] = abs(merged['vwap_tv'] - merged['vwap_strategy'])
   
   # Check max difference
   print(f"Max EMA difference: {merged['ema_diff'].max():.2f}")
   print(f"Max VWAP difference: {merged['vwap_diff'].max():.2f}")
   ```

### Method 3: Live Validation Script
Create a validation script that runs alongside your strategy:

```python
# validate_indicators.py
from lib.api.historical import get_intraday_data_v3
from lib.utils.indicators import calculate_ema, calculate_vwap
import pandas as pd

def validate_indicators(access_token, instrument_key):
    # Fetch 1-min candles
    candles = get_intraday_data_v3(access_token, instrument_key, "minute", 1)
    df = pd.DataFrame(candles)
    
    # Calculate indicators
    ema_20 = calculate_ema(df, 20)
    vwap = calculate_vwap(df)
    
    print(f"EMA(20): {ema_20:.2f} | VWAP: {vwap:.2f}")

# Usage
validate_indicators(token, "NSE_FO|49229")
```

### Common Discrepancies & Fixes

**1. VWAP Mismatch**
- **Problem**: Using API VWAP (exchange ATP) instead of Candle VWAP.
- **Solution**: Use `calculate_vwap(df)` on 1-min candles for TradingView match.

**2. EMA Starting Point**
- **Problem**: Insufficient data for EMA warmup.
- **Solution**: Ensure `len(df) >= period * 2`.

**3. Timeframe Mismatch**
- **Problem**: Comparing 1-min data to 3-min chart.
- **Solution**: Resample data correctly before calculation.

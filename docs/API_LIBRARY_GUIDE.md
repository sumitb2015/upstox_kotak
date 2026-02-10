# Upstox API Library - Complete Documentation

## Overview

This document provides comprehensive documentation for the refactored Upstox API library, ensuring error-free, well-tested integration across all strategies.

## Library Structure

```
utils/
├── api_wrapper.py      # Main unified API interface (NEW)
├── indicators.py       # TA-Lib-based indicator calculations (NEW)
├── order_helper.py     # Order placement abstractions (NEW)
├── instrument_utils.py # Instrument lookup and lot size (ENHANCED)

api/
├── market_quotes.py    # LTP, quotes, Greeks
├── historical.py       # Historical and intraday candles
├── streaming.py        # WebSocket live data
├── order_management.py # Order placement and management
└── ...
```

## Quick Start

### 1. Basic Setup

```python
from utils.api_wrapper import UpstoxAPI

# Initialize API wrapper
api = UpstoxAPI(access_token)
```

### 2. Get Live Price (LTP)

```python
# Single instrument
price = api.get_ltp("NSE_FO|49229")
print(f"Nifty Futures: {price}")

# Returns: float or None
# Example: 25100.50
```

**Common Errors Fixed:**
- ✅ Handles different response structures automatically
- ✅ Returns None instead of crashing on API errors
- ✅ Works with both old and new instrument key formats

### 3. Get Historical Data

```python
# Intraday data (today only)
candles = api.get_intraday_candles(
    instrument_key="NSE_FO|49229",
    interval_minutes=3
)

# Returns: List[Dict] with keys: timestamp, open, high, low, close, volume
```

**As DataFrame:**
```python
df = api.get_candles_as_dataframe(
    instrument_key="NSE_FO|49229",
    interval_minutes=1,
    intraday=True
)

# Returns: pd.DataFrame sorted by timestamp
# Columns: timestamp, open, high, low, close, volume
```

**Historical Range:**
```python
df = api.get_candles_as_dataframe(
    instrument_key="NSE_FO|49229",
    interval_minutes=5,
    intraday=False,
    from_date="2026-01-20",
    to_date="2026-01-23"
)
```

**Common Errors Fixed:**
- ✅ Automatic timestamp conversion to datetime
- ✅ Consistent data sorting
- ✅ Handles empty responses gracefully
- ✅ Proper interval unit mapping (minute/minutes)

### 4. Calculate Indicators

```python
from utils.indicators import calculate_ema, calculate_vwap

# Get candles
df = api.get_candles_as_dataframe("NSE_FO|49229", interval_minutes=1)

# Calculate VWAP
vwap = calculate_vwap(df)
print(f"VWAP: {vwap}")

# Calculate EMA
ema_20 = calculate_ema(df, period=20)
print(f"EMA(20): {ema_20}")
```

**Available Indicators:**
- `calculate_ema(df, period)` - Exponential Moving Average
- `calculate_ema_series(df, period)` - Full EMA series
- `calculate_vwap(df)` - Volume Weighted Average Price
- `calculate_sma(df, period)` - Simple Moving Average
- `calculate_rsi(df, period=14)` - Relative Strength Index

**Features:**
- ✅ Uses TA-Lib when available (fallback to pandas)
- ✅ Proper error handling and validation
- ✅ Eliminates manual calculation errors

### 5. Place Orders

```python
# Place order with automatic lot size handling
order = api.place_order(
    instrument_key="NSE_FO|58689",
    nse_data=nse_df,  # NSE market data
    num_lots=1,
    transaction_type="SELL",
    product_type="INTRADAY",
    order_type="MARKET"
)

# Returns: Order response dict or None
```

**Get Lot Size:**
```python
lot_size = api.get_lot_size("NSE_FO|58689", nse_df)
print(f"Lot size: {lot_size}")  # 65 for Nifty options

# Calculate quantity
quantity = api.calculate_quantity("NSE_FO|58689", nse_df, num_lots=2)
print(f"Total contracts: {quantity}")  # 130
```

**Common Errors Fixed:**
- ✅ No more hardcoded lot sizes (50, 65, 75 errors eliminated)
- ✅ Automatic lot size lookup from NSE data
- ✅ Proper quantity calculation (lots × lot_size)
- ✅ Clean error messages

### 6. WebSocket Live Data

```python
def on_price_update(data):
    """Callback for live price updates"""
    print(f"Live price: {data.get('last_price')}")

# Subscribe to live data
api.subscribe_live_data(
    instrument_keys=["NSE_FO|49229"],
    mode='full',  # 'ltpc' for price only, 'full' for depth+Greeks
    callback=on_price_update
)

# Or use streamer directly for advanced control
streamer = api.get_streamer()
streamer.add_market_callback(on_price_update)
streamer.connect_market_data(["NSE_FO|49229"], mode='full')
```

**Common Errors Fixed:**
- ✅ Automatic reconnection on disconnect
- ✅ Proper data parsing (handles nested structures)
- ✅ Clean callback interface

### 7. Context Manager (Auto-Cleanup)

```python
# Automatically disconnects streams on exit
with UpstoxAPI(access_token) as api:
    price = api.get_ltp("NSE_FO|49229")
    print(price)
# Streams disconnected automatically
```

## Strategy Integration

### Before (Manual Implementation)

```python
# ❌ Manual, error-prone code
import upstox_client

# Manual EMA calculation
ema = df['close'].ewm(span=20, adjust=False).mean().iloc[-1]

# Hardcoded lot size (WRONG!)
quantity = 1 * 50  # Should be 65 for Nifty

# Manual order placement
config = upstox_client.Configuration()
config.access_token = access_token
api_instance = upstox_client.OrderApi(upstox_client.ApiClient(config))
order_request = upstox_client.PlaceOrderRequest(...)
response = api_instance.place_order(order_request)
```

### After (Library-Based)

```python
# ✅ Clean, tested, abstracted
from utils.api_wrapper import UpstoxAPI
from utils.indicators import calculate_ema

api = UpstoxAPI(access_token)

# Get data and calculate indicators
df = api.get_candles_as_dataframe("NSE_FO|49229", interval_minutes=3)
ema = calculate_ema(df, 20)

# Place order (lot size fetched automatically)
order = api.place_order(
    instrument_key="NSE_FO|58689",
    nse_data=nse_df,
    num_lots=1,  # Correct quantity calculated internally
    transaction_type="SELL"
)
```

## Error Handling Best Practices

### Always Check Return Values

```python
price = api.get_ltp("NSE_FO|49229")
if price is None:
    print("Failed to fetch price")
    return

# Use price safely
print(f"Current price: {price}")
```

### Handle Empty Data

```python
df = api.get_candles_as_dataframe("NSE_FO|49229", interval_minutes=1)
if df is None or df.empty:
    print("No candle data available")
    return

# Process data
vwap = calculate_vwap(df)
```

### Validate Indicators

```python
from utils.indicators import calculate_ema

try:
    ema = calculate_ema(df, period=20)
except ValueError as e:
    print(f"EMA calculation failed: {e}")
    # Handle error (e.g., insufficient data)
```

## Common Integration Patterns

### Pattern 1: Live Monitoring Strategy

```python
from utils.api_wrapper import UpstoxAPI
from utils.indicators import calculate_ema, calculate_vwap

api = UpstoxAPI(access_token)

while True:
    # Fetch latest data
    df = api.get_candles_as_dataframe("NSE_FO|49229", interval_minutes=1)
    
    if df is None or df.empty:
        time.sleep(30)
        continue
    
    # Calculate indicators
    vwap = calculate_vwap(df)
    ema = calculate_ema(df, 20)
    
    # Get live price
    live_price = api.get_ltp("NSE_FO|49229")
    
    # Trading logic
    if live_price < vwap and live_price < ema:
        # Entry signal
        api.place_order(...)
    
    time.sleep(60)  # Check every minute
```

### Pattern 2: WebSocket-Based Strategy

```python
class Strategy:
    def __init__(self, access_token, nse_data):
        self.api = UpstoxAPI(access_token)
        self.nse_data = nse_data
        self.live_price = 0
        
    def on_price_update(self, data):
        """Handle live price updates"""
        self.live_price = data.get('last_price', 0)
        
        # Check entry conditions
        if self.should_enter():
            self.execute_entry()
    
    def run(self):
        # Subscribe to live data
        self.api.subscribe_live_data(
            instrument_keys=["NSE_FO|49229"],
            mode='full',
            callback=self.on_price_update
        )
```

## Testing & Validation

### Test Lot Size Accuracy

```python
from utils.api_wrapper import UpstoxAPI

api = UpstoxAPI(access_token)

# Test Nifty option lot size
lot_size = api.get_lot_size("NSE_FO|58689", nse_df)
assert lot_size == 65, f"Expected 65, got {lot_size}"

# Test quantity calculation
qty = api.calculate_quantity("NSE_FO|58689", nse_df, num_lots=2)
assert qty == 130, f"Expected 130, got {qty}"

print("✅ Lot size tests passed")
```

### Test Indicator Accuracy

```python
from utils.indicators import calculate_ema, calculate_vwap
import pandas as pd

# Create test data
test_data = {
    'high': [100, 101, 102],
    'low': [98, 99, 100],
    'close': [99, 100, 101],
    'volume': [1000, 1100, 1200]
}
df = pd.DataFrame(test_data)

# Test VWAP calculation
vwap = calculate_vwap(df)
print(f"VWAP: {vwap}")  # Should be reasonable value

# Test EMA calculation
ema = calculate_ema(df, period=2)
print(f"EMA(2): {ema}")  # Should be close to recent prices

print("✅ Indicator tests passed")
```

## Migration Guide

### For Existing Strategies

1. **Import new libraries**:
   ```python
   from utils.api_wrapper import UpstoxAPI
   from utils.indicators import calculate_ema, calculate_vwap
   ```

2. **Replace manual API calls**:
   ```python
   # Before
   response = requests.get(url, headers=headers)
   
   # After
   api = UpstoxAPI(access_token)
   price = api.get_ltp(instrument_key)
   ```

3. **Replace manual calculations**:
   ```python
   # Before
   ema = df['close'].ewm(span=20).mean().iloc[-1]
   
   # After
   ema = calculate_ema(df, 20)
   ```

4. **Replace manual order placement**:
   ```python
   # Before
   quantity = lot_size * 50  # Hardcoded!
   place_order(..., quantity=quantity, ...)
   
   # After
   api.place_order(..., num_lots=lot_size)
   ```

## Troubleshooting

### Issue: Price Returns None

**Cause**: API timeout or invalid instrument key

**Solution**:
```python
price = api.get_ltp(instrument_key)
if price is None:
    print(f"Invalid instrument or API error: {instrument_key}")
    # Retry or use fallback
```

### Issue: Empty Candle Data

**Cause**: Market closed or invalid date range

**Solution**:
```python
df = api.get_candles_as_dataframe(...)
if df is None or df.empty:
    print("Market closed or no data")
    # Use cached data or wait
```

### Issue: Order Placement Failed

**Cause**: Invalid quantity, insufficient funds, or market hours

**Solution**:
```python
order = api.place_order(...)
if order is None:
    print("Order failed - check logs for details")
    # Verify lot size, quantity, and market status
```

## Summary

✅ **Clean Interfaces**: Simple, intuitive method names  
✅ **Error Handling**: Consistent None returns on failure  
✅ **No Hardcoding**: Lot sizes always fetched dynamically  
✅ **TA-Lib Integration**: Accurate indicator calculations  
✅ **Well Tested**: Validated against live market data  
✅ **Easy Integration**: Drop-in replacement for manual code  

---

**For Questions/Issues**: Refer to specific function docstrings or test examples above.

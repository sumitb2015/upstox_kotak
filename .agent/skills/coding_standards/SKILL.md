---
name: Coding Standards & Safety
description: Best practices for error handling, thread safety, indicator warmup, and production safety.
---

# Agent Best Practices - Upstox Algorithmic Trading System

This guide covers **Error Handling, Performance Optimization, Standard Checklists, and Production Considerations**.

---

## 🤖 1. Common Pitfalls to Avoid

❌ **DON'T:**
- Hardcode lot sizes (use `get_lot_size()` or `place_option_order()`)
- Manually calculate VWAP from quotes (use `get_vwap()`)
- Ignore key mapping issues in Upstox responses
- Create duplicate indicator functions or manual math - **ALWAYS use TA-Lib** via `lib.utils.indicators` for standard indicators.
- Ignore Supertrend's custom calculation - it is the ONLY non-TA-Lib standard indicator.
- Manually calculate EMA on Renko bricks - **ALWAYS use `calculate_renko_ema`** in `lib.utils.indicators`. Renko EMA must be time-independent and based on brick closes.
- Place orders without checking margin (use `lib.utils.margin_calculator`)
- Forget critical imports (Always check for `pandas as pd` and `timedelta` in `live.py`)

✅ **DO:**
- Check `FUNCTION_REFERENCE.md` before writing new functions
- Use expiry cache for repeated expiry lookups
- Implement proper error handling and logging
- Use WebSocket for real-time data, not polling
- Test with dry_run mode before live trading

---

## 🤖 2. Thread Safety in Multi-threaded Scripts
Strategies often use WebSockets (which run in a separate thread) to update position prices or monitor exits.

> [!WARNING]
 Always use `threading.RLock()` (not `Lock()`) when accessing or modifying shared state in complex strategies. A re-entrant lock prevents deadlocks if a locked method calls another method that also attempts to acquire the same lock.

```python
import threading

class MyStrategy:
    def __init__(self, ...):
        self.positions = []
        self.lock = threading.RLock() # MANDATORY for complex state logic
        
    def on_market_data(self, data):
        # Update price from WebSocket thread
        with self.lock:
            self.helper_method() # Doesn't deadlock with RLock
            
    def helper_method(self):
        with self.lock: # Re-enters existing lock
            pass
```

---

## 🤖 3. Indicator Warmup & Live Accuracy
To avoid `NaN` values (warmup) and ensure indicators reflect the latest live candles, you **MUST** merge historical data with intraday data. Relying solely on the `historical-candle` API is strictly prohibited for live signals as its latest candle is often delayed by minutes.

### The Mandatory Merged Data Pattern:
1. **Fetch History**: Get 2-5 days of 1-minute data for indicator warmup (requires ~1000-2000 bars).
2. **Fetch Intraday**: Get today's 1-minute candles using `get_intraday_data_v3`.
3. **Merge & Clean**: Concat them, ensuring history stops before today starts to avoid duplicates.
4. **Resample**: Resample the 1-minute merged data to your strategy timeframe (e.g., 3min or 5min).
5. **Calculate**: Run your indicator (RSI, EMA, etc.) on the resampled data.

```python
# Implementation Flow
from lib.api.historical import get_historical_data, get_intraday_data_v3

# 1. Base History
hist = get_historical_data(token, key, interval='minute', lookback_minutes=2000)
# 2. Fresh Today
intra = get_intraday_data_v3(token, key, interval_unit='minute', interval_value=1)

# 3. Merge & Resample
df = merge_and_resample(hist, intra, rule='3min')

# 4. Calculate
rsi = calculate_rsi(df, period=14)
```

---

## 🤖 4. Error Handling & Validation

**Key mapping issues (Upstox API quirk):**
- Upstox returns keys with `:` instead of `|` in some responses
- Always use `get_market_quote_for_instrument()` or `get_vwap()` which handle this
- Never directly access quote responses without key validation

**Market hours validation:**
```python
from lib.utils.market_validation import is_trading_hours

if not is_trading_hours():
    print("Market closed")
    return
```

### Common Bugs & Fixes

**Bug 1: VWAP Returns 0**
```python
# ❌ Problem: Key mapping mismatch
quotes = get_market_quotes(token, [key])
vwap = quotes[key]['average_price']  # KeyError or 0

# ✅ Solution: Use helper
vwap = get_vwap(token, key)  # Handles key mapping
```

**Bug 2: Stale Indicator Values**
```python
# ❌ Problem: Not updating previous values
if price < ema:  # Always uses latest EMA
    enter()

# ✅ Solution: Track previous for crossover
self.prev_ema = self.current_ema
self.current_ema = calculate_ema(df, 20)

if self.prev_close > self.prev_ema and close < ema:
    enter()  # Crossover detected
```

**Bug 3: Entry on Historical Signal**
```python
# ❌ Problem: Trading on old signal
candles = fetch_candles()
if check_entry(candles):
    enter()  # Might be old signal!

# ✅ Solution: Warmup + timestamp check
if self.candles_processed < 2:
    return  # Skip first candle
```

**Bug 4: JSON Serialization Error (Timestamps/NaN)**
```python
# ❌ Problem: Passing raw Pandas Timestamps or NaNs directly to Redis/FastAPI JSON response
df.to_dict('records') # Fails if index or columns contain raw pd.Timestamp
redis_wrapper.push_json_list(key, payload) # TypeError: Object of type Timestamp is not JSON serializable

# ✅ Solution: Convert explicitly before dict transformation
df['timestamp'] = df['timestamp'].astype(str)
# OR handle NaNs:
df = df.fillna(0)
```

**Bug 5: WebSocket Data Structure Assumptions & Casing**
```python
# ❌ Problem: Assuming snake_case or specific nesting in raw feeds
ltp = data.get('market_ff', {}).get('ltpc', {}).get('ltp') # Fails: Casing is wrong

# ✅ Solution: Use the UpstoxStreamer library (It handles auto-flattening and normalization).
# CRITICAL: Be aware that Upstox uses mixed casing in its raw WebSocket JSON:
# - 'marketFF' (CamelCase, not market_ff)
# - 'ltpC' or 'ltpc' (Inconsistent casing)
# - 'vWap' (CamelCase, not vwap)
# - 'instrument_key' (Sometimes uses ':' instead of '|')

ltp = data.get('ltp') or data.get('last_price')
if not ltp:
    logger.warning("Empty LTP in feed - Check casing/normalization in library")
```

---

## 👤 5. Production Considerations

### Market Hours Validation
```python
# Always check before trading
from datetime import datetime, time as dt_time

entry_start = dt_time(9, 20)  # After opening volatility
exit_time = dt_time(15, 18)   # Before market close

current_time = datetime.now().time()
if current_time < entry_start or current_time > exit_time:
    return  # Don't trade
```

### Error Recovery
```python
# Always wrap API calls
try:
    candles = get_intraday_data_v3(...)
    if not candles:
        logger.warning("No candles, retrying...")
        time.sleep(30)
        continue
except Exception as e:
    logger.error(f"API error: {e}")
    time.sleep(60)
    continue
```

### Logging Best Practices
```python
# Use structured logging with UTF-8 encoding for emojis
import sys
import io

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('strategy.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# Force UTF-8 and line-buffering on Windows (prevents emoji errors and out-of-sequence logs)
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

# Now emojis work in logs
logger.info(f"🕯️ Candle {timestamp} | Close: {close} | VWAP: {vwap} | Vol: {vol}")
logger.info(f"🎯 ENTRY: {direction} {strike} @ ₹{price}")
logger.warning(f"⚠️ TSL triggered at ₹{price}")
logger.error(f"❌ Order failed: {error}")
```

### Standard Console Output
To prevent misleading or interleaved output (e.g., library `print` statements appearing after strategy termination), follow these rules:

1. **Prefer Logger over Print**: Use the `logger` object for all strategy-level updates. **NEVER use `print()` in library files** as it causes asynchronous buffering issues on Windows, leading to misleading console output.
2. **Broker-Specific Tagging**: Always prefix messages with the broker or component name in brackets.
   - `[UPSTOX]` - Data, Analysis, Streaming
   - `[KOTAK]` - Orders, Execution
   - `[CORE]` - Logic, Strategy state
3. **Emoji Standards**:
   - 📊 `[UPSTOX]` - Data loading
   - 🔐 `[KOTAK]` - Authentication
   - 🎯 `[CORE]` - Entry events
   - ⚖️ `[CORE]` - Adjustments
   - 🚪 `[CORE]` - Exit events
   - ✅ Success / ⚠️ Warning / ❌ Error
4. **Flush Output on Windows**: Always initialize stdout to ensure immediate flushing and UTF-8 support.

```python
# Standard Logger Pattern
logger.info("🔐 [KOTAK] Authenticating execution broker...")
logger.info("📊 [UPSTOX] Loading market data...")
logger.info(f"🎯 [CORE] Entry at {strike} | Premium: {total_premium}")
```

### Access Token Loading
```python
# Always implement dry_run
if self.config.get('dry_run', False):
    logger.info("[DRY RUN] Would place order: ...")
    # Simulate position tracking
    self.positions.append(simulated_position)
else:
    # Real order
    order = place_option_order(...)
```

---

## 👤 6. Performance Optimization

**1. Cache NSE Data**
```python
# ❌ Don't reload every time
def get_instrument():
    nse_data = download_nse_market_data()  # Slow!
    return get_future_instrument_key("NIFTY", nse_data)

# ✅ Load once, reuse
class Strategy:
    def __init__(self):
        self.nse_data = download_nse_market_data()  # Once
    
    def get_instrument(self):
        return get_future_instrument_key("NIFTY", self.nse_data)
```

**2. Use Expiry Cache**
```python
# ❌ Repeated API calls
expiry = get_nearest_expiry(token, "NSE_INDEX|Nifty 50")

# ✅ Cached
from lib.utils.expiry_cache import get_expiry_for_strategy
expiry = get_expiry_for_strategy(token, "current_week", "NIFTY")
```

**3. Batch API Calls**
```python
# ❌ Multiple calls
ce_quote = get_ltp_quote(token, ce_key)
pe_quote = get_ltp_quote(token, pe_key)

# ✅ Single call
quotes = get_multiple_ltp_quotes(token, [ce_key, pe_key])
```

---

## 🤖 7. Strategy Quality & Bug-Free Checklist

Before finalizing any strategy, verify it against these common bugs and architectural requirements:

*   **Thread Safety**: If using WebSockets (UpstoxStreamer), always use `threading.Lock()` for any list/dict modifications (especially `self.positions` and `self.current_direction`). WebSocket callbacks run in a separate thread.
*   **Intraday Indicator Reset**:
    *   **VWAP**: MUST only use candles from the **current trading day** (session reset at 9:15 AM). 
        *   ✅ **CORRECT**: Use `df_intraday` directly (from `get_intraday_data_v3`) for VWAP calculation. This dataframe already contains only today's session data.
        *   ❌ **INCORRECT**: Do NOT calculate VWAP on stitched historical + intraday data, as this includes previous days and produces incorrect values.
        *   ❌ **INCORRECT**: Do NOT filter stitched data by date (`df[df['timestamp'].dt.date == today]`) as primary method - use this only as a fallback if intraday API fails.
        *   **Implementation Pattern**:
        ```python
        # Fetch data
        hist_data = get_historical_data(...)  # For indicator warmup
        intraday_data = get_intraday_data_v3(...)  # Today's session only
        
        # Stitch for Supertrend/EMA (needs historical warmup)
        df_combined = stitch_data(hist_data, intraday_data)
        
        # Calculate indicators separately:
        # 1. Supertrend/EMA: Use combined data
        update_indicators(df_combined)
        
        # 2. VWAP: Use ONLY intraday data
        if not df_intraday.empty:
            vwap = calculate_vwap(df_intraday)  # ✅ Correct
        ```
    *   **EMA/RSI/Supertrend**: These NEED historical data (warmup). **Mandatory**: Merge historical data with intraday data (Pattern in Rule 3) to ensure you are calculating on the latest live candle, as the historical API alone can be stale.
*   **Instrument Resolution**:
    *   **Upstox Key**: Used for Market Data and WebSocket subscriptions (e.g., `NSE_FO|58689`).
    *   **Kotak Symbol**: Used for Order Placement (e.g., `NIFTY2601624200CE`).
    *   **Always resolve BOTH separately** using `lib.utils.instrument_utils` and `kotak_api.lib.trading_utils`.
*   **Timezone & Formatting**: Use `datetime.now().strftime('%H:%M:%S')` for logs. Ensure time comparisons use `datetime.time` objects.
*   **Abstract Class Implementation**: Always ensure that all abstract methods defined in `strategy_core.py` (e.g., `execute_trade`) are implemented in `live.py` with the **EXACT same name**. Pyright or manual instantiation will fail if even one is missing.
*   **Authentication Helper**: NEVER use `os.getenv("UPSTOX_ACCESS_TOKEN")` directly in your strategies. ALWAYS use `from lib.core.authentication import get_access_token` followed by `token = get_access_token()`. This handles file-based tokens, environment variables, and refreshes automatically.
*   **NoneType Guards**: Always check `if not token: sys.exit(1)` after fetching it. Slicing or using a `None` token in `UpstoxStreamer` will cause a `TypeError`.
*   **Formatted Logging**: Follow the emoji and tagging standard (Rule 5).
*   **Lot Size Resolution**: Never hardcode lot sizes (e.g., 50). Use `lib.utils.instrument_utils.get_lot_size(key, nse_data)` to get the current lot size for Nifty (75), BankNifty (30), etc.
*   **Expiry Safety**: When using `get_option_instrument_key` (and related utils), you **MUST** pass the `expiry_date` argument (e.g., `expiry_date=self.expiry`). Without this, the function defaults to the *Current Week*, which causes **Price Selection Logic Mismatches** for strategies trading Next Week or Monthly contracts (Price 74 vs 200).
*   **Exit Conditions**:
    *   Always implement a **Time Square-off** (e.g., 15:15).
    *   **Ctrl+C Handling**: Always wrap the main loop in `try-except KeyboardInterrupt`. Inside the handler, you MUST:
        1. Call `self.execute_exit_all()` to close positions.
        2. Call `self.streamer.disconnect_all()` to close background threads.
        3. Call `os._exit(0)` to force the process to terminate.
*   **Dry Run Support**: Every strategy must respect `self.dry_run = config.get('dry_run', True)` in the `OrderManager` and local logic.
*   **WebSocket Full Feed Stability**: When using `mode="full"`, ensure you pass it to BOTH `connect_market_data()` and any subsequent `subscribe_market_data()` calls. The SDK may default back to `ltpc` if the mode is not explicitly repeated during re-subscriptions.

---

## 🤖 9. Low-Latency WebSocket Candles (OHLC)

For strategies requiring per-minute indicator or Renko updates (e.g., Aggressive Renko Dip), you **MUST** avoid REST API polling for candles. Instead, use the built-in WebSocket OHLC extraction.

### Implementation Pattern:
1. **Connect in Full Mode**: Use `mode="full"` to receive the `marketOHLC`/`indexOHLC` envelopes.
2. **Handle Wrapper**: The `UpstoxStreamer` automatically unwraps the finalized 1-minute candle into a dedicated `ohlc_1m` key.
3. **Instant Processing**: Trigger your logic (indicator update, Renko brick check) as soon as the `ohlc_1m` packet arrives.

```python
# Strategy level reception (live.py)
def on_market_data(self, data):
    ohlc_1m = data.get('ohlc_1m')
    if ohlc_1m:
        # Finalized candle close price (e.g. 25575.3)
        close = ohlc_1m['close']
        timestamp = ohlc_1m['timestamp']
        # Process instantly (Zero delay)
        self.process_minute_logic(close, timestamp)
```

**Benefits**:
- **Zero REST Calls**: Prevents rate-limiting and reduces network overhead.
- **Lower Latency**: Receive the candle close within milliseconds of the minute boundary.
- **Consistency**: Historical data (WARMUP) followed by WebSocket data (LIVE) provides a perfectly continuous data stream.

---

## 🤖 8. Multi-Leg Order Safety (New)

When implementing strategies involving multiple legs (Straddles, Strangles, Iron Condors), you MUST ensure **Atomic Execution** or **Rollback Logic** to prevent naked positions.

 **Why?**
- If Leg A (CE) executes, but Leg B (PE) fails (due to margin, API timeout, or rate limit), you are left with a naked directional position instead of a hedged neutral one.

✅ **DO:**
- Track successful order executions in a temporary list.
- If *any* leg in the sequence fails, immediately trigger a **ROLLBACK**.
- **Rollback**: Place an exit order for all successful legs and mark the trade as `FAILED` or `CLOSED` in your state manager.
- **CRITICAL: Always retrieve and use actual execution prices** for BOTH **Entry and Exit** orders using `OrderManager.get_execution_price(order_id)`. 
- **Wait for confirmation**: Wait at least 1 second after `place_order` before calling `get_execution_price` to allow exchange processing.
- **State Integrity**: Do not clear internal position state until an exit fill is verified. If `get_execution_price` fails, alert the user and maintain the position state to prevent naked positions.

```python
legs = []
failed = False

for leg in target_legs:
    order_id = place_order(leg)
    if order_id:
        # ✅ Get actual execution price
        exec_price = order_manager.get_execution_price(order_id)
        leg.entry_price = exec_price  # Use actual fill price
        legs.append(leg) 
    else:
        failed = True
        break

if failed:
    logger.warning("Construction failed. Rolling back...")
    exit_positions(legs) # Immediate exit of partials
```

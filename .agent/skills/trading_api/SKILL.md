---
name: Trading API & Library Guide
description: Documentation for Upstox/Kotak core libraries, market data, and order management.
---

# Agent API & Library Guide - Upstox Algorithmic Trading System

This guide covers the **Core Libraries, Data Fetching, Order Execution, and WebSocket Streaming**.

---

## 🤖 1. Library Usage - ALWAYS Use Existing Functions

> [!IMPORTANT]
> **COMPREHENSIVE API REFERENCE**: Always refer to [quick_help/FUNCTION_REFERENCE.md](file:///c:/algo/upstox/quick_help/FUNCTION_REFERENCE.md) to access all documented functions in the Upstox API library. Do NOT reinvent functions that already exist.

**CRITICAL**: Before writing any new code, check the reference document:
- **Reference Document**: [FUNCTION_REFERENCE.md](file:///c:/algo/upstox/quick_help/FUNCTION_REFERENCE.md) - Contains 120+ documented functions for Upstox & Kotak.
- **Common Modules**:
  - `lib.api.market_data` - Market quotes, VWAP, NSE data
  - `lib.api.historical` - Intraday & historical candles
  - `lib.api.option_chain` - Option chain, Greeks, expiries
  - `lib.api.order_management` - Place, modify, cancel orders
  - `lib.utils.indicators` - EMA, SMA, RSI, ATR, ADX, VWAP (All using TA-Lib), Supertrend (Custom)
  - `lib.utils.order_helper` - Simplified order placement with auto lot-size
  - `lib.api.market_quotes` - Full market quotes (Depth, OHLC, OI)
  - `lib.utils.expiry_cache` - Cached expiry fetching

**GOLDEN RULE**: DO NOT Assume Functions Exist!
Before using any `lib.*` function:
1. Check `quick_help/FUNCTION_REFERENCE.md`.
2. If it's not there, grep the codebase to find the correct name.
3. If it doesn't exist, IMPLEMENT IT FIRST, document it, then use it.

**Example - WRONG vs RIGHT:**
```python
# ❌ WRONG - Manual VWAP calculation
quotes = get_market_quotes(token, [key])
vwap = quotes[key].get('average_price', 0)  # May return 0 due to key mapping issues

# ✅ RIGHT - Use standard helper
from lib.api.market_data import get_vwap
vwap = get_vwap(token, key)  # Handles key mapping automatically

# ✅ RIGHT - Fetch Full Market Quote (Depth, OHLC, OI)
from lib.api.market_quotes import get_full_market_quote
quote = get_full_market_quote(token, key)
```

---

## 🤖 2. Data Fetching Patterns

### Intraday Candles
```python
from lib.api.historical import get_intraday_data_v3

# 1-minute candles
candles = get_intraday_data_v3(token, instrument_key, "minute", 1)


# 5-minute candles
candles = get_intraday_data_v3(token, instrument_key, "minute", 5)
```

### Historical Data (V3)
Fetch historical candles for a specific date range.

```python
from lib.api.historical import get_historical_data_v3

# Fetch daily candles for the last 30 days
candles = get_historical_data_v3(
    token, 
    instrument_key="NSE_INDEX|Nifty 50", 
    interval_unit="day", 
    interval_value=1,
    from_date="2025-01-01",
    to_date="2025-01-30"
)
```

### OHLC Queries (Live V3)
Use `get_ohlc_quote` for lightweight live OHLC data (Open, High, Low, Close, Volume) without full depth.

```python
from lib.api.market_quotes import get_ohlc_quote

# Get Live & Previous OHLC
# Interval: '1d', '1m', '30m'
ohlc = get_ohlc_quote(token, "NSE_INDEX|Nifty 50", interval="1d")

if ohlc:
    data = ohlc['data']["NSE_INDEX|Nifty 50"]
    print(f"Live High: {data['live_ohlc']['high']}")
    print(f"Prev Close: {data['prev_ohlc']['close']}")
```

### Option Chain
```python
from lib.api.option_chain import get_option_chain_dataframe, get_greeks

# Get full chain (DataFrame)
chain_df = get_option_chain_dataframe(token, "NSE_INDEX|Nifty 50", expiry)

# Get raw chain (Dict - matches API response)
# See: https://upstox.com/developer/api-documentation/get-pc-option-chain
# See: https://upstox.com/developer/api-documentation/get-pc-option-chain
from lib.api.option_chain import get_option_chain
raw_data = get_option_chain(token, "NSE_INDEX|Nifty 50", expiry)

# Calculate Total PCR (Put-Call Ratio)
from lib.api.option_chain import calculate_pcr
pcr = calculate_pcr(chain_df)
print(f"Total PCR: {pcr}")
```

### Market Holidays
Fetch the list of trading holidays for the current year.

```python
from lib.api.market_data import get_market_holidays

holidays = get_market_holidays(token)

if holidays:
    for h in holidays:
        # Note: Attributes might be underscored in some SDK versions
        d = getattr(h, 'date', getattr(h, '_date', None))
        desc = getattr(h, 'description', getattr(h, '_description', 'Unknown'))
        print(f"Holiday: {d} - {desc}")
```

### Option Contracts (V2)
Fetch all available option contracts for an instrument (e.g., Nifty 50) to filter by strike, type, or expiry.

```python
from lib.api.market_data import get_option_contracts

# Get all contracts (returns list of dicts)
contracts = get_option_contracts(token, "NSE_INDEX|Nifty 50")

# Filter by expiry
contracts_expiry = get_option_contracts(token, "NSE_INDEX|Nifty 50", expiry_date="2026-02-19")

if contracts:
    c = contracts[0]
    print(f"Symbol: {c.get('trading_symbol')}")
    print(f"Expiry: {c.get('expiry')}")
    print(f"Strike: {c.get('strike_price')}")
```

### Place Order (V3)
> [!WARNING] **Broker Rule Violation**
> The `place_order` function exists in `lib.api.order_management` and supports V3 features like slicing.
> **HOWEVER**, per agent rules, **Live Execution MUST use Kotak Neo API**.
> This function should ONLY be used for paper trading or specific approved testing on Upstox.

```python
from lib.api.order_management import place_order

# Example (DO NOT USE FOR LIVE STRATEGIES)
order_id = place_order(
    token,
    instrument_token="NSE_EQ|INE002A01018",
    quantity=10,
    transaction_type="BUY",
    order_type="MARKET",
    product="D",
    slice=True # V3 Feature
)
```

### Option Instrument Keys (CRITICAL for LTP)
To fetch LTP for options, you must resolve the **Upstox Instrument Key** (different from Kotak Trading Symbol).

1.  **Download Master Data** (Once in `setup`):
    ```python
    from lib.api.market_data import download_nse_market_data
    self.nse_data = download_nse_market_data()
    ```

2.  **Resolve Key**:
    ```python
    from lib.utils.instrument_utils import get_option_instrument_key
    
    upstox_key = get_option_instrument_key(
        underlying_symbol="NIFTY", 
        strike_price=26000, 
        option_type="CE", 
        nse_data=self.nse_data, 
        expiry_date=expiry
    )
    ```

3.  **Fetch LTP**:
    ```python
    from lib.api.market_data import get_ltp
    ltp = get_ltp(access_token, upstox_key)
    ```

### Technical Indicators
> [!IMPORTANT]
> **TA-Lib RULE**: Always use TA-Lib for standard indicators (RSI, EMA, SMA, ATR, ADX) to ensure chart-matching accuracy (Wilder's Smoothing).
> **EXCEPTION**: `calculate_supertrend` and `calculate_vwap` use optimized custom logic/formulas.

```python
from lib.utils.indicators import calculate_ema, calculate_rsi, calculate_vwap, calculate_supertrend

# Always use library functions which call TA-Lib directly
ema_20 = calculate_ema(df, 20)
rsi = calculate_rsi(df, 14)
vwap = calculate_vwap(df_1min)  # From candle data
trend, st_value = calculate_supertrend(df, period=10, multiplier=3)
```

### Handling Flat vs Pivoted Option Chains
Upstox API data can be "flattened" (CE and PE in separate rows). Always verify structure before accessing columns like `CE_OI`.

```python
# If data is flat (rows have 'type' column), pivot it:
if 'type' in df.columns and 'CE_OI' not in df.columns:
    pivoted = df.pivot(index='strike_price', columns='type', values=['oi', 'ltp'])
    pivoted.columns = [f'{col[1]}_{col[0]}'.upper() for col in pivoted.columns]
    df = pivoted.reset_index()
    # Now columns are strike_price, CE_OI, PE_OI, CE_LTP, PE_LTP
```

---

## 🤖 3. Order Placement (EXECUTION via KOTAK)

**CRITICAL**: All order execution MUST be done using the **Kotak Neo API** library located in the `kotak_api` folder. Use the `OrderManager` class for all trade operations.

```python
from kotak_api.lib.broker import BrokerClient
from kotak_api.lib.order_manager import OrderManager

# 1. Initialize Kotak Broker Client
kotak_broker = BrokerClient()
kotak_client = kotak_broker.authenticate()

# 2. Initialize Order Manager
order_mgr = OrderManager(kotak_client, dry_run=DRY_RUN)

# 3. Place Order (Example)
# Note: Kotak uses 'B' for Buy and 'S' for Sell
success = order_mgr.place_order(
    symbol="NIFTY2601624200CE", 
    qty=50, 
    transaction_type="S", 
    tag="Straddle"
)
```

> [!IMPORTANT]
> **Broker Roles**:
> - **Upstox**: Fetch LTP, Candles, Option Chain, Greeks, and WebSocket updates.
> - **Kotak**: Place, Modify, and Cancel orders. Do NOT use Upstox `place_order` for live execution.

### Kotak API Execution Guide (For AI Agents)

#### 1. Initialization
The Kotak components should be initialized once in the strategy's `setup` or `initialize` method. The library is located in the `kotak_api` folder.

```python
from kotak_api.lib.broker import BrokerClient
from kotak_api.lib.order_manager import OrderManager

class MyStrategy:
    def __init__(self, upstox_token, config):
        # Data Ingestion (Upstox)
        self.upstox_token = upstox_token
        
        # Execution (Kotak)
        self.kotak_broker = BrokerClient()
        self.kotak_client = None
        self.order_mgr = None
        self.dry_run = config.get('dry_run', True)

    def initialize(self):
        # Authenticate Kotak
        self.kotak_client = self.kotak_broker.authenticate()
        # Initialize Order Manager
        self.order_mgr = OrderManager(self.kotak_client, dry_run=self.dry_run)
        
    def check_margin(self):
        """Fetch available margin/funds."""
        funds = self.kotak_broker.get_funds()
        if funds:
            # Example: Accessing cash balance
             cash = funds.get('data', {}).get('cash', 0)
             return float(cash)
        return 0.0
```

#### 2. Transaction Types
Kotak API uses single-letter transaction types:
- `"B"`: Buy
- `"S"`: Sell

#### 3. Symbol Mapping & Lookups
Upstox uses `instrument_key` (e.g., `NSE_FO|58689`). Kotak requires the **Trading Symbol** (e.g., `NIFTY22JAN25C24000`).

- **Strike to Symbol**: Use `kotak_api.lib.trading_utils.get_strike_token(broker, strike, type, expiry)` to resolve the correct symbol name.
- **Latency Tip**: After `place_order()`, always wait ~1 second before calling `check_order_status()` to allow the exchange to process the request.

#### 4. Order Verification (Get Execution Price)
After an order is filled, **ALWAYS** fetch the actual traded price from the exchange. Do NOT rely on the limit price or current LTP.

```python
# After order status is 'complete' or 'filled'
real_price = order_mgr.get_execution_price(order_id)
logger.info(f"Actual Execution Price: {real_price}")
```

#### 5. Master Data Management
The Kotak API requires local CSV master files for symbol resolution. If `get_strike_token` fails, ensure master data is fresh.

```python
# To force a fresh download (usually done in setup or maintenance)
broker.download_fresh_master()
broker.load_master_data()
```

#### 6. Instrument Mapping Utility
Use `get_instrument_token` to resolve Kotak's internal `instrument_token` for quotes.

```python
token = broker.get_instrument_token("NIFTY22JAN25C24000", exchange="nse_fo")
```

---

## 🤖 4. WebSocket Streaming

**Use appropriate mode based on data needs:**

```python
from lib.api.streaming import UpstoxStreamer

streamer = UpstoxStreamer(access_token)

# For price tracking only - use 'ltpc'
streamer.connect_market_data(
    instrument_keys=[key],
    mode="ltpc"  # Lightweight
)

# For complete data (VWAP, OI, depth) - use 'full'
streamer.connect_market_data(
    instrument_keys=[key],
    mode="full"  # Includes VWAP, OHLC, volume, OI
)

# For options Greeks - use 'option_greeks'
streamer.connect_market_data(
    instrument_keys=[option_key],
    mode="option_greeks"  # Delta, Gamma, Theta, Vega, IV
)
```

---

## 🤖 5. Live Indicator Calculation Pattern
Relying solely on the historical API for live signals is unsafe due to API finalization delays. You MUST use the **Merged Data Pattern** for accurate indicators:

1. **Warmup**: Fetch 2-5 days of historical data via `get_historical_data` at initialization.
2. **Freshness**: In your main loop, fetch today's 1-minute candles via `get_intraday_data_v3`.
##### 3. Combination
Concatenate history with intraday, ensuring no duplicates.

### 🔍 Function Verification Rule
**BEFORE WRITING CODE:**
1. Check `quick_help/FUNCTION_REFERENCE.md`.
2. `grep` the codebase to confirm function signature.
3. **NEVER** invent functions (like `get_ltp` or `get_history`) without checking.

---

## 🤖 6. Real-Time Data (WebSockets)

For strategies requiring second-by-second updates or 1-minute candle formations without polling:

### initialization
```python
from lib.api.streaming import UpstoxStreamer

# Initialize
streamer = UpstoxStreamer(access_token)
```

### 1-Minute Candle Data & LTP
The `UpstoxStreamer` automatically parses the complex proto-buffer messages into a clean dictionary. It specifically extracts finalized 1-minute candles (`ohlc_1m`).

```python
def on_market_update(data):
    # data is a dictionary for a single instrument
    symbol = data.get('instrument_key')
    ltp = data.get('ltp')
    
    # Check for 1-Minute Candle (Finalized)
    if 'ohlc_1m' in data:
        candle = data['ohlc_1m']
        print(f"New Candle for {symbol}: {candle['close']} at {candle['timestamp']}")
        # Trigger Strategy Logic Here
        # strategy.on_candle_close(candle)

# Connect
streamer.connect_market_data(
    instrument_keys=["NSE_INDEX|Nifty 50", "NSE_FO|58689"],
    mode="full", # 'full' required for OHLC
    on_message=on_market_update
)
```

### Portfolio Streaming (Orders & Positions)
The `UpstoxStreamer` can also monitor real-time order fills and position changes.

```python
def on_order_update(order_data):
    print(f"Order Update: {order_data['order_id']} is {order_data['status']}")

streamer.connect_portfolio(
    order_update=True,
    position_update=True,
    on_order=on_order_update
)
```

### Accessing Latest Data (Cache)
You can also poll the streamer's local cache if you don't want event-driven logic:
```python
latest_feed = streamer.get_latest_data("NSE_INDEX|Nifty 50")
if latest_feed:
    print(latest_feed.get('ltp'))
```

---

## 🤖 7. Utility Scripts

### IV Recorder (Historical IV)
Since the API does not provide historical IV, use the `iv_recorder` script to build your own dataset.

**Script**: `scripts/iv_recorder/record_iv.py`

**Usage**:
```bash
python scripts/iv_recorder/record_iv.py
```

**Features**:
- Polls Option Chain every 60 seconds.
- Records IV, LTP, **and OI** for ATM +/- 250 strikes.
- Appends to `data/iv_history/iv_history_{date}.csv`.

> [!NOTE]
> **Why use this for OI?**
> The standard `get_intraday_data_v3` and `get_historical_data_v3` APIs return `None` or `0` for Open Interest on option contracts (verified Feb 2026). This recorder is the **reliable** way to build historical OI and IV datasets for analytics.

# Upstox API - Complete Function Reference

This document lists all important Upstox API functions available in your library.

## 📊 Market Data Functions

### NSE Instruments
- `download_nse_market_data()` - Download complete NSE instrument master data
- `get_future_instrument_key(symbol, nse_data)` - Get futures instrument key
- `get_option_instrument_key(symbol, strike, option_type, nse_data)` - Get option instrument key

### Quotes & VWAP
- `get_vwap(token, instrument_key)` - **STANDARD** Get daily VWAP (Average Traded Price)
- `get_market_quote_for_instrument(token, instrument_key)` - Get full quote with key mapping
- `get_market_quotes(token, instrument_keys)` - Get quotes for multiple instruments
- `get_ltp(token, instrument_key)` - **NEW** Get Last Traded Price (Simple Wrapper)
- `get_multiple_ltp_quotes(token, instrument_keys)` - Get LTP for multiple instruments
- `get_ohlc_quote(token, instrument_key, interval)` - Get OHLC data

## 📈 Historical & Intraday Data

### Intraday (V3 API)
- `get_intraday_data_v3(token, key, unit, interval)` - Get intraday candles
  - **1-minute**: `get_intraday_data_v3(token, key, "minute", 1)`
  - **5-minute**: `get_intraday_data_v3(token, key, "minute", 5)`
  - **15-minute**: `get_intraday_data_v3(token, key, "minute", 15)`
  - **30-minute**: `get_intraday_data_v3(token, key, "minute", 30)`

### Historical (V2 API)
- `get_historical_data(token, key, interval, days)` - Get historical candles
  - **Daily**: Use `fetch_historical_data()` from `lib.api.market_data`

## 🎯 Option Chain & Greeks

### Option Chain
- `get_expiries(token, instrument_key)` - Get all available expiries
- `get_nearest_expiry(token, instrument_key)` - Get nearest expiry
- `get_option_chain_dataframe(token, instrument_key, expiry)` - Get full option chain as DataFrame

### Greeks
- `get_greeks(df, strike, option_type)` - Get greeks from option chain DataFrame
- `get_option_greek(token, instrument_key)` - Get greeks via direct API call
- `get_multiple_option_greeks(token, instrument_keys)` - Get greeks for multiple options
- `get_atm_iv(df)` - Get ATM Implied Volatility
- `get_atm_strike_from_chain(df)` - Find ATM strike from chain

### Option Chain Helpers
- `get_ce_data(df, strike)` - Get complete CE data including greeks
- `get_pe_data(df, strike)` - Get complete PE data including greeks
- `get_market_data(df, strike, option_type)` - Get market data for specific strike
- `get_oi_data(df, strike)` - Get OI data for both CE and PE
- `get_premium_data(df, strike)` - Get premium data for both CE and PE

## 📅 Market Holidays & Timings

- `get_market_holidays()` - Get list of market holidays
- `get_market_status()` - Check if market is OPEN/CLOSED
  - Market Hours: 9:15 AM - 3:30 PM
  - Pre-market: 9:00 AM - 9:15 AM
  - Post-market: 3:40 PM - 4:00 PM

## 💼 Order Management

### Place Orders
- `place_order(token, instrument_token, quantity, transaction_type, order_type, product, validity)` - Place a new order
  - **transaction_type**: "BUY" or "SELL"
  - **order_type**: "MARKET", "LIMIT", "SL", "SL-M"
  - **product**: "INTRADAY", "DELIVERY", "NRML", "MIS"
  - **validity**: "DAY", "IOC"

### Modify & Cancel
- `modify_order(token, order_id, quantity, order_type, price)` - Modify existing order
- `cancel_order(token, order_id)` - Cancel an order

### Order Book & Trades
- `get_order_book(token)` - Get all orders (pending, executed, cancelled)
- `get_order_details(token, order_id)` - Get specific order details
- `get_trade_history(token)` - Get all executed trades

## 📂 Portfolio & Positions

- `get_positions(token)` - Get current open positions
- `get_holdings(token)` - Get long-term holdings
- `get_funds(token)` - Get available margin and fund information

## 👤 User Profile & Account

### User Information (lib.api.user)
- `get_user_profile(token)` - Get user details (name, email, brokerage type)
- `get_funds_summary(token)` - Get equity and commodity margin/fund details
- `logout(token)` - Logout and invalidate access token

**Example:**
```python
from lib.api.user import get_user_profile, get_funds_summary

profile = get_user_profile(access_token)
print(f"User: {profile['user_name']}")

funds = get_funds_summary(access_token)
print(f"Available Margin: ₹{funds['equity']['available_margin']:,.2f}")
```

## 🎯 GTT Orders (Good Till Triggered)

### GTT Order Management (lib.api.gtt)
- `place_gtt_order(token, instrument_token, quantity, transaction_type, product, type, price, trigger_price)` - Create GTT order
- `cancel_gtt_order(token, gtt_order_id)` - Cancel GTT order
- `get_gtt_order_details(token, gtt_order_id)` - Get GTT order details
- `modify_gtt_order(token, gtt_order_id, quantity, price, trigger_price)` - Modify GTT order

**GTT Types:**
- **SINGLE**: Single trigger order
- **OCO**: One-Cancels-Other (bracket order)

**Example:**
```python
from lib.api.gtt import place_gtt_order

# Place GTT order to buy when price reaches trigger
gtt = place_gtt_order(
    access_token=token,
    instrument_token="NSE_FO|58689",
    quantity=130,
    transaction_type="BUY",
    product="D",
    type="SINGLE",
    price=100.0,
    trigger_price=95.0
)
```

## 💰 Margin Calculator

### Margin Calculation (lib.utils.margin_calculator)

**Get Margin Requirements:**
- `get_margin_details(token, instruments)` - Get margin for multiple instruments
- `get_single_instrument_margin(token, instrument_key, quantity, transaction_type, product)` - Get margin for single instrument
- `get_option_delivery_margin(token, instrument_key, quantity, transaction_type)` - Option delivery margin
- `get_mcx_delivery_margin(...)` - MCX delivery margin
- `get_mcx_futures_margin(...)` - MCX futures margin
- `get_mcx_options_margin(...)` - MCX options margin

**Margin Analysis:**
- `format_margin_details(margin_data)` - Format and display margin breakdown
- `check_margin_availability(token, instruments, available_funds)` - Check if sufficient margin available
- `analyze_margin_response(margin_data)` - Analyze margin characteristics

**Example:**
```python
from lib.utils.margin_calculator import get_single_instrument_margin, check_margin_availability

# Get margin for single instrument
margin = get_single_instrument_margin(
    access_token=token,
    instrument_key="NSE_FO|58689",
    quantity=130,
    transaction_type="BUY",
    product="D"
)

print(f"Required Margin: ₹{margin['data']['required_margin']:,.2f}")

# Check if you have enough margin
instruments = [
    {
        "instrument_key": "NSE_FO|58689",
        "quantity": 130,
        "transaction_type": "BUY",
        "product": "D"
    }
]

result = check_margin_availability(token, instruments, available_funds=50000)
if result['margin_available']:
    print("✅ Sufficient margin!")
else:
    print(f"❌ Shortfall: ₹{result['shortfall']:,.2f}")
```

## 🔄 WebSocket Streaming

### WebSocket Modes

Upstox WebSocket supports **3 data modes** with different levels of detail:

1. **`ltpc`** - Last Traded Price + Change (Lightweight)
2. **`full`** - Complete market data (Recommended)
3. **`option_greeks`** - Greeks data for options

### Market Data Stream

**Initialize Streamer:**
```python
from lib.api.streaming import UpstoxStreamer

streamer = UpstoxStreamer(access_token)
```

#### Mode 1: LTPC (Last Traded Price + Change)

**Lightest mode - Only price and change data**

```python
def on_ltpc_update(data):
    print(f"Symbol: {data.get('instrument_key')}")
    print(f"LTP: ₹{data.get('last_price', 0):.2f}")
    print(f"Change: {data.get('net_change', 0):.2f}")
    print(f"% Change: {data.get('percent_change', 0):.2f}%")

# Connect with LTPC mode
streamer.connect_market_data(
    instrument_keys=["NSE_FO|49229", "NSE_EQ|INE002A01018"],
    mode="ltpc",
    on_message=on_ltpc_update
)
```

**LTPC Data Fields:**
- `last_price` - Last traded price
- `last_traded_quantity` - Last traded quantity
- `last_traded_time` - Timestamp
- `net_change` - Absolute change
- `percent_change` - Percentage change
- `close_price` - Previous close

#### Mode 2: FULL (Complete Market Data)

**Complete market data - OHLC, Volume, OI, VWAP, Bids/Asks**

```python
def on_full_update(data):
    # Price Data
    print(f"LTP: ₹{data.get('last_price', 0):.2f}")
    
    # OHLC
    ohlc = data.get('ohlc', {})
    print(f"Open: {ohlc.get('open')}, High: {ohlc.get('high')}")
    print(f"Low: {ohlc.get('low')}, Close: {ohlc.get('close')}")
    
    # Volume & OI
    print(f"Volume: {data.get('volume', 0):,}")
    print(f"OI: {data.get('oi', 0):,}")
    
    # VWAP (Average Traded Price)
    print(f"VWAP: ₹{data.get('average_price', 0):.2f}")
    
    # Bid/Ask
    print(f"Bid: ₹{data.get('bid_price', 0):.2f} ({data.get('bid_qty', 0)})")
    print(f"Ask: ₹{data.get('ask_price', 0):.2f} ({data.get('ask_qty', 0)})")

# Connect with FULL mode
streamer.connect_market_data(
    instrument_keys=["NSE_FO|49229"],
    mode="full",
    on_message=on_full_update
)
```

**FULL Mode Data Fields:**
- **Price**: `last_price`, `close_price`, `average_price` (VWAP)
- **OHLC**: `ohlc.open`, `ohlc.high`, `ohlc.low`, `ohlc.close`
- **Volume**: `volume`, `total_buy_quantity`, `total_sell_quantity`
- **OI**: `oi` (Open Interest), `oi_day_high`, `oi_day_low`
- **Bid/Ask**: `bid_price`, `bid_qty`, `ask_price`, `ask_qty`
- **Depth**: `depth.buy[]`, `depth.sell[]` (5 levels each)
- **Change**: `net_change`, `percent_change`
- **Timestamps**: `last_traded_time`, `exchange_timestamp`

#### Mode 3: OPTION_GREEKS

**Greeks data for options (Delta, Gamma, Theta, Vega, IV)**

```python
def on_greeks_update(data):
    print(f"Delta: {data.get('delta', 0):.4f}")
    print(f"Gamma: {data.get('gamma', 0):.4f}")
    print(f"Theta: {data.get('theta', 0):.4f}")
    print(f"Vega: {data.get('vega', 0):.4f}")
    print(f"IV: {data.get('iv', 0):.4f}")

# Connect with option_greeks mode
streamer.connect_market_data(
    instrument_keys=["NSE_FO|58689"],  # Option instrument
    mode="option_greeks",
    on_message=on_greeks_update
)
```

### Dynamic Subscription Management

**Subscribe to more instruments after connection:**
```python
# Initial connection
streamer.connect_market_data(
    instrument_keys=["NSE_FO|49229"],
    mode="full"
)

# Add more instruments dynamically
streamer.subscribe_market_data(
    instrument_keys=["NSE_EQ|INE002A01018", "NSE_EQ|INE040A01034"],
    mode="ltpc"
)

# Unsubscribe from instruments
streamer.unsubscribe_market_data(["NSE_EQ|INE002A01018"])
```

### Portfolio Stream

**Real-time order and position updates:**

```python
def on_order_update(order_info):
    print(f"Order {order_info['order_id']}: {order_info['status']}")
    print(f"Symbol: {order_info['trading_symbol']}")
    print(f"Filled: {order_info['filled_quantity']}/{order_info['quantity']}")
    print(f"Price: ₹{order_info['price']:.2f}")

def on_position_update(position_info):
    print(f"Position: {position_info['trading_symbol']}")
    print(f"Quantity: {position_info['quantity']}")
    print(f"P&L: ₹{position_info['pnl']:.2f}")

# Connect to portfolio stream
streamer.connect_portfolio(
    order_update=True,
    position_update=True,
    on_order=on_order_update,
    on_position=on_position_update
)
```

### Complete WebSocket Example

```python
from lib.api.streaming import UpstoxStreamer

class MyStrategy:
    def __init__(self, access_token):
        self.streamer = UpstoxStreamer(access_token)
        self.prices = {}
    
    def on_tick(self, data):
        symbol = data.get('instrument_key')
        ltp = data.get('last_price', 0)
        self.prices[symbol] = ltp
        
        # Your strategy logic here
        if ltp > some_threshold:
            self.place_order()
    
    def start(self):
        # Connect to market data
        self.streamer.connect_market_data(
            instrument_keys=["NSE_FO|49229"],
            mode="full",
            on_message=self.on_tick
        )
        
        # Keep running
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()
    
    def stop(self):
        self.streamer.disconnect_all()

# Usage
strategy = MyStrategy(access_token)
strategy.start()
```

### WebSocket Best Practices

1. **Choose the Right Mode:**
   - Use `ltpc` for simple price tracking (lowest bandwidth)
   - Use `full` for complete market data (VWAP, OI, depth)
   - Use `option_greeks` only for options with Greeks

2. **Handle Reconnections:**
   - WebSocket automatically reconnects on disconnection
   - Resubscribe to instruments after reconnection

3. **Data Rate:**
   - `ltpc`: ~1-2 updates/second
   - `full`: ~5-10 updates/second
   - Limit to 100 instruments per connection

4. **Error Handling:**
   - Always implement error callbacks
   - Log connection status changes
   - Handle malformed data gracefully

## 🔧 Utility Functions

### Instrument Utils
- `get_future_instrument_key(symbol, nse_data)` - Get futures key
- `get_option_instrument_key(symbol, strike, option_type, nse_data)` - Get option key

### Expiry Cache
- `get_expiry_for_strategy(token, expiry_type, instrument)` - Get expiry with caching
  - **expiry_type**: "current_week", "next_week", "monthly"

### Date Utils
- `calculate_days_to_expiry(expiry_date)` - Calculate days to expiry

### Indicators
- `calculate_ema_series(df, period)` - Calculate EMA series
- `calculate_vwap(df)` - Calculate VWAP from candle data

## 📝 Quick Examples

### Get 1-Minute Candles
```python
candles = get_intraday_data_v3(access_token, instrument_key, "minute", 1)
df = pd.DataFrame(candles)
```

### Get 5-Minute Candles
```python
candles = get_intraday_data_v3(access_token, instrument_key, "minute", 5)
df = pd.DataFrame(candles)
```

### Get Daily Data
```python
from lib.api.market_data import fetch_historical_data
from datetime import datetime, timedelta

end_date = datetime.now()
start_date = end_date - timedelta(days=30)

df = fetch_historical_data(
    access_token,
    instrument_key,
    "days",
    1,
    start_date.strftime("%Y-%m-%d"),
    end_date.strftime("%Y-%m-%d")
)
```

### Place Market Order
```python
order = place_order(
    access_token=access_token,
    instrument_token=instrument_key,
    quantity=25,
    transaction_type="BUY",
    order_type="MARKET",
    product="INTRADAY",
    validity="DAY"
)
```

### Modify Order
```python
modify_order(
    access_token=access_token,
    order_id="240123000123456",
    quantity=50,
    order_type="LIMIT",
    price=100.0
)
```

## 🛠️ Utility Functions

### Order Helpers (lib.utils.order_helper)

**Simplified Order Placement with Auto Lot Size:**
- `place_option_order(token, instrument_key, nse_data, num_lots, transaction_type, product_type, order_type, validity, price, trigger_price)` - Place option order with automatic lot size calculation
- `place_futures_order(...)` - Same as above for futures
- `get_order_quantity(instrument_key, nse_data, num_lots)` - Calculate total quantity from lots

**Example:**
```python
from lib.utils.order_helper import place_option_order

# Place 2 lots of Nifty CE (automatically calculates quantity = 2 × 65 = 130)
order = place_option_order(
    access_token=token,
    instrument_key="NSE_FO|58689",
    nse_data=nse_df,
    num_lots=2,
    transaction_type="SELL",
    product_type="INTRADAY"
)
```

### Technical Indicators (lib.utils.indicators)

**All indicators use TA-Lib with pandas fallback:**

- `calculate_ema(df, period, price_column='close')` - Get latest EMA value
- `calculate_ema_series(df, period, price_column='close')` - Get full EMA series
- `calculate_sma(df, period, price_column='close')` - Simple Moving Average
- `calculate_rsi(df, period=14, price_column='close')` - Relative Strength Index
- `calculate_atr(df, period=14)` - Average True Range
- `calculate_adx(df, period=14)` - Average Directional Index
- `calculate_vwap(df)` - Intraday VWAP from candle data
- `calculate_supertrend(df, period=7, multiplier=3.0)` - SuperTrend indicator

**Example:**
```python
from lib.utils.indicators import calculate_ema, calculate_rsi, calculate_vwap

# Get 20-period EMA
ema_20 = calculate_ema(df, 20)

# Get RSI
rsi = calculate_rsi(df, 14)

# Calculate VWAP from intraday candles
vwap = calculate_vwap(df_1min)
```

### Instrument Utilities (lib.utils.instrument_utils)

- `get_lot_size(instrument_key, nse_data)` - Get lot size for an instrument
- `get_future_instrument_key(symbol, nse_data)` - Get futures key
- `get_option_instrument_key(symbol, strike, option_type, nse_data)` - Get option key

### Expiry Management (lib.utils.expiry_cache)

- `get_expiry_for_strategy(token, expiry_type, instrument, force_refresh=False)` - Get expiry with caching
  - **expiry_type**: "current_week", "next_week", "monthly"
  - Caches results to avoid repeated API calls

**Example:**
```python
from lib.utils.expiry_cache import get_expiry_for_strategy

# Get current week expiry (cached)
expiry = get_expiry_for_strategy(token, "current_week", "NIFTY")
```

### Date Utilities (lib.utils.date_utils)

- `calculate_days_to_expiry(expiry_date)` - Calculate days remaining to expiry
- `is_market_open()` - Check if market is currently open
- `get_market_hours()` - Get market timing information

### Brokerage & Costs (lib.utils.brokerage_calculator)

- `get_brokerage_details(token, instrument_token, quantity, product, transaction_type, price)` - Get detailed brokerage breakdown

**Example:**
```python
from lib.utils.brokerage_calculator import get_brokerage_details

brokerage = get_brokerage_details(
    access_token=token,
    instrument_token="NSE_FO|58689",
    quantity=130,
    product="D",
    transaction_type="BUY",
    price=100.0
)
```

### Profit & Loss Tracking (lib.utils.profit_loss)

- `get_profit_loss_report(token, from_date, to_date, segment, financial_year, page_number, page_size)` - Get P&L report
- `get_recent_profit_loss(token, days=30, segment="FO", financial_year=None)` - Get recent P&L
- `format_profit_loss_report(pl_data)` - Format P&L data for display
- `analyze_profit_loss_trends(formatted_data)` - Analyze P&L trends
- `get_current_financial_year()` - Get current FY in Upstox format

**Example:**
```python
from lib.utils.profit_loss import get_recent_profit_loss, format_profit_loss_report

# Get last 30 days P&L
pl_data = get_recent_profit_loss(token, days=30, segment="FO")
formatted = format_profit_loss_report(pl_data)

print(f"Total P&L: ₹{formatted['summary']['total_profit_loss']:,.2f}")
```

### Market Validation (lib.utils.market_validation)

- `is_trading_hours()` - Check if within trading hours
- `is_market_holiday(date)` - Check if date is a holiday
- `validate_order_params(...)` - Validate order parameters before placement

## 📚 Additional Resources

- **Jupyter Notebook**: `quick_help/upstox_api_reference.ipynb` - Interactive examples
- **Function Reference**: `quick_help/FUNCTION_REFERENCE.md` - This document
- **Official Docs**: https://github.com/upstox/upstox-python
- **API Docs**: https://upstox.com/developer/api-documentation/

## ⚠️ Important Notes

1. **VWAP**: Always use `get_vwap()` for daily VWAP - it handles Upstox key mapping issues
2. **Historical Data**: V3 API uses "minute" unit, V2 API uses "day"/"week"/"month"
3. **Order Safety**: Always test with small quantities or dry_run mode first
4. **WebSocket**: Requires continuous connection - use in strategy files, not notebooks
5. **Rate Limits**: Be mindful of API rate limits when making bulk requests

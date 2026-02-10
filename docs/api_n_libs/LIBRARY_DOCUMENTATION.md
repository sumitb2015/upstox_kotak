# Upstox Strategy Library Documentation

This library provides a comprehensive set of helper functions wrapping the Upstox Python SDK. These functions are designed to be "plug and play" for building new trading strategies.

## User & Funds (`api/user.py`)
- `get_user_profile(access_token)`: Returns user details.
- `get_funds_summary(access_token)`: Returns equity and commodity margins.
- `logout(access_token)`: Logout and invalidate the access token.

## Portfolio (`api/portfolio.py`)
- `get_holdings(access_token)`: Returns current holdings as a Pandas DataFrame.
- `get_positions(access_token)`: Returns net and day-wise positions as a DataFrame.
- `convert_position(access_token, instrument_key, new_product, old_product, transaction_type, quantity)`: Converts positions (e.g., Intraday to Delivery).

## Order Management (`api/order_management.py`)
- `place_order(...)`: Place individual orders.
- `place_multi_order(access_token, orders)`: Place batch orders (V3).
- `modify_order(access_token, order_id, ...)`: Modify open orders.
- `cancel_order(access_token, order_id)`: Cancel orders.
- `get_order_details(access_token, order_id)`: Get full audit trail of an order.
- `exit_positions(access_token, instrument_key=None, product=None)`: Square off positions.

## GTT Orders (`api/gtt.py`)
- `place_gtt_order(...)`: Place GTT (Good Till Triggered) orders.
- `modify_gtt_order(access_token, gtt_order_id, quantity, price, trigger_price)`: Modify GTT orders.
- `cancel_gtt_order(access_token, gtt_order_id)`: Cancel GTT orders.
- `get_gtt_order_details(access_token, gtt_order_id)`: Get GTT details.

## Market Data (`api/market_data.py` & `api/market_quotes.py`)
- `get_full_market_quote(access_token, symbol)`: Full L2 depth and quotes.
- `get_ltp_quote(access_token, symbol)`: Lightweight LTP fetch.
- `get_option_expiry_dates(access_token, underlying_key)`: List available expiries.
- `get_market_status()`: check if market is OPEN or CLOSED.
- `fetch_historical_data(...)`: Fetch candle data for backtesting.
- `get_expired_option_contracts(access_token, instrument_key, expiry_date)`: Get expired option contracts.
- `get_expired_future_contracts(access_token, instrument_key)`: Get expired future contracts.
- `get_expired_historical_candle_data(access_token, instrument_key, interval, to_date, from_date)`: Get historical candle data for expired contracts.

## Real-time Streaming (`api/streaming.py`)
- `UpstoxStreamer(access_token)`:
  - `connect_market_data(instrument_keys, mode="ltpc", on_message=None)`: Connect to live market data (Uses V3 Protobuf).
  - `subscribe_market_data(instrument_keys, mode="ltpc")`: Add new instruments to the stream.
  - `unsubscribe_market_data(instrument_keys)`: Stop streaming for specific instruments.
  - `change_market_mode(instrument_keys, mode)`: Switch mode (e.g., from `ltpc` to `full` or `option_greeks`).
  - `connect_portfolio(order_update=True, position_update=True, holding_update=False, gtt_update=False, on_order=None, on_position=None, on_holding=None)`: Stream live order, trade, position, and holding updates.
  - `add_market_callback(callback)`: Add multiple listeners for price updates.
  - `add_order_callback(callback)`: Add multiple listeners for order status changes.
  - `add_position_callback(callback)`: Add listeners for position updates.
  - `add_holding_callback(callback)`: Add listeners for holding updates.
  - `enable_debug(enable=True)`: Enable/Disable printing of raw WebSocket data to console.
  - `disconnect_all()`: Gracefully close all websocket connections.

### Portfolio Stream Features
The portfolio stream provides real-time updates for:
- **Order Updates**: Status changes (pending → complete), fills, rejections
- **Position Updates**: Real-time P&L, quantity changes
- **Holding Updates**: Long-term holdings changes
- **GTT Orders**: Good-Till-Triggered order status

Each update is parsed and provides structured data including:
- Order ID, status, filled quantity, average price
- Instrument key, trading symbol, exchange
- Timestamps and status messages

## Usage Example
```python
from core.authentication import check_existing_token, perform_authentication
from api.portfolio import get_positions
from api.order_management import place_order

# Authenticate
access_token = perform_authentication()

# Get Positions
df_pos = get_positions(access_token)
print(df_pos)

# Place an Order
if df_pos.empty:
    place_order(access_token, "NSE_EQ|INE002A01018", quantity=1)
```

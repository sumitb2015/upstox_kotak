"""
Upstox Library Facade
---------------------
Unified access point for all Upstox API helper functions and core classes.
Allows cleaner imports in strategies:
from lib.upstox import UpstoxAPI, get_instrument_key, EMA, MarketStatus, ...
"""

# 1. API Wrappers
from lib.utils.api_wrapper import UpstoxAPI

# 2. Market Data Helpers
from lib.api.market_data import download_nse_market_data, get_market_status

# 3. Instrument Utilities
from lib.utils.instrument_utils import (
    get_instrument_key,
    get_option_instrument_key, 
    get_future_instrument_key,
    get_equity_instrument_key,
    get_lot_size,
    get_nifty_option_instrument_keys
)

# 4. Indicators
from lib.utils.indicators import (
    calculate_ema,
    calculate_vwap,
    calculate_rsi,
    calculate_atr,
    calculate_adx,
    calculate_supertrend
)

# 5. Order Helpers
from lib.utils.order_helper import (
    place_option_order,
    place_futures_order,
    get_order_quantity
)

# 6. Expiry Helpers
from lib.utils.expiry_cache import (
    get_expiry_for_strategy,
    get_monthly_expiry
)

# 7. Date Utilities
from lib.utils.date_utils import (
    get_next_thursday,
    get_last_thursday
)

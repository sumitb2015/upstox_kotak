"""
Shared Trading Library for Kotak Neo API Strategies

This library provides reusable components for building trading strategies:
- DataStore: Thread-safe market data cache
- WebSocketClient: WebSocket management
- BrokerClient: Broker API wrapper with authentication
- OrderManager: Order placement and tracking
- PositionTracker: Position and MTM calculation

Usage:
    from lib.broker import BrokerClient
    from lib.data_store import DataStore
    
    broker = BrokerClient()
    broker.authenticate()
    data_store = DataStore()
"""

__version__ = "1.0.0"
__all__ = [
    # Core infrastructure
    "DataStore",
    "WebSocketClient",
    "BrokerClient",
    "OrderManager",
    "PositionTracker",
    # Trading utilities
    "get_instrument_token",
    "get_nearest_expiry", 
    "get_strike_token",
    "get_atm_strike",
    "get_otm_strike",
    "get_itm_strike",
    "calculate_position_value",
    "calculate_imbalance",
    "find_swing_high",
    "find_swing_low",
    "detect_swing_points",
    "parse_expiry_from_symbol",
    "get_all_option_tokens",
    # Indicators
    "calculate_ema",
    "calculate_sma",
    "calculate_rsi",
    # Time utilities
    "is_market_hours",
    "is_trading_time",
    "should_auto_exit",
    "time_until_market_close",
    "is_near_market_close",
    # Utils
    "get_lot_size",
    "round_to_strike_interval",
    "setup_strategy_logger",
    # Historical data
    "fetch_nifty_historical",
    "fetch_stock_historical",
    "warm_up_indicators",
    "convert_df_to_candles",
    "get_latest_closes",
    "get_previous_day_data"
]

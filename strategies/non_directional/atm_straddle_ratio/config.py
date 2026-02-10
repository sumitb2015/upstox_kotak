"""
ATM Short Straddle Strategy - Configuration

Strategy: Sell ATM straddle at 9:20 AM, adjust based on CE/PE ratio
"""

# Strategy Parameters
STRATEGY_NAME = "ATM Straddle Ratio"
DRY_RUN = False  # Set to False for live trading

# Entry Configuration
ENTRY_TIME = "09:20"  # Time to enter straddle (HH:MM)
MAX_ENTRY_RETRIES = 3 # Stop trying after this many failures
ENTRY_RETRY_BACKOFF = 5 # Seconds to wait before retrying (5 mins)
ATM_CHECK_INTERVAL = 60 # Seconds between ATM drift checks to trade
LOT_SIZE = 1  # Number of lots to trade

# Adjustment Configuration
RATIO_THRESHOLD = 0.6  # Trigger adjustment when min/max < 0.6

# Exit Configuration
PROFIT_TARGET = 5000  # Exit when P&L >= ₹5,000
STOP_LOSS = -3000  # Exit when P&L <= -₹3,000

# Market Hours
MARKET_START = "09:15"
MARKET_END = "15:18"  # Exit before 15:20
FORCE_EXIT_TIME = "15:18"  # Force exit at this time

# Instrument Configuration
UNDERLYING = "NIFTY"
EXPIRY_TYPE = "current_week"  # current_week, next_week, monthly

# WebSocket Configuration
WEBSOCKET_MODE = "ltpc"  # Lightweight mode for price tracking
PRICE_UPDATE_INTERVAL = 1  # Process updates every N seconds

# Logging
LOG_LEVEL = "INFO"
LOG_FILE = "atm_straddle_ratio.log"

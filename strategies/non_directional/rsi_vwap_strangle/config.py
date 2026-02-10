# Strategy Configuration
DRY_RUN = False # Set to False for Live Trading

# --- Instrument Settings ---
INDEX_NAME = "NSE_INDEX|Nifty 50"
START_TIME = "09:20:00"  # Strategy Start Time
EXIT_TIME = "15:18:00"   # Strategy Exit Time

# --- Strike Selection ---
TARGET_PREMIUM = 50.0  # Target premium for both CE and PE

# --- Entry Conditions ---
RSI_PERIOD = 14
RSI_MIN = 35.0
RSI_MAX = 60.0
RSI_TIMEFRAME = "3minute"  # For Overbought/Oversold check

# --- Risk Management ---
SL_PCT = 0.20          # 20% Stop Loss per leg
TRAILING_SL_PCT = 0.20 # 20% Trailing SL
SL_HARDENING_PROFIT_PCT = 0.15 # Move SL to Cost once 15% profit is reached

# --- Pyramiding (Trending) ---
PYRAMID_ENABLED = True
PYRAMID_PROFIT_STEP_PCT = 0.10  # Add positions every 10% profit increase
PYRAMID_TSL_PCT = 0.10          # Tighten TSL to 10% once pyramiding is active
MAX_PYRAMID_LOTS = 3            # Maximum additional lots to add
MAX_TOTAL_LOTS = 10             # Safety cap

# --- Targets ---
TARGET_PROFIT_PCT = 0.50  # Exit leg/strategy if profit > 50% of collected premium

# --- Re-entry ---
REENTRY_ENABLED = True    # Re-enter if price returns to original open price
REENTRY_RECOVERY_PCT = 0.1  # Require 10% price recovery from exit before re-entry

# --- State Persistence ---
STATE_RESTORATION_ENABLED = False # Set to True to recover position after restart

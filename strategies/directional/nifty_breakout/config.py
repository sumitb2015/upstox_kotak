"""
Configuration for Nifty Breakout Strategy.
Trades breaks of Yesterday's High/Low confirmed by Supertrend.
"""

from datetime import datetime

# --- Strategy Constants ---
STRATEGY_NAME = "Nifty_Breakout_ST"
SYMBOL = "NSE_INDEX|Nifty 50"  # Underlying
INSTRUMENT_NAME = "NIFTY"       # Short name for option lookup

# --- Time Controls ---
START_TIME = "09:15:00"
EXIT_TIME = "15:18:00"
NO_NEW_ENTRY_AFTER = "15:00:00"

# --- Strategy Parameters ---
SUPERTREND_PERIOD = 10
SUPERTREND_MULTIPLIER = 3
STRIKE_OFFSET = 2  # 2 Strikes OTM

# --- Risk Management ---
LOT_SIZE = 1  # Initial Quantity in Lots (Nifty Lot = 75 or 25 depending on current regulation, handled by order manager usually, but here we specify lots)
SL_PCT = 20.0       # 20% Stop Loss per leg
TARGET_PCT = 20.0   # 20% Target per leg
TRAIL_SL_PCT = 20.0 # Standard TSL Trail (Wait, user said "implement trailing SL", usually 1:1. I'll stick to a standard configuration or use the Risk Management skill defaults if generic. I'll set it to trail 5% for every 5% move or similar, but simplified: Trail by SL distance)

# --- Pyramiding ---
# "pyramidding at 5% profit. max pyramids are 3"
PYRAMID_ENABLED = True
PYRAMID_ENTRY_PCT = 5.0  # Add position every 5% profit
MAX_PYRAMID_COUNT = 3
PYRAMID_LOTS = 1         # Lots to add per pyramid

# --- System ---
DRY_RUN = True
EXPIRY_TYPE = "current_week"  # "current_week", "next_week", "monthly"
RESTORE_STATE = True

def validate_config():
    """Validates configuration parameters."""
    if SL_PCT <= 0 or TARGET_PCT <= 0:
        raise ValueError("SL and Target percentages must be positive.")
    
    if PYRAMID_ENABLED and (PYRAMID_ENTRY_PCT <= 0 or MAX_PYRAMID_COUNT < 1):
        raise ValueError("Invalid Pyramiding configuration.")
        
    try:
        datetime.strptime(EXIT_TIME, "%H:%M:%S")
    except ValueError:
        raise ValueError(f"Invalid EXIT_TIME format: {EXIT_TIME}")
    
    return True

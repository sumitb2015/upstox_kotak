from datetime import time

class StrategyConfig:
    # Instrument
    INSTRUMENT_NAME = "NIFTY"
    EXCHANGE = "NSE_INDEX"
    
    # Timeframe
    CANDLE_INTERVAL = "minute" # Base interval
    CANDLE_PERIOD = 5          # 5-minute candles
    
    # Strike Selection
    STRIKE_DISTANCE = 100      # ATM +/- 100
    EXPIRY_TYPE = "current_week"
    
    # Position Sizing
    LOT_SIZE = 75              # Default 1 Lot (Adjust as needed)
    MAX_LOTS = 4
    
    # Risk Management
    SPOT_SL_BUFFER = 0.0       # Points buffer for Spot SL
    
    # Tiered TSL Settings
    OPTION_TSL_PCT = 0.20      # Base TSL (20%)
    
    TSL_TIER_1_TRIGGER = 0.10  # 10% Profit -> Move to Cost
    TSL_TIER_2_TRIGGER = 0.20  # 20% Profit -> Tighten TSL
    TSL_TIER_2_PCT = 0.10      # New TSL distance (10%)
    
    TSL_TIER_3_TRIGGER = 0.40  # 40% Profit -> Super Tight
    TSL_TIER_3_PCT = 0.05      # New TSL distance (5%)
    
    # Time Settings
    ENTRY_START_TIME = time(9, 15)
    ENTRY_END_TIME = time(15, 0)
    EXIT_TIME = time(15, 15)
    
    # Logging
    LOG_LEVEL = "INFO"

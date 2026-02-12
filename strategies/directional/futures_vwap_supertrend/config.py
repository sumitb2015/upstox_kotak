"""
Futures VWAP Supertrend Strategy Configuration

Entry Logic (Tick-by-Tick):
- CE: Sell OTM when Futures price < VWAP AND Supertrend is Bearish (-1)
- PE: Sell OTM when Futures price > VWAP AND Supertrend is Bullish (1)
- Filter: Price must be within `max_vwap_distance_pct` (0.2%) of VWAP.
- Selection: OTM Strike with Short Buildup (Price Dec >= 20% & OI Inc >= 25%).

Pyramiding:
- Add 1 lot when individual position profit >= 10%
- Maximum 2 pyramid levels per direction
- TSL tightens (Base 10% -> 5%) per pyramid level

Exit:
- TSL hit (Monitored Tick-by-Tick)
- Trend Reversal (Futures vs VWAP or ST Reversal) - Configurable (Candle Close or Tick-by-Tick).
"""

# Strategy Configuration
CONFIG = {
    # === Underlying & Instrument ===
    # The underlying index to trade (e.g., 'NIFTY', 'BANKNIFTY', 'FINNIFTY').
    'underlying': 'NIFTY',
    
    # === Candle Settings ===
    # The timeframe for candle calculation (in minutes).
    # Used for Supertrend calculation and candle-based entry/exit checks.
    'candle_interval_minutes': 3,
    
    # === Position Sizing ===
    # Initial number of lots to trade per entry.
    'lot_size': 1,
    # Maximum number of additional entries allowed via pyramiding.
    'max_pyramid_levels': 2,
    # Absolute maximum total lots allowed (Initial + Pyramiding).
    'max_total_lots': 4,
    
    # === Strike Selection ===
    # Offset from ATM to select the strike price for Call options (e.g., 150 means ATM + 150).
    'atm_offset_ce': 150,
    # Offset from ATM to select the strike price for Put options (e.g., -150 means ATM - 150).
    'atm_offset_pe': -150,
    
    # === Indicators ===
    # Period for Average True Range (ATR) used in Supertrend calculation.
    'st_period': 10,
    # Multiplier for ATR to determine Supertrend bands.
    'st_multiplier': 2.0,
    # Number of historical candles to fetch for indicator stability.
    'lookback_candles': 500,
    
    # === Entry Conditions ===
    # Enable or disable Open Interest (OI) filter for entries.
    'oi_check_enabled': False,
    # Minimum Put-Call Ratio (PCR) to allow Long/Bullish entries (if OI check enabled).
    'pcr_lower_threshold': 0.95,
    # Maximum Put-Call Ratio (PCR) to allow Short/Bearish entries (if OI check enabled).
    'pcr_upper_threshold': 1.05,
    # Number of strikes above/below ATM to consider for cumulative OI calculation.
    'oi_strikes_radius': 4,
    
    # === Trend Safety ===
    # Maximum allowable percentage distance of price from VWAP for a valid entry.
    # Prevents entering when the trend is already over-extended.
    'max_vwap_distance_pct': 0.002, # 0.2%
    
    # === Short Buildup Filter (Entry) ===
    # Minimum price decrease percentage required to identify short buildup in options.
    'short_buildup_p_dec_threshold': 0.20, # 20% Price Decrease
    # Minimum Open Interest increase percentage required to identify short buildup.
    'short_buildup_oi_inc_threshold': 0.20, # 20% OI Increase (Code default is 30% if not set, config overrides)
    # Master switch to enable/disable the short buildup filter.
    'short_buildup_enabled': True,
    # Minimum points Out-of-the-Money (OTM) required for strike selection.
    'min_otm_offset': 100,
    
    # === Pyramiding ===
    # Profit percentage required on an existing position to trigger a pyramid entry.
    'pyramid_profit_pct': 0.10, # 10%
    
    # === Trailing Stop Loss ===
    # Initial Trailing Stop Loss percentage from the lowest price.
    'base_trailing_sl_pct': 0.10, # 10%
    # Percentage to tighten the TSL by for each pyramid level.
    # New TSL = base_trailing_sl_pct - (pyramid_level * tsl_tightening_pct)
    # Level 0 (Initial): 10% -> Level 1: 7.5% -> Level 2: 5%
    'tsl_tightening_pct': 0.025, # 2.5% per level
    
    # === Exit Conditions ===
    # Exit position if price crosses over VWAP (Trend Reversal).
    'exit_on_vwap_cross': True,
    # Exit position if Supertrend direction reverses.
    'exit_on_st_reversal': True,

    # === Timing Configuration ===
    # If False, entries are checked on every tick (Tick-by-Tick).
    # If True, entries are checked only on candle close.
    'enter_on_candle_close': False,
    # If False, exits (reversals) are checked on every tick.
    # If True, exits (reversals) are checked only on candle close.
    'exit_on_candle_close': True,
    
    # === Product Type ===
    # Product type for orders: 'D' for Intraday (MIS), 'I' for Investment (CNC/NRML).
    'product_type': 'D',
    
    # === Trading Hours ===
    # Time to start checking for entries (HH:MM).
    'entry_start_time': '09:20',
    # Time to square off all positions and stop trading (HH:MM).
    'exit_time': '15:15',
    
    # === Execution ===
    # Keep False for real trading. True suppresses order placement.
    'dry_run': False,
    # Use WebSocket for real-time data (Recommended True).
    'use_websockets': True,
    # Option expiry selection: 'current_week', 'next_week', or 'monthly'.
    'expiry_type': 'current_week',
    # Attempt to restore previous state on restart (Not fully implemented/reliable yet).
    'restore_state': False,
}

def get_tsl_percentage(pyramid_level: int) -> float:
    """
    Calculates the dynamic Trailing Stop Loss percentage based on the pyramid level.
    As positions are added (pyramiding), the TSL tightens to lock in profits.
    """
    base = CONFIG['base_trailing_sl_pct']
    reduction = CONFIG['tsl_tightening_pct']
    tsl_pct = base - (pyramid_level * reduction)
    # Ensure TSL doesn't become too tight (minimum 5%)
    return max(tsl_pct, 0.05)

def validate_config(config: dict) -> list:
    """Validates the configuration dictionary for required keys and values."""
    errors = []
    required_keys = ['underlying', 'candle_interval_minutes', 'lot_size', 'expiry_type', 'product_type', 'restore_state']
    for key in required_keys:
        if key not in config:
            errors.append(f"Missing required key: {key}")
            
    if config.get('expiry_type') not in ['current_week', 'next_week', 'monthly']:
        errors.append(f"Invalid expiry_type: {config.get('expiry_type')}")
        
    return errors

import os

# Aggressive Renko Dip Configuration

CONFIG = {
    # =========================================================================
    # CORE STRATEGY SETTINGS (RENKO & ENTRY)
    # -------------------------------------------------------------------------
    'underlying': 'NIFTY',           # The primary instrument to track for signals (e.g., NIFTY Index)
    'nifty_brick_size': 5,           # Size of each Renko brick in points. Smaller = More signals (Aggressive).
    'nifty_reversal_brick_count': 2, # How many adverse bricks are needed to confirm a trend reversal (Standard=2).
    'nifty_renko_ema_period': 10,    # Period for the Renko-based EMA. 
                                     # Logic: 
                                     #   - LONG Entry if Close > EMA
                                     #   - SHORT Entry if Close < EMA
    'trend_streak': 2,               # Number of consecutive same-color bricks required to trigger an entry.
                                     # Reduced from 3 to 2 for faster, more aggressive entries.
    'resumption_streak': 2,          # Number of bricks required to add to a position (Pyramiding) 
                                     # if the trend continues after entry.

    # =========================================================================
    # RSI FILTER SETTINGS (MOMENTUM)
    # -------------------------------------------------------------------------
    'rsi_period': 14,                # Lookback period for RSI calculation on 1-minute candles.
    'rsi_pivot': 50,                 # The baseline for trend determination.
                                     #   - Bullish if RSI > 50
                                     #   - Bearish if RSI < 50
    'rsi_overbought': 85,            # Upper bound for RSI. (Extended for aggressive strategy to allow runs)
    'rsi_oversold': 15,              # Lower bound for RSI. (Extended for aggressive strategy to allow runs)
    
    # =========================================================================
    # OPTION STRIKE SELECTION & EXPIRY
    # -------------------------------------------------------------------------
    'expiry_type': 'current_week',   # Which expiry to trade: 'current_week', 'next_week', or 'monthly'.
    'strike_selection': 'ATM',       # Reference strike: 'ATM' (At The Money) is standard.
    'strike_offset': 2,              # Adjustment from ATM. 
                                     #   - 1 means 1 strike OTM (Out of The Money)
                                     #   - Example: Nifty 24000, Offset 1 -> Buy CE 24050 / PE 23950
    'product_type': 'MIS',           # Order type: 'MIS' (Intraday) or 'NRML' (Overnight/Carryforward).

    # =========================================================================
    # RISK MANAGEMENT & EXITS (OPTION RENKO)
    # -------------------------------------------------------------------------
    'option_brick_pct': 0.05,        # Brick size for the OPTION chart, calculated as % of entry price.
                                     #   - Example: Price 100, 5% = 5 point brick size.
    'min_option_brick': 1.0,         # Minimum absolute floor for option brick size (to prevent tiny bricks).
    
    'tsl_brick_count': 3,            # Trailing Stop Loss sensitivity.
                                     #   - Exit if the option moves X bricks against the trade.
    'tsl_type': 'staircase',         # How the TSL moves:
                                     #   - 'fluid': Updates on every tick high/low (tightest).
                                     #   - 'staircase': Updates only when a full new brick forms (step-by-step).
    'wait_for_candle_close': True,   # Exit execution timing:
                                     #   - True: Wait for the 1-minute candle to close before exiting on TSL.
                                     #   - False: Exit INSTANTLY if the LTP touches the TSL level.
    'profit_target_bricks': 6,       # Fixed Profit Target:
                                     #   - If profit reaches X bricks, exit position immediately.
                                     #   - Helpful for scalping sharp moves.

    # =========================================================================
    # DYNAMIC TRAILING (PROFIT LOCKING)
    # -------------------------------------------------------------------------
    'dynamic_tightening': False,      # Enable aggressive TSL tightening when in profit.
    'tighten_after_bricks': 2,       # Trigger: Start tightening after we are X bricks in profit.
    'tightened_multiplier': 1.5,     # Action: Reduce TSL width to 1.5x brick size (Standard is usually 2.0x or 3.0x).
                                     #   - This locks in profit faster as the trade moves in our favor.

    # =========================================================================
    # PYRAMIDING (ADDING TO WINNERS)
    # -------------------------------------------------------------------------
    'enable_pyramiding': True,       # Enable adding chunks to a winning position.
    'trading_lots': 1,               # Initial entry quantity (in Lots).
    'max_pyramid_lots': 3,           # Maximum TOTAL lots allowed (Base + Pyramids).
    'pyramid_interval': 2,           # Frequency: Add a new lot every X *Option Bricks* of movement in favor.

    # =========================================================================
    # SYSTEM & SAFETY SETTINGS
    # -------------------------------------------------------------------------
    'candle_fetch_delay_seconds': 3, # Time (in sec) to wait after a new minute starts before fetching API data.
                                     #   - Ensures we don't get stale data if the broker is slow to update.
    'max_bricks_per_update': 100,    # Circuit breaker: Limits processing if a massive spike creates too many bricks at once.
    'prevent_immediate_reentry': True, # Cool-down Logic:
                                     #   - Prevents re-entering the SAME trend immediately after being stopped out.
    'reentry_cooldown_bricks': 2,    #   - If True, wait for X new Nifty bricks to form before allowing re-entry.

    # =========================================================================
    # MARKET FILTERS (WHIPSAW PROTECTION)
    # -------------------------------------------------------------------------
    'enable_regime_filter': False,   # Master switch for the "Choppy Market" filter.
    'regime_lookback_bricks': 20,    # Sample size: Look at the last 20 bricks.
    'max_reversal_pct': 0.40,        # Threshold: If >40% of bricks were reversals (color changes), 
                                     #   - Assume market is Choppy/Ranging -> DO NOT TRADE.
    
    'enable_momentum_filter': False, # Master switch for speed-based filtering. (Disabled by default)
    'min_brick_momentum': 0.3,       # Min Speed: Market must be moving at least X bricks/minute.
    'max_brick_momentum': 10.0,      # Max Speed: Avoid trading if market is exploding (risk of slippage).

    # =========================================================================
    # EXECUTION TIMING
    # -------------------------------------------------------------------------
    'entry_start_time': "09:20",     # No entries before this time (Let market settle).
    'exit_all_time': "15:15",        # Hard exit time for all intraday positions.
    
    'verbose': True,                 # Enable detailed logging.
    'dry_run': False,                # True = Paper Trading (No real orders). False = Real Money.
    'restore_state': False,          # Crash Recovery:
                                     #   - True: Try to reload last known position from file on restart.
                                     #   - False: Always start fresh (Safer for intraday).
    'state_file': os.path.join(os.path.dirname(os.path.abspath(__file__)), 'strategy_state.json')
}

def validate_config(config):
    required_keys = ['underlying', 'expiry_type', 'nifty_brick_size', 'trading_lots', 'tsl_brick_count']
    missing = [k for k in required_keys if k not in config]
    if missing:
        raise ValueError(f"Missing config keys: {missing}")
    
    if config['expiry_type'] not in ['current_week', 'next_week', 'monthly']:
        raise ValueError(f"Invalid expiry_type: {config['expiry_type']}")
    
    if config['tsl_brick_count'] < 1:
        raise ValueError(f"tsl_brick_count must be >= 1, got {config['tsl_brick_count']}")


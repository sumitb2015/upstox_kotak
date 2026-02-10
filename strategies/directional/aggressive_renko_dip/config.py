import os

# Aggressive Renko Dip Configuration

CONFIG = {
    'underlying': 'NIFTY',
    'nifty_brick_size': 5,       # Aggressive Signal Renko
    'nifty_reversal_brick_count': 2, # Bricks needed for Nifty reversal (Standard=2)
    'nifty_renko_ema_period': 20, # EMA Filter for Renko Entry
    'trend_streak': 2,            # 2 bricks for entry (reduced from 3 for aggressive entry)
    'resumption_streak': 2,       # 2 bricks for pyramid
    
    'rsi_period': 14,
    'rsi_pivot': 50,
    'rsi_overbought': 85,         # Extended for aggressive
    'rsi_oversold': 15,           # Extended for aggressive
    
    'option_brick_pct': 0.08,     # 8% premium trail
    'min_option_brick': 1.0,
    'tsl_brick_count': 3,         # Exit after 2 opposite-direction Option bricks (Reversal)
    'tsl_type': 'staircase',      # 'fluid' (tick-by-tick) or 'staircase' (step-by-step)
    'wait_for_candle_close': True, # [NEW] True = Exit only after minute ends; False = Exit instantly on tick breach
    
    # Candle Fetch Timing
    'candle_fetch_delay_seconds': 3,  # Delay after minute boundary to fetch candle (adjust if API data is stale)
    
    # Safety Limits
    'max_bricks_per_update': 100,  # Safety cap for brick formation in a single tick
    
    # Pyramid Settings
    'enable_pyramiding': True,  # Disabled by default
    'trading_lots': 1,
    'max_pyramid_lots': 3,
    'pyramid_interval': 3,  # OPTION bricks (not Nifty) for pyramid
    
    'expiry_type': 'current_week', # Options: 'current_week', 'next_week', 'monthly'
    'strike_selection': 'ATM',    # Or 'OTM'
    'strike_offset': 1,           # Number of strikes OTM (Automatic direction)
    
    # Market Regime Filter (Whipsaw Protection)
    'enable_regime_filter': False,
    'regime_lookback_bricks': 20,  # Number of bricks to analyze
    'max_reversal_pct': 0.40,      # Max 40% reversals = trending
    
    # Brick Momentum Filter (Optional - can be noisy on restarts)
    'enable_momentum_filter': False,  # Disabled by default
    'min_brick_momentum': 0.3,     # Min bricks/minute (10pts every 3+ mins)
    'max_brick_momentum': 10.0,    # Max bricks/minute (too fast = whipsaw)
    
    'product_type': 'MIS',        # 'MIS' for intraday, 'NRML' for carryforward
    'entry_start_time': "09:20",
    'exit_all_time': "15:15",
    
    'verbose': True,
    'dry_run': False,
    'restore_state': False, # Disabled by default as per agent rules
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


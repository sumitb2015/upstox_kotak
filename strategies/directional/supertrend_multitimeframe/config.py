# Supertrend Multi-Timeframe Strategy Configuration

CONFIG = {
    # Instrument Settings
    'underlying': 'NIFTY',
    'expiry_type': 'current_week',  # 'current_week', 'monthly', 'next_week'
    'target_premium': 90,           # Target premium for Strike Selection
    
    # Timeframe Settings
    'nifty_interval': '3minute',    # Nifty Index Interval
    'option_interval': '3minute',   # Option Chart Interval
    
    # Supertrend Settings
    'st_period': 10,
    'st_multiplier': 2.0,
    
    # Execution Settings
    'product_type': 'MIS',          # 'MIS' or 'NRML'
    'use_websocket': True, # Re-enabled as requested
    'trading_lots': 1,              # Number of lots to trade
    'max_positions': 1,             # Max concurrent positions
    'cooldown_minutes': 5,          # Minutes to wait before re-entering same side after exit
    
    # Risk Management
    'sl_buffer_points': 5.0,        # Optional buffer for SL above Supertrend
    'target_profit_points': 40.0,   # Fixed target (Optional)
    'min_entry_gap_pct': 0.02,      # Minimum 2% gap between Price and ST for entry
    'exit_on_candle_close': True,   # If True, waits for candle close to confirm trend reversal (avoids wicks)
    'hard_stop_breach_duration_sec': 30,  # Seconds of sustained breach before hard stop exit (filters wicks)
    
    # Global Risk Management (Hardening)
    'max_loss_pct': 0.50,          # Max 50% loss on collect premium before exit
    'profit_locking': {
        'enabled': True,
        'lock_threshold_pct': 0.30, # Start locking when profit hits 30% of entry premium
        'lock_tiers': [
            (0.30, 0.50), # > 30% Profit: Lock 50% of peak profit (Trailing)
            (0.50, 0.70), # > 50% Profit: Lock 70% of peak profit
            (0.70, 0.85), # > 70% Profit: Lock 85% of peak profit
            (1.00, 0.95)  # > 100% Profit: Lock 95% (Near full protection)
        ]
    },
    
    # System Settings
    'verbose': True,
    'dry_run': False,               # Set to True for paper trading
    'state_file': 'strategies/directional/supertrend_multitimeframe/strategy_state.json'
}

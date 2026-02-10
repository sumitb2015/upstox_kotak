"""
EMA Directional Hedge Strategy Configuration

Entry Logic:
- Bull Put Spread: Price above both EMAs, EMA9 > EMA20, difference increasing
- Bear Call Spread: Price below both EMAs, EMA9 < EMA20, difference decreasing

Exit Logic:
- Profit Target: 50% of max profit
- Stop Loss: 1.5x of max profit
- Momentum Exit: When EMA momentum reverses (2 consecutive candles)
- Trailing SL: Breakeven after 30 min, lock 20% profit at 40% milestone
"""

# Strategy Configuration
CONFIG = {
    # === Underlying & Instrument ===
    'underlying': 'NIFTY',
    
    # === Candle Settings ===
    'candle_interval_minutes': 3,  # 3-minute candles for scalping
    
    # === Position Sizing ===
    'lot_size': 1,  # Lots per trade
    'max_trades_per_day': 3,  # Prevent overtrading
    
    # === Pyramiding (Scale-in) ===
    'enable_pyramiding': True,
    'max_lots': 5,  # Max total lots allowed
    'pyramid_step_profit_pct': 0.15,  # Add lot every 15% profit gain
    
    # === Strike Selection ===
    # Bull Put Spread: Sell 1 strike OTM PUT, Buy hedge 100-150 points lower
    # Bear Call Spread: Sell 1 strike OTM CALL, Buy hedge 100-150 points higher
    'strikes_otm': 1,  # Number of strikes OTM for short leg
    'hedge_distance': 150,  # Points away for hedge leg
    
    # === EMA Settings ===
    'ema_fast': 9,  # Fast EMA
    'ema_slow': 20,  # Slow EMA
    'min_ema_diff_threshold': 5,  # Reduced threshold for 3-min scalping
    'lookback_candles': 50,  # Candles to fetch for EMA calculation
    
    # === Momentum Detection ===
    'momentum_confirmation_candles': 1,  # React on 1st candle (Scalping)
    'momentum_exit_candles': 2,  # Require N reversal candles to exit
    
    # === Entry Conditions ===
    'enable_price_position_filter': True,  # Price must be above/below both EMAs
    
    # === Exit Conditions ===
    'profit_target_pct': 0.30,  # 30% of max profit (Faster exit)
    'stop_loss_multiplier': 1.5,  # 1.5x of max profit
    'use_momentum_exit': True,  # Exit on momentum reversal
    
    # === Trailing Stop Loss ===
    'enable_trailing_sl': True,
    'trail_to_breakeven_after_minutes': 30,  # Trail to breakeven after 30 min
    'trail_to_lock_profit_at_pct': 0.40,  # Lock 20% profit when 40% reached
    'lock_profit_amount_pct': 0.20,  # Amount to lock
    
    # === Product Type ===
    'product_type': 'D',  # 'D' = Intraday (MIS), 'I' = Delivery
    
    # === Trading Hours ===
    'entry_start_time': '10:30',  # Start after indicators stabilize
    'entry_end_time': '15:00',  # Stop new entries
    'exit_time': '15:18',  # Mandatory square-off
    
    # === Risk Management ===
    'max_loss_per_day': 5000,  # Maximum loss before stopping
    
    # === Execution ===
    'dry_run': True,  # Set to False for live trading
    'use_atomic_execution': True,  # Critical for spread orders
    
    # === Expiry ===
    'expiry_type': 'next_week',  # Options: 'current_week', 'next_week', 'monthly'
    
    # === Logging ===
    'verbose': True,  # Detailed logging
}


def validate_config():
    """Validate configuration parameters."""
    assert CONFIG['lot_size'] > 0, "Lot size must be positive"
    assert CONFIG['ema_fast'] < CONFIG['ema_slow'], "Fast EMA must be less than slow EMA"
    assert CONFIG['candle_interval_minutes'] > 0, "Candle interval must be positive"
    assert 0 < CONFIG['profit_target_pct'] <= 1, "Profit target must be between 0 and 1"
    assert CONFIG['stop_loss_multiplier'] > 0, "Stop loss multiplier must be positive"
    assert CONFIG['min_ema_diff_threshold'] >= 0, "EMA threshold must be non-negative"
    assert CONFIG['momentum_confirmation_candles'] >= 1, "Momentum confirmation must be >= 1"
    assert CONFIG['max_trades_per_day'] > 0, "Max trades per day must be positive"
    assert CONFIG['hedge_distance'] > 0, "Hedge distance must be positive"
    
    print("✅ Configuration validated successfully")


if __name__ == "__main__":
    validate_config()
    print("\n📋 EMA Hedge Spread Strategy Configuration:")
    for key, value in CONFIG.items():
        print(f"  {key}: {value}")

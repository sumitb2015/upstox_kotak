"""
Option Scalper Strategy Configuration
"""

SCALPER_CONFIG = {
    # Strategy Parameters
    "strategy_name": "OptionScalper",
    "index_symbol": "NSE_INDEX|Nifty 50",  # Underlying index
    
    # Strike Selection
    "option_strike_offset": 100, # Further OTM for selling safety
    "execution_mode": "SHORT",  # LONG (Option Buying) or SHORT (Option Selling)
    
    # Depth Analysis Parameters
    "depth_imbalance_threshold": 2.0,  # Buy Qty / Sell Qty > 2.0 for Bullish
    "depth_wall_size": 25000,          # Minimum quantity to consider a "Wall" (Nifty specific)
    
    # Momentum Parameters
    "momentum_threshold": 2.0,         # Points moved in last minute to trigger
    
    # Execution & Risk Management
    "product_type": "MIS",            # Intraday
    "lot_size": 75,                   # Nifty Lot Size (Will be auto-detected, but good for defaults)
    "quantity_lots": 1,               # Number of lots to trade
    
    # Exit Rules (Scalping - Quick In/Out)
    "target_points": 5.0,             # Selling: Collect 5 points (faster)
    "stop_loss_points": 10.0,         # Selling: Wider SL for volatility
    "max_hold_time_seconds": 180,     # 3 minutes max hold
    "trailing_sl_trigger": 7.0,       # Start trailing after 7 points gain
    
    # Risk Limits
    "max_trades_per_day": 10,
    "max_daily_loss": 2000,
    
    # System
    "dry_run": True,                  # Default to Dry Run for safety
    "polling_interval": 1.0           # Depth polling interval in seconds
}

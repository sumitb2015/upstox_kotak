"""
Dynamic Straddle Skew Strategy Configuration

Entry:
- 09:20: Neutral Short Straddle (CE + PE ATM)

Skew Bias & Pyramiding:
- Threshold: Winning Premium < Losing Premium * 0.70 (30% Skew)
- Action: Add 1 lot to the winning (decaying) side
- Scaling: Add more lots every 10% further decay of winning leg
- Max Lots: 4 total on winning side

Defensive Reduction:
- Trigger: Winning premium rises 15% from its lowest tracked price
- Action: Reduce last added lot
"""

CONFIG = {
    # === Underlying & Instrument ===
    'underlying': 'NIFTY',
    
    # === Position Sizing ===
    'initial_lots': 1,         # Lots per entry (1 CE + 1 PE)
    'pyramid_lot_size': 1,     # Lots to add per pyramid level
    'max_pyramid_lots': 3,     # Additional lots 
    'max_total_lots': 5,       # Safety cap (6 Winning + 2 Losing = 8 total)
    
    # === Entry Timing ===
    'entry_start_time': '09:20',
    'exit_time': '15:15',
    
    # === Skew Detection ===
    'skew_threshold_pct': 0.3,  # Increased from 0.15 to 0.20 (20% diff to trigger bias)
    'skew_persistence_ticks': 5, # Require 5 consecutive ticks (seconds) of skew to confirm bias
    
    # === Pyramiding Logic ===
    'pyramid_trigger_decay_pct': 0.1, # Increased from 0.07 (10% decay needed to add lot)
    'pyramid_profit_booking_pct': 0.25, # Keep profit booking same
    
    # === Defensive Reduction ===
    'reduction_recovery_pct': 0.25, # Increased from 0.20 (Allow 30% pullback before cutting)
    'reduction_cooldown_minutes': 3, # Cooldown after reducing to base lots (prevents immediate re-pyramid)
    
    # === Roll Adjustment (Major Skew) ===
    'roll_adjustment_enabled': True,
    'roll_skew_threshold': 0.30,      # Trigger roll if skew > 40% (Strong Trend)
    'roll_premium_match_pct': 1.0,    # Target new premium = 100% of losing leg
    
    # === Strike Selection ===
    'strike_selection_type': 'STRANGLE_PREMIUM', 
    # Options: 'STRADDLE' (ATM), 'STRANGLE_OFFSET' (Fixed Spread), 'STRANGLE_PREMIUM' (Target Price)
    
    'strangle_spread': 100,    # Distance from ATM (Used if type is STRANGLE_OFFSET)
    'target_premium': 60,      # Target Price for CE/PE (Used if type is STRANGLE_PREMIUM)
    
    # === Product Type ===
    'product_type': 'D',       # 'D' = Intraday (MIS), 'I' = Delivery
    
    # === Risk Management ===
    'max_loss_per_day': 10000,
    # 'target_profit_daily': 10000, # Legacy fixed amount
    
    # === Percentage Based Targets (Calculated on Initial Capital) ===
    'target_profit_pct': 0.30,  # Exit at 40% gain on deployed capital
    
    'profit_locking': {
        'enabled': True,
        'lock_threshold_pct': 0.1, # Start locking when profit hits 5% of capital (e.g. ~2k on 40k)
        
        # New Tiered Locking (Hardening)
        # Format: (Min_Profit_Abs, Lock_Ratio)
        # If profit exceeds Min_Profit, use that Lock_Ratio.
        # Processed in ascending order.
        'lock_tiers': [
            (0,    0.30), # Base: 40%
            (1500, 0.60), # > 2k: Lock 60%
            (2250, 0.70), # > 4k: Lock 70%
            (3000, 0.75), # > 6k: Lock 75%
            (4000, 0.80), # > 8k: Lock 80% (Aggressive)
        ]
    },
    'individual_sl_pct': None, # Disabled - rely on global P&L targets only
    
    # === Execution ===
    'dry_run': False,          # Set to False for live trading
    'verbose': True,           # Detailed logging
    'use_websockets': True,
    
    # === RSI Entry Filter ===
    'rsi_filter_enabled': True,
    'rsi_period': 14,
    'rsi_lower_threshold': 40,
    'rsi_upper_threshold': 60,
    
    # === Expiry ===
    'expiry_type': 'current_week', # 'current_week', 'next_week', 'monthly'
}

def validate_config():
    """Validate configuration parameters."""
    assert CONFIG['initial_lots'] > 0, "Initial lots must be positive"
    assert CONFIG['max_pyramid_lots'] >= 0, "Max pyramid lots must be non-negative"
    assert 0 < CONFIG['skew_threshold_pct'] < 1, "Skew threshold must be between 0 and 1"
    assert 0 < CONFIG['reduction_recovery_pct'] < 1, "Reduction recovery must be between 0 and 1"
    
    # New Validations
    valid_modes = ['STRADDLE', 'STRANGLE', 'STRANGLE_OFFSET', 'STRANGLE_PREMIUM']
    assert CONFIG['strike_selection_type'] in valid_modes, "Invalid Strike Selection Type"
    
    if CONFIG['strike_selection_type'] == 'STRANGLE_OFFSET':
        assert CONFIG['strangle_spread'] > 0, "Strangle spread must be positive"
        
    if CONFIG['strike_selection_type'] == 'STRANGLE_PREMIUM':
        assert CONFIG['target_premium'] > 0, "Target premium must be positive"
        
    if CONFIG.get('target_profit_pct'):
        assert 0 < CONFIG['target_profit_pct'] < 10, "Target Profit Pct seems abnormal (Expected 0.0-10.0)"
        
    if CONFIG.get('rsi_filter_enabled'):
        assert CONFIG['rsi_period'] > 0, "RSI period must be positive"
        assert 0 <= CONFIG['rsi_lower_threshold'] < CONFIG['rsi_upper_threshold'] <= 100, "Invalid RSI thresholds"

    print("✅ Configuration validated successfully")

if __name__ == "__main__":
    validate_config()
    print("\n📋 Strategy Configuration:")
    for key, value in CONFIG.items():
        print(f"  {key}: {value}")

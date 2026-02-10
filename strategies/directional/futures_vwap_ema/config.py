"""
Futures VWAP EMA Strategy Configuration

Entry Logic:
- CE: Sell ATM+150 when Futures price < VWAP AND price < EMA(20)
- PE: Sell ATM-150 when Futures price > VWAP AND price > EMA(20)

Pyramiding:
- Add 1 lot when individual position profit >= 10%
- Maximum 2 pyramid levels per direction
- TSL tightens by 5% per pyramid level

Exit:
- TSL hit (20% from lowest, tightening to 15% at pyramid 1, 10% at pyramid 2)
- Futures price crosses back above/below VWAP (depending on direction)
"""

# Strategy Configuration
CONFIG = {
    # === Underlying & Instrument ===
    'underlying': 'NIFTY',
    
    # === Candle Settings ===
    'candle_interval_minutes': 1,  # Changed to 1-minute for faster signals  # User configurable interval
    
    # === Position Sizing ===
    'lot_size': 1,  # Lots per entry/pyramid
    'max_pyramid_levels': 2,  # Maximum pyramid positions
    'max_total_lots': 4,      # Maximum total lots allowed across all positions
    
    # === Strike Selection ===
    'atm_offset_ce': 150,  # CE: ATM + 150
    'atm_offset_pe': -150,  # PE: ATM - 150
    
    # === Indicators ===
    'ema_period': 20,  # 20 EMA for trend
    'lookback_candles': 50,  # Candles to fetch for VWAP/EMA calculation
    
    # === Entry Conditions ===
    # CE Entry: price < VWAP AND price < EMA AND PCR < 0.9
    # PE Entry: price > VWAP AND price > EMA AND PCR > 1.1
    'oi_check_enabled': False,
    'pcr_lower_threshold': 0.95,  # For CE Sell (More sensitive)
    'pcr_upper_threshold': 1.05,  # For PE Sell (More sensitive)
    'oi_strikes_radius': 4,      # ATM ± 4 strikes (total 9 strikes)
    'allow_trend_entry': True,   # Allow entry if price is already above/below EMA in a strong trend
    
    # === Pyramiding ===
    'pyramid_profit_pct': 0.10,  # 10% profit per position to add pyramid
    
    # === Trailing Stop Loss ===
    'base_trailing_sl_pct': 0.20,  # Base TSL: 20% from lowest price
    'tsl_tightening_pct': 0.05,  # Reduce by 5% per pyramid level
    # Level 0: 20%, Level 1: 15%, Level 2: 10%
    
    # === Exit Conditions ===
    'exit_on_vwap_cross': True,  # Exit when price crosses back
    'exit_on_ema_cross': False,  # Don't use EMA for exit
    
    # === Product Type ===
    'product_type': 'D',  # 'D' = Intraday (MIS), 'I' = Delivery
    
    # === Trading Hours ===
    'entry_start_time': '09:20',  # Earliest entry time
    'exit_time': '15:15',  # Force exit before market close
    
    # === Risk Management ===
    'max_loss_per_day': 5000,  # Maximum loss before stopping (optional)
    
    # === Execution ===
    'dry_run': False,  # Set to False for live trading
    'use_websockets': True,  # Live tracking via WebSocket
    
    # === Expiry ===
    'expiry_type': 'current_week',  # Options: 'current_week', 'next_week', 'monthly'
    
    # === Logging ===
    'verbose': True,  # Detailed logging
}


def get_tsl_percentage(pyramid_level: int) -> float:
    """
    Calculate TSL percentage for a given pyramid level.
    
    Args:
        pyramid_level: Current pyramid level (0, 1, 2)
        
    Returns:
        TSL percentage (e.g., 0.20, 0.15, 0.10)
    """
    base = CONFIG['base_trailing_sl_pct']
    reduction = CONFIG['tsl_tightening_pct']
    
    tsl_pct = base - (pyramid_level * reduction)
    
    # Ensure TSL never goes below 5%
    return max(tsl_pct, 0.05)


def validate_config():
    """Validate configuration parameters."""
    assert CONFIG['lot_size'] > 0, "Lot size must be positive"
    assert CONFIG['max_pyramid_levels'] >= 0, "Max pyramid levels must be non-negative"
    assert 0 < CONFIG['base_trailing_sl_pct'] <= 1, "Base TSL must be between 0 and 1"
    assert 0 <= CONFIG['tsl_tightening_pct'] < CONFIG['base_trailing_sl_pct'], "TSL tightening must be less than base"
    assert 0 < CONFIG['pyramid_profit_pct'] <= 1, "Pyramid profit must be between 0 and 1"
    assert CONFIG['ema_period'] > 0, "EMA period must be positive"
    assert CONFIG['candle_interval_minutes'] > 0, "Candle interval must be positive"
    
    print("✅ Configuration validated successfully")


if __name__ == "__main__":
    validate_config()
    print("\n📋 Strategy Configuration:")
    for key, value in CONFIG.items():
        print(f"  {key}: {value}")
    
    print("\n📊 TSL Percentages per Level:")
    for level in range(CONFIG['max_pyramid_levels'] + 1):
        print(f"  Level {level}: {get_tsl_percentage(level)*100:.0f}%")

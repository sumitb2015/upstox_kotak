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
- Trend Reversal (Futures vs VWAP or ST Reversal) on Candle Close.
"""

# Strategy Configuration
CONFIG = {
    # === Underlying & Instrument ===
    'underlying': 'NIFTY',
    
    # === Candle Settings ===
    'candle_interval_minutes': 3,
    
    # === Position Sizing ===
    'lot_size': 1,
    'max_pyramid_levels': 2,
    'max_total_lots': 4,
    
    # === Strike Selection ===
    'atm_offset_ce': 150,
    'atm_offset_pe': -150,
    
    # === Indicators ===
    'st_period': 10,  # Supertrend ATR Period
    'st_multiplier': 2.0,  # Supertrend Multiplier
    'lookback_candles': 500,  # Fetch more for stable Supertrend
    
    # === Entry Conditions ===
    'oi_check_enabled': False,
    'pcr_lower_threshold': 0.95,
    'pcr_upper_threshold': 1.05,
    'oi_strikes_radius': 4,
    
    # === Trend Safety ===
    'max_vwap_distance_pct': 0.002, # 0.2% Max distance from VWAP for entry (Prevent late entry)
    
    # === Short Buildup Filter (Entry) ===
    'short_buildup_p_dec_threshold': 0.20, # 20% Price Decrease
    'short_buildup_oi_inc_threshold': 0.25, # 30% OI Increase
    'short_buildup_enabled': True,
    'min_otm_offset': 100, # Minimum 100 pts OTM from ATM
    
    # === Pyramiding ===
    'pyramid_profit_pct': 0.10,
    
    # === Trailing Stop Loss ===
    'base_trailing_sl_pct': 0.10, # Tightened to 10% (was 20%)
    'tsl_tightening_pct': 0.05,
    
    # === Exit Conditions ===
    'exit_on_vwap_cross': True,
    'exit_on_st_reversal': True,
    
    # === Product Type ===
    'product_type': 'D',  # 'D' = Intraday (MIS)
    
    # === Trading Hours ===
    'entry_start_time': '09:20',
    'exit_time': '15:15',
    
    # === Execution ===
    'dry_run': False,
    'use_websockets': True,
    'expiry_type': 'current_week',
}

def get_tsl_percentage(pyramid_level: int) -> float:
    base = CONFIG['base_trailing_sl_pct']
    reduction = CONFIG['tsl_tightening_pct']
    tsl_pct = base - (pyramid_level * reduction)
    return max(tsl_pct, 0.05)

"""
Positional Monthly Strangle Configuration
"""
import os

CONFIG = {
    'strategy_name': 'MONTHLY_STRANGLE',
    'underlying': 'NIFTY',
    
    # === Execution ===
    'dry_run': False,
    'db_path': os.path.join(os.path.dirname(__file__), 'strangle_trades.db'),
    
    # === Strike Selection ===
    'expiry_type': 'monthly',
    'expiry_type': 'monthly',
    # 'strike_offset': 1000,   # Spot +/- 1000 (Deprecated)
    'target_premium': 60,    # Find strike closest to this premium
    
    # === Position Sizing ===
    'lots': 1,
    
    # === Risk Management ===
    'stop_loss_pct': 0.30,   # 30% of Premium
    'target_profit_pct': 0.50, # 50% of Premium
    
    # === Time ===
    'entry_time': '09:30',
    'check_interval': 60,    # Check every minute (Positional = Low Frequency)
}

def validate_config():
    assert CONFIG['target_premium'] > 0
    assert 0 < CONFIG['stop_loss_pct'] < 10
    print("✅ Configuration validated")

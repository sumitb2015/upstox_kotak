"""
Portfolio Manager Configuration
-------------------------------
Global Risk Management settings for the Kotak account.
"""

CONFIG = {
    # === P&L Thresholds (Absolute Values in ₹) ===
    'TARGET_PROFIT': 5000.0,   # Exit ALL if Daily Profit >= 5000
    'MAX_LOSS': -5000.0,       # Exit ALL if Daily Loss <= -5000
    
    # === Profit Locking (Step-Up Trailing) ===
    # If P&L reaches 'reach', we ensure it doesn't drop below 'lock_min'
    'PROFIT_LOCKING': [
        {'reach': 2000, 'lock_min': 1000},  # Reach 2k, lock 1k
        {'reach': 3000, 'lock_min': 2000},  # Reach 3k, lock 2k
        {'reach': 4000, 'lock_min': 3000},  # Reach 4k, lock 3k
    ],
    
    # === Monitoring ===
    'POLL_INTERVAL': 5,        # Seconds between P&L checks
    
    # === Execution ===
    'DRY_RUN': True,           # If True, simulates square-off logic without placing orders
    
    # === Safety ===
    'ENABLE_KILL_SWITCH': True, # Creates lock file to stop other strategies
    'LOCK_FILE_PATH': 'c:/algo/upstox/.STOP_TRADING'
}

def validate_config():
    """Validate configuration parameters."""
    print("[INFO] Validating Portfolio Manager Config...")
    
    assert CONFIG['TARGET_PROFIT'] > 0, "Target Profit must be positive"
    assert CONFIG['MAX_LOSS'] < 0, "Max Loss must be negative"
    assert CONFIG['POLL_INTERVAL'] >= 1, "Poll Interval must be at least 1 second"
    
    print("[SUCCESS] Configuration validated successfully")

if __name__ == "__main__":
    validate_config()

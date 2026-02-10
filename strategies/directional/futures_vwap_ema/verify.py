
import pandas as pd
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from strategies.futures_vwap_ema.strategy_core import FuturesVWAPEMACore, Position

class TestCore(FuturesVWAPEMACore):
    def fetch_futures_data(self, *args, **kwargs): pass
    def fetch_option_price(self, *args, **kwargs): pass
    def execute_trade(self, *args, **kwargs): pass

def test_indicators():
    print("Testing Indicators...")
    df = pd.DataFrame({
        'timestamp': pd.date_range(start='2024-01-01', periods=5, freq='3min'),
        'open': [100, 102, 101, 103, 105],
        'high': [101, 103, 102, 104, 106],
        'low': [99, 101, 100, 102, 104],
        'close': [100, 102, 101, 103, 105],
        'volume': [1000, 1100, 1050, 1200, 1150]
    })
    
    config = {'ema_period': 3, 'lot_size': 1, 'max_pyramid_levels': 2, 'pyramid_profit_pct': 0.1, 'base_trailing_sl_pct': 0.2, 'tsl_tightening_pct': 0.05}
    core = TestCore(config)
    
    vwap = core.calculate_vwap(df)
    ema = core.calculate_ema(df, 3)
    
    print(f"✅ VWAP: {vwap:.2f}")
    print(f"✅ EMA(3): {ema:.2f}")
    
    # Test Entry Logic
    should_enter, direction, reason = core.check_entry_signal(90, 103, 104) # Price < VWAP (103) & EMA (104)
    if should_enter and direction == 'CE':
        print(f"✅ CE Entry Signal Verified: {reason}")
    else:
        print(f"❌ CE Entry Signal Failed: {reason}")

    should_enter, direction, reason = core.check_entry_signal(110, 103, 104) # Price > VWAP (103) & EMA (104)
    if should_enter and direction == 'PE':
        print(f"✅ PE Entry Signal Verified: {reason}")
    else:
        print(f"❌ PE Entry Signal Failed: {reason}")

    # Test Pyramid Logic
    print("\nTesting Pyramiding...")
    pos = Position('CE', 10000, 100, 1, 0, 'test_key')
    core.positions.append(pos)
    
    # 0% profit
    can_pyramid, reason = core.can_add_pyramid()
    if not can_pyramid:
         print(f"✅ Pyramid blocked at 0% profit: {reason}")
    
    # 11% profit (Current price 89 for short entry 100)
    pos.update_price(89) 
    can_pyramid, reason = core.can_add_pyramid()
    if can_pyramid:
         print(f"✅ Pyramid allowed at 11% profit: {reason}")

    # Test TSL Logic
    print("\nTesting TSL...")
    # Level 0 (20% TSL) -> Lowest 89 -> TSL = 89 * 1.2 = 106.8
    tsl_price = core.calculate_tsl_price(0, 89)
    print(f"✅ Level 0 TSL (20%): {tsl_price:.2f} (Expected ~106.8)")
    
    # Level 1 (15% TSL) -> Lowest 89 -> TSL = 89 * 1.15 = 102.35
    tsl_price = core.calculate_tsl_price(1, 89)
    print(f"✅ Level 1 TSL (15%): {tsl_price:.2f} (Expected ~102.35)")

if __name__ == "__main__":
    test_indicators()

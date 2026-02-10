
import sys
import os
import pandas as pd
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from strategies.directional.futures_vwap_ema.strategy_core import FuturesVWAPEMACore, Position
from strategies.directional.futures_vwap_ema.config import CONFIG

class MockStrategy(FuturesVWAPEMACore):
    def fetch_futures_data(self, *args, **kwargs): pass
    def fetch_option_price(self, *args, **kwargs): pass
    def execute_trade(self, *args, **kwargs): pass

def test_lot_cap():
    print("\nTesting Max Total Lots Cap...")
    
    test_config = CONFIG.copy()
    test_config['max_total_lots'] = 4
    test_config['lot_size'] = 1
    test_config['max_pyramid_levels'] = 5 # Set high to ensure lot cap hits first
    test_config['pyramid_profit_pct'] = 0.10
    
    strategy = MockStrategy(test_config)
    
    # 1. Add initial position (1 lot)
    strategy.positions.append(Position('CE', 25000, 100, 1, 0, 'key1'))
    print(f"Added pos 1. Total lots: {sum(p.lot_size for p in strategy.positions)}")
    
    # 2. Add pyramid positions until cap
    # Make previous positions profitable so pyramiding is valid
    for p in strategy.positions: p.current_price = 50 # 50% profit
    
    can, reason = strategy.can_add_pyramid()
    print(f"Can add? {can} ({reason})")
    assert can == True
    strategy.positions.append(Position('CE', 25000, 100, 1, 1, 'key2')) # Total 2
    
    for p in strategy.positions: p.current_price = 50
    can, reason = strategy.can_add_pyramid()
    print(f"Can add? {can} ({reason})")
    assert can == True
    strategy.positions.append(Position('CE', 25000, 100, 1, 2, 'key3')) # Total 3
    
    for p in strategy.positions: p.current_price = 50
    can, reason = strategy.can_add_pyramid()
    print(f"Can add? {can} ({reason})")
    assert can == True
    strategy.positions.append(Position('CE', 25000, 100, 1, 3, 'key4')) # Total 4
    
    # 3. Try to add 5th lot (Should be blocked)
    print("Trying to add 5th lot (Cap is 4)...")
    for p in strategy.positions: p.current_price = 50
    can, reason = strategy.can_add_pyramid()
    print(f"Can add? {can} ({reason})")
    
    assert can == False
    assert "Maximum total lots (4) would be exceeded" in reason
    print("✅ Max Total Lots Cap test passed!")

if __name__ == "__main__":
    # Run existing tests (if any functions exist)
    try:
        from strategies.directional.futures_vwap_ema.verify_oi import test_oi_entry_filter
        test_oi_entry_filter()
    except ImportError:
        pass
        
    test_lot_cap()

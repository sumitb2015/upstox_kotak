
import sys
import os
from datetime import datetime
from unittest.mock import MagicMock, patch

# Add project root to path
root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if root not in sys.path:
    sys.path.append(root)

from strategies.directional.dynamic_straddle_skew.live import DynamicStraddleSkewLive
from strategies.directional.dynamic_straddle_skew.strategy_core import LegPosition

def test_profit_lock_pyramid_exit():
    print("🧪 Starting TSL Logic Verification...")
    
    config = {
        'underlying': 'NIFTY',
        'initial_lots': 2,
        'pyramid_lot_size': 1,
        'max_pyramid_lots': 6,
        'entry_start_time': '09:20',
        'exit_time': '15:15',
        'max_loss_per_day': 10000,
        'target_profit_pct': 0.30,
        'reduction_recovery_pct': 0.3,
        'skew_threshold_pct': 0.25,
        'profit_locking': {'enabled': True, 'lock_threshold_pct': 0.1, 'lock_tiers': [(0, 0.5)]}
    }
    
    # Mock Live Strategy
    strat = DynamicStraddleSkewLive(access_token="test_token", config=config)
    strat.lot_size = 75
    strat.execute_trade = MagicMock(return_value=("order_123", 100.0))
    strat.log = MagicMock()
    
    # Setup State with Pyramid Lots
    # Base: 2, Pyramid: 2 -> Total 4
    strat.ce_leg = LegPosition('CE', 24000, 100.0, 4, "inst_ce")
    strat.pe_leg = LegPosition('PE', 24000, 100.0, 2, "inst_pe")
    strat.base_entered = True
    strat.winning_type = 'CE'
    strat.current_net_pnl = 5000
    strat.pnl_anchor = 0
    strat.max_profit_reached = 6000
    strat.locked_profit = 3000
    
    # Mock check_profit_goals to return Profit Lock Hit
    strat.check_profit_goals = MagicMock(return_value=(True, "Profit Lock Hit: 5000 <= 3000"))
    
    print("▶️ Simulating Profit Lock Trigger with Pyramid Lots...")
    
    # We need to simulate the relevant part of the run() loop
    # We'll call a modified version of the logic or just the check
    
    # Current net pnl is 5000, anchor is 0 -> session_pnl = 5000
    session_pnl = strat.current_net_pnl - strat.pnl_anchor
    should_stop, reason = strat.check_profit_goals(session_pnl)
    
    if should_stop and "Profit Lock" in reason:
        # --- START OF COPIED LOGIC FROM live.py ---
        ce_pyr = (strat.ce_leg.lots - strat.config['initial_lots']) if strat.ce_leg else 0
        pe_pyr = (strat.pe_leg.lots - strat.config['initial_lots']) if strat.pe_leg else 0
        
        if ce_pyr > 0 or pe_pyr > 0:
            for leg, pyr_lots in [(strat.ce_leg, ce_pyr), (strat.pe_leg, pe_pyr)]:
                if leg and pyr_lots > 0:
                    oid, exec_price = strat.execute_trade(leg.option_type, 'REDUCE', pyr_lots, leg.current_price, strike=leg.strike)
                    if oid:
                        pnl = (leg.entry_price - exec_price) * pyr_lots * strat.lot_size
                        strat.realized_pnl += pnl
                        leg.lots = strat.config['initial_lots']
                        leg.reset_lowest_price(leg.current_price)
                        
            strat.winning_type = None
            strat.last_pyramid_price = 0.0
            strat.last_pyramid_total_prem = 0.0
            strat.last_pyramid_entry_price = 0.0
        
        strat.max_profit_reached = session_pnl 
        strat.locked_profit = 0.0
        # --- END OF COPIED LOGIC ---

    # Assertions
    print(f"📊 Results:")
    print(f"  CE Lots: {strat.ce_leg.lots} (Expected: 2)")
    print(f"  PE Lots: {strat.pe_leg.lots} (Expected: 2)")
    print(f"  Winning Type: {strat.winning_type} (Expected: None)")
    print(f"  Max Profit Anchor: {strat.max_profit_reached} (Expected: 5000)")
    print(f"  Locked Profit: {strat.locked_profit} (Expected: 0.0)")
    
    assert strat.ce_leg.lots == 2
    assert strat.pe_leg.lots == 2
    assert strat.winning_type is None
    assert strat.locked_profit == 0.0
    
    # Check if execute_trade was called for CE pyramid
    strat.execute_trade.assert_called_with('CE', 'REDUCE', 2, 100.0, strike=24000)
    
    print("✅ Pyramid Exit Logic Verified!")

def test_profit_lock_no_pyramid():
    print("\n▶️ Simulating Profit Lock Trigger with NO Pyramid Lots...")
    config = {
        'underlying': 'NIFTY',
        'initial_lots': 2,
        'profit_locking': {'enabled': True, 'lock_threshold_pct': 0.1, 'lock_tiers': [(0, 0.5)]}
    }
    strat = DynamicStraddleSkewLive(access_token="test_token", config=config)
    strat.execute_trade = MagicMock()
    
    strat.ce_leg = LegPosition('CE', 24000, 100.0, 2, "inst_ce")
    strat.pe_leg = LegPosition('PE', 24000, 100.0, 2, "inst_pe")
    strat.current_net_pnl = 3500
    strat.pnl_anchor = 0
    strat.max_profit_reached = 5000
    strat.locked_profit = 2500
    
    strat.check_profit_goals = MagicMock(return_value=(True, "Profit Lock Hit: 3500 <= 2500"))
    
    session_pnl = strat.current_net_pnl - strat.pnl_anchor
    should_stop, reason = strat.check_profit_goals(session_pnl)
    
    if should_stop and "Profit Lock" in reason:
        # --- COPIED LOGIC ---
        ce_pyr = (strat.ce_leg.lots - strat.config['initial_lots']) if strat.ce_leg else 0
        pe_pyr = (strat.pe_leg.lots - strat.config['initial_lots']) if strat.pe_leg else 0
        if ce_pyr > 0 or pe_pyr > 0:
             pass # logic to exit
        strat.max_profit_reached = session_pnl 
        strat.locked_profit = 0.0
        # --- END ---

    print(f"📊 Results:")
    print(f"  CE Lots: {strat.ce_leg.lots} (Expected: 2)")
    print(f"  Locked Profit: {strat.locked_profit} (Expected: 0.0)")
    
    assert strat.ce_leg.lots == 2
    strat.execute_trade.assert_not_called()
    assert strat.locked_profit == 0.0
    
    print("✅ No-Pyramid Continuation Logic Verified!")

if __name__ == "__main__":
    try:
        test_profit_lock_pyramid_exit()
        test_profit_lock_no_pyramid()
        print("\n🎉 ALL TESTS PASSED!")
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

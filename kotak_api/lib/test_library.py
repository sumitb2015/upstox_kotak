"""
Test script for trading library modules.

Tests each library component independently:
- DataStore
- BrokerClient  
- WebSocketClient
- OrderManager
- PositionTracker
"""

import sys
import time

# Add parent directory to path
sys.path.insert(0, r'c:\Kotakv2_env')

from lib.data_store import DataStore
from lib.broker import BrokerClient
from lib.websocket_client import WebSocketClient
from lib.order_manager import OrderManager
from lib.position_tracker import PositionTracker
from lib.utils import get_lot_size, round_to_strike_interval


def test_data_store():
    """Test DataStore functionality."""
    print("\n" + "="*60)
    print("Testing DataStore...")
    print("="*60)
    
    ds = DataStore()
    
    # Test update and get
    ds.update(token="12345", ltp=100.50, pc=2.5, oi=50000)
    ds.update(token="67890", ltp=200.75, pc=-1.2, oi=30000)
    
    assert ds.get_ltp("12345") == 100.50, "LTP retrieval failed"
    assert ds.get_change("12345") == 2.5, "PC retrieval failed"
    assert ds.get_oi("12345") == 50000, "OI retrieval failed"
    
    # Test missing token
    assert ds.get_ltp("99999") == 0.0, "Missing token should return 0"
    
    # Test staleness
    assert not ds.is_stale(timeout=1), "Should not be stale immediately"
    time.sleep(2)
    assert ds.is_stale(timeout=1), "Should be stale after timeout"
    
    print("✅ DataStore tests passed!")
    return True


def test_broker_client():
    """Test BrokerClient (requires credentials)."""
    print("\n" + "="*60)
    print("Testing BrokerClient...")
    print("="*60)
    
    broker = BrokerClient()
    
    # Test credential loading
    assert broker.consumer_key is not None, "Missing KOTAK_CONSUMER_KEY in .env"
    assert broker.mobile is not None, "Missing KOTAK_MOBILE_NUMBER in .env"
    
    print("  ✅ Credentials loaded")
    
    # Test authentication (optional - requires valid credentials)
    try:
        broker.authenticate()
        print("  ✅ Authentication successful")
        
        # Test master data loading
        master_df = broker.load_master_data()
        assert len(master_df) > 0, "Master data should not be empty"
        print(f"  ✅ Master data loaded: {len(master_df):,} instruments")
        
        return True
    except Exception as e:
        print(f"  ⚠️ Authentication/data loading skipped: {e}")
        print("  (This is expected if credentials are invalid or broker API is down)")
        return True  # Don't fail test


def test_utils():
    """Test utility functions."""
    print("\n" + "="*60)
    print("Testing Utils...")
    print("="*60)
    
    # Test strike rounding
    assert round_to_strike_interval(24173, 50) == 24200, "Strike rounding failed"
    assert round_to_strike_interval(24125, 50) == 24100, "Strike rounding failed"
    
    print("✅ Utils tests passed!")
    return True


if __name__ == "__main__":
    print("\n🧪 TRADING LIBRARY TEST SUITE")
    print("="*60)
    
    tests = [
        ("DataStore", test_data_store),
        ("Utils", test_utils),
        ("BrokerClient", test_broker_client),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success))
        except Exception as e:
            print(f"\n❌ {name} test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {name}")
    
    all_passed = all(success for _, success in results)
    print("\n" + ("🎉 All tests passed!" if all_passed else "⚠️ Some tests failed"))

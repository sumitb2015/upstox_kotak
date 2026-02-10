"""
Simple test to diagnose where the Kotak strategy initialization hangs
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Test 1: Import Kotak modules
def test_kotak_imports():
    """Test that Kotak modules can be imported."""
    print("\n[1/5] Testing Kotak imports...")
    try:
        from kotak_api.lib.broker import BrokerClient
        from kotak_api.lib.order_manager import OrderManager
        print("✅ Imports successful")
        return BrokerClient, OrderManager
    except Exception as e:
        print(f"❌ Import failed: {e}")
        import pytest
        pytest.fail(f"Import failed: {e}")

def test_broker_client_creation():
    """Test BrokerClient creation."""
    print("\n[2/5] Creating BrokerClient...")
    try:
        from kotak_api.lib.broker import BrokerClient
        broker = BrokerClient()
        print(f"✅ BrokerClient created")
        print(f"   Consumer Key: {broker.consumer_key[:10]}..." if broker.consumer_key else "   No consumer key")
        return broker
    except Exception as e:
        print(f"❌ BrokerClient creation failed: {e}")
        import pytest
        pytest.fail(f"BrokerClient creation failed: {e}")

def test_authentication():
    """Test Kotak authentication."""
    print("\n[3/5] Authenticating with Kotak Neo...")
    print("   (This step may take 10-15 seconds...)")
    try:
        from kotak_api.lib.broker import BrokerClient
        broker = BrokerClient()
        import signal
        
        def timeout_handler(signum, frame):
            raise TimeoutError("Authentication timeout!")
        
        # Set 30 second timeout (Windows doesn't support signal.alarm, so skip on Windows)
        if hasattr(signal, 'SIGALRM'):
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(30)
        
        broker.authenticate()
        
        if hasattr(signal, 'SIGALRM'):
            signal.alarm(0)  # Cancel alarm
        
        print("✅ Authentication successful")
        return broker
    except TimeoutError as e:
        print(f"❌ {e}")
        print("   Kotak authentication is hanging. Check:")
        print("   - Network connectivity")
        print("   - TOTP secret validity")
        print("   - Kotak API status")
        import pytest
        pytest.fail(f"Authentication timeout: {e}")
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        import traceback
        traceback.print_exc()
        import pytest
        pytest.fail(f"Authentication failed: {e}")

def test_load_master_data():
    """Test loading master data."""
    print("\n[4/5] Loading Master Data...")
    try:
        from kotak_api.lib.broker import BrokerClient
        broker = BrokerClient()
        broker.authenticate()
        broker.load_master_data()
        print(f"✅ Master data loaded: {len(broker.master_df)} instruments")
        return broker
    except Exception as e:
        print(f"❌ Master data loading failed: {e}")
        import pytest
        pytest.fail(f"Master data loading failed: {e}")

def test_order_manager_creation():
    """Test OrderManager creation."""
    print("\n[5/5] Creating OrderManager (Dry Run)...")
    try:
        from kotak_api.lib.broker import BrokerClient
        from kotak_api.lib.order_manager import OrderManager
        broker = BrokerClient()
        broker.authenticate()
        order_mgr = OrderManager(broker.client, dry_run=True)
        print("✅ OrderManager created")
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED - Kotak initialization works!")
        print("=" * 60)
        print("\nNext step: Test symbol resolution and order placement")
    except Exception as e:
        print(f"❌ OrderManager creation failed: {e}")
        import pytest
        pytest.fail(f"OrderManager creation failed: {e}")

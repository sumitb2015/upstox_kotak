
import os
import sys
import logging
import json

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from kotak_api.lib.broker import BrokerClient

logging.basicConfig(level=logging.INFO)

def debug_order(order_id):
    broker = BrokerClient()
    try:
        client = broker.authenticate()
        print(f"\nSearching for Order ID: {order_id}")
        
        # 1. Check History
        hist = client.order_history(order_id=str(order_id))
        print("\nORDER HISTORY:")
        print(json.dumps(hist, indent=2))
        
        # 2. Check Order Report for current status
        report = client.order_report()
        orders = report.get('data', []) if isinstance(report, dict) else report
        
        for ord in orders:
            if str(ord.get('nOrdNo')) == str(order_id):
                print("\nORDER REPORT ENTRY:")
                print(json.dumps(ord, indent=2))
                break
                
    except Exception as e:
        print(f"Debug failed: {e}")

if __name__ == "__main__":
    # Test with the last order ID from the user's log
    debug_order("260128000218480")

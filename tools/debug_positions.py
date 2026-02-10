
import os
import sys
import logging
import json

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from kotak_api.lib.broker import BrokerClient

logging.basicConfig(level=logging.INFO)

def check_raw_positions():
    broker = BrokerClient()
    try:
        client = broker.authenticate()
        print("\nFETCHING RAW POSITIONS...")
        pos_resp = client.positions()
        print(json.dumps(pos_resp, indent=2))
                
    except Exception as e:
        print(f"Debug failed: {e}")

if __name__ == "__main__":
    check_raw_positions()

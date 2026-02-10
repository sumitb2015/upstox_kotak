import os
from Kotak_Api.lib.broker import BrokerClient

def test_download():
    broker = BrokerClient()
    broker.authenticate()
    
    print("Testing broker.download_fresh_master()...")
    broker.download_fresh_master()
    
    # Check if files exist
    kotak_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'Kotak_Api'))
    print(f"Checking {kotak_dir}...")
    
    for f in ['nse_fo.csv', 'nse_cm.csv']:
        path = os.path.join(kotak_dir, f)
        if os.path.exists(path):
             print(f"✅ FOUND: {f} ({os.path.getsize(path)} bytes)")
        else:
             print(f"❌ MISSING: {f}")

if __name__ == "__main__":
    test_download()

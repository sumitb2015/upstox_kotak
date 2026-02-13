
import upstox_client
import sys
import os

sys.path.append(os.path.abspath("c:/algo/upstox"))

def inspect():
    print(f"DEBUG: Methods of ExpiredInstrumentApi: {dir(upstox_client.ExpiredInstrumentApi)}")

if __name__ == "__main__":
    inspect()

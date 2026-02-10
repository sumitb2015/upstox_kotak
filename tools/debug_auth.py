import sys
import os
import traceback

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.core.authentication import perform_authentication, save_access_token

def debug_auth():
    print("🛠️ Starting Auth Debugger...")
    print(f"Python Executable: {sys.executable}")
    print(f"CWD: {os.getcwd()}")
    
    try:
        token = perform_authentication()
        if token:
            print(f"✅ Authentication Successful! Token: {token[:10]}...")
            save_access_token(token)
        else:
            print("❌ Authentication returned None")
    except Exception:
        print("\n❌ Authentication Failed with Exception:")
        traceback.print_exc()

if __name__ == "__main__":
    debug_auth()

import sys
import os

# Add root to python path exactly as the notebook does
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.core.authentication import check_existing_token, get_access_token

print("Checking token...")
if check_existing_token():
    print("✅ Valid token found via check_existing_token()")
    token = get_access_token()
    if token:
        print(f"✅ Token retrieved successfully! Length: {len(token)}")
    else:
        print("❌ get_access_token returned None despite check_existing_token returning True")
else:
    print("⚠️ No valid token found (or expired). Authentication would be triggered.")
    # We don't trigger auth here to avoid popping up browsers or 2FA prompts in this verification script
    # unless we want to test that too.
    # But checking if env vars are loaded is key.
    
    import lib.core.authentication as auth
    print(f"Checking loaded env vars in module...")
    # Access private variables if possible or just check via os.getenv
    # Since load_dotenv was called at module level, os.getenv should work now
    
    client_id = os.getenv("client_id")
    print(f"Client ID present: {bool(client_id)}")
    if client_id:
        print(f"Client ID starts with: {client_id[:4]}...")

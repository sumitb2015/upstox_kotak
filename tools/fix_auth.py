#!/usr/bin/env python3
"""
Quick Authentication Fix Script
Run this to diagnose and fix 401 Unauthorized errors
"""

import os
import requests
from datetime import datetime

def main():
    print("🔧 Quick Authentication Fix")
    print("="*40)
    
    # Step 1: Check if token file exists
    token_file = "lib/core/accessToken.txt"
    if not os.path.exists(token_file):
        print("❌ No access token file found")
        print("🔑 Need to authenticate first...")
        try:
            from authentication import perform_authentication
            token = perform_authentication()
            if token:
                print("✅ Authentication successful!")
                return
            else:
                print("❌ Authentication failed")
                return
        except Exception as e:
            print(f"❌ Error during authentication: {e}")
            return
    
    # Step 2: Check token file age
    file_mtime = datetime.fromtimestamp(os.path.getmtime(token_file))
    age_hours = (datetime.now() - file_mtime).total_seconds() / 3600
    print(f"📁 Token file age: {age_hours:.1f} hours")
    
    # Step 3: Read and validate token
    with open(token_file, "r") as file:
        token = file.read().strip()
    
    if len(token) < 20:
        print("❌ Token appears invalid (too short)")
        print("🔑 Re-authenticating...")
        os.remove(token_file)
        try:
            from authentication import perform_authentication
            new_token = perform_authentication()
            if new_token:
                print("✅ Re-authentication successful!")
                return
        except Exception as e:
            print(f"❌ Re-authentication failed: {e}")
            return
    
    # Step 4: Test current token with API
    print(f"🔍 Testing token: {token[:10]}...")
    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }
        
        response = requests.get(
            "https://api.upstox.com/v3/market-quote/ltp?instrument_key=NSE_INDEX|Nifty 50",
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            print("✅ Token is working correctly!")
            print("🎉 Authentication is OK - you can run your strategy now")
            return
        elif response.status_code == 401:
            print("❌ Token is invalid/expired (401 Unauthorized)")
            print("🔑 Re-authenticating...")
            os.remove(token_file)
            try:
                from authentication import perform_authentication
                new_token = perform_authentication()
                if new_token:
                    print("✅ Re-authentication successful!")
                    return
            except Exception as e:
                print(f"❌ Re-authentication failed: {e}")
                return
        else:
            print(f"⚠️ API returned status: {response.status_code}")
            print(f"Response: {response.text[:200]}...")
            return
            
    except requests.RequestException as e:
        print(f"❌ Network error: {e}")
        return
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return

if __name__ == "__main__":
    main()

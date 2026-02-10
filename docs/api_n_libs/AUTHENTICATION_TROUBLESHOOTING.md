# Authentication Troubleshooting Guide

## 401 Unauthorized Error - Access Token Issues

### Error Description
```
Error getting LTP quote: 401 Client Error: Unauthorized for url: https://api.upstox.com/v3/market-quote/ltp?instrument_key=NSE_INDEX%7CNifty%2050
```

This error indicates that the Upstox API is rejecting the access token due to authentication issues.

---

## Common Causes and Solutions

### 1. **Expired Access Token**
**Cause**: Access tokens have a limited lifespan and expire after a certain period.

**Solution**:
```python
# Check if token file exists and is recent
import os
from datetime import datetime

access_token_file = "accessToken.txt"
if os.path.exists(access_token_file):
    file_mtime = datetime.fromtimestamp(os.path.getmtime(access_token_file))
    print(f"Token file last modified: {file_mtime}")
    
    # If token is older than 1 day, re-authenticate
    if (datetime.now() - file_mtime).days > 0:
        print("Token may be expired. Re-authenticating...")
        # Delete old token file
        os.remove(access_token_file)
        # Re-authenticate
        from authentication import perform_authentication
        new_token = perform_authentication()
```

### 2. **Invalid Access Token**
**Cause**: The token in the file is corrupted or invalid.

**Solution**:
```python
# Check token format
with open("accessToken.txt", "r") as file:
    token = file.read().strip()
    
if len(token) < 20:  # Upstox tokens are typically longer
    print("Token appears to be invalid. Re-authenticating...")
    # Delete and re-authenticate
    os.remove("accessToken.txt")
    from authentication import perform_authentication
    new_token = perform_authentication()
```

### 3. **Missing or Incorrect Environment Variables**
**Cause**: Required environment variables are not set.

**Solution**:
```python
import os

# Check required environment variables
required_vars = ["client_id", "client_secret", "redirect_uri"]
missing_vars = []

for var in required_vars:
    if not os.getenv(var):
        missing_vars.append(var)

if missing_vars:
    print(f"Missing environment variables: {missing_vars}")
    print("Please set the following environment variables:")
    print("export client_id='your_client_id'")
    print("export client_secret='your_client_secret'")
    print("export redirect_uri='your_redirect_uri'")
```

### 4. **API Key Issues**
**Cause**: The client_id or client_secret is incorrect.

**Solution**:
```python
# Verify API credentials
api_key = os.getenv("client_id")
api_secret = os.getenv("client_secret")

if not api_key or not api_secret:
    print("API credentials not found in environment variables")
    print("Please check your .env file or environment variables")
else:
    print(f"API Key: {api_key[:10]}...")
    print(f"API Secret: {api_secret[:10]}...")
```

### 5. **Network or API Issues**
**Cause**: Temporary network issues or API downtime.

**Solution**:
```python
import requests
import time

def test_api_connectivity():
    """Test basic API connectivity"""
    try:
        # Test with a simple API call
        response = requests.get("https://api.upstox.com/v3/market-quote/ltp?instrument_key=NSE_INDEX|Nifty 50", 
                              headers={"Authorization": f"Bearer {access_token}"})
        
        if response.status_code == 401:
            print("Authentication failed - token issue")
            return False
        elif response.status_code == 200:
            print("API connectivity OK")
            return True
        else:
            print(f"API returned status: {response.status_code}")
            return False
            
    except requests.RequestException as e:
        print(f"Network error: {e}")
        return False

# Test connectivity
test_api_connectivity()
```

---

## Step-by-Step Troubleshooting Process

### Step 1: Check Token File
```python
import os
from datetime import datetime

def check_token_file():
    token_file = "accessToken.txt"
    
    if not os.path.exists(token_file):
        print("❌ No access token file found")
        return False
    
    # Check file age
    file_mtime = datetime.fromtimestamp(os.path.getmtime(token_file))
    age_hours = (datetime.now() - file_mtime).total_seconds() / 3600
    
    print(f"📁 Token file age: {age_hours:.1f} hours")
    
    if age_hours > 24:
        print("⚠️ Token file is older than 24 hours - may be expired")
        return False
    
    # Check token content
    with open(token_file, "r") as file:
        token = file.read().strip()
    
    if len(token) < 20:
        print("❌ Token appears to be invalid (too short)")
        return False
    
    print(f"✅ Token file looks valid: {token[:10]}...")
    return True

check_token_file()
```

### Step 2: Test API Authentication
```python
def test_authentication():
    """Test if the current token works with API"""
    try:
        with open("accessToken.txt", "r") as file:
            token = file.read().strip()
        
        # Test with a simple API call
        import requests
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }
        
        response = requests.get(
            "https://api.upstox.com/v3/market-quote/ltp?instrument_key=NSE_INDEX|Nifty 50",
            headers=headers
        )
        
        if response.status_code == 200:
            print("✅ Authentication successful")
            return True
        elif response.status_code == 401:
            print("❌ Authentication failed - token invalid/expired")
            return False
        else:
            print(f"⚠️ API returned status: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing authentication: {e}")
        return False

test_authentication()
```

### Step 3: Re-authenticate if Needed
```python
def re_authenticate():
    """Perform fresh authentication"""
    try:
        # Remove old token file
        if os.path.exists("accessToken.txt"):
            os.remove("accessToken.txt")
            print("🗑️ Removed old token file")
        
        # Perform fresh authentication
        from authentication import perform_authentication
        new_token = perform_authentication()
        
        if new_token:
            print("✅ Fresh authentication successful")
            return new_token
        else:
            print("❌ Authentication failed")
            return None
            
    except Exception as e:
        print(f"❌ Error during re-authentication: {e}")
        return None

# Re-authenticate if needed
new_token = re_authenticate()
```

### Step 4: Verify Environment Variables
```python
def check_environment():
    """Check if all required environment variables are set"""
    required_vars = {
        "client_id": "Your Upstox API client ID",
        "client_secret": "Your Upstox API client secret", 
        "redirect_uri": "Your redirect URI (usually http://localhost:8080)"
    }
    
    missing = []
    for var, description in required_vars.items():
        value = os.getenv(var)
        if not value:
            missing.append(f"{var}: {description}")
        else:
            print(f"✅ {var}: {value[:10]}...")
    
    if missing:
        print("\n❌ Missing environment variables:")
        for var in missing:
            print(f"   {var}")
        print("\nPlease set these in your .env file or environment")
        return False
    
    print("✅ All environment variables are set")
    return True

check_environment()
```

---

## Complete Troubleshooting Script

```python
#!/usr/bin/env python3
"""
Complete Authentication Troubleshooting Script
"""

import os
import requests
from datetime import datetime

def troubleshoot_authentication():
    """Complete authentication troubleshooting process"""
    print("🔍 Starting Authentication Troubleshooting")
    print("="*50)
    
    # Step 1: Check environment variables
    print("\n1️⃣ Checking Environment Variables...")
    if not check_environment():
        return False
    
    # Step 2: Check token file
    print("\n2️⃣ Checking Token File...")
    if not check_token_file():
        print("Token file issues detected")
    
    # Step 3: Test authentication
    print("\n3️⃣ Testing API Authentication...")
    if not test_authentication():
        print("Authentication failed - attempting re-authentication...")
        
        # Step 4: Re-authenticate
        print("\n4️⃣ Re-authenticating...")
        new_token = re_authenticate()
        
        if new_token:
            # Step 5: Test new token
            print("\n5️⃣ Testing New Token...")
            if test_authentication():
                print("✅ Authentication troubleshooting completed successfully!")
                return True
            else:
                print("❌ New token also failed")
                return False
        else:
            print("❌ Re-authentication failed")
            return False
    else:
        print("✅ Authentication is working correctly!")
        return True

def check_environment():
    """Check environment variables"""
    required_vars = ["client_id", "client_secret", "redirect_uri"]
    missing = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing.append(var)
        else:
            print(f"✅ {var}: Set")
    
    if missing:
        print(f"❌ Missing: {missing}")
        return False
    return True

def check_token_file():
    """Check token file validity"""
    token_file = "accessToken.txt"
    
    if not os.path.exists(token_file):
        print("❌ No token file found")
        return False
    
    # Check age
    file_mtime = datetime.fromtimestamp(os.path.getmtime(token_file))
    age_hours = (datetime.now() - file_mtime).total_seconds() / 3600
    print(f"📁 Token age: {age_hours:.1f} hours")
    
    # Check content
    with open(token_file, "r") as file:
        token = file.read().strip()
    
    if len(token) < 20:
        print("❌ Token too short")
        return False
    
    print(f"✅ Token: {token[:10]}...")
    return True

def test_authentication():
    """Test current token with API"""
    try:
        with open("accessToken.txt", "r") as file:
            token = file.read().strip()
        
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
            print("✅ API call successful")
            return True
        elif response.status_code == 401:
            print("❌ 401 Unauthorized - token invalid/expired")
            return False
        else:
            print(f"⚠️ API status: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def re_authenticate():
    """Perform fresh authentication"""
    try:
        # Remove old token
        if os.path.exists("accessToken.txt"):
            os.remove("accessToken.txt")
            print("🗑️ Removed old token")
        
        # Fresh authentication
        from authentication import perform_authentication
        new_token = perform_authentication()
        
        if new_token:
            print("✅ New token obtained")
            return new_token
        else:
            print("❌ Authentication failed")
            return None
            
    except Exception as e:
        print(f"❌ Re-auth error: {e}")
        return None

if __name__ == "__main__":
    success = troubleshoot_authentication()
    if success:
        print("\n🎉 Authentication is working! You can now run your strategy.")
    else:
        print("\n💥 Authentication issues remain. Please check your API credentials.")
```

---

## Quick Fix Commands

### 1. **Delete and Re-authenticate**
```bash
# Remove old token file
rm accessToken.txt

# Run authentication
python -c "from authentication import perform_authentication; perform_authentication()"
```

### 2. **Check Environment Variables**
```bash
# Check if variables are set
echo $client_id
echo $client_secret
echo $redirect_uri

# Set variables if missing
export client_id="your_client_id"
export client_secret="your_client_secret"
export redirect_uri="http://localhost:8080"
```

### 3. **Test API Connection**
```python
# Quick API test
python -c "
import requests
with open('accessToken.txt', 'r') as f:
    token = f.read().strip()
response = requests.get('https://api.upstox.com/v3/market-quote/ltp?instrument_key=NSE_INDEX|Nifty 50', 
                       headers={'Authorization': f'Bearer {token}'})
print(f'Status: {response.status_code}')
"
```

---

## Prevention Tips

1. **Regular Token Refresh**: Set up automatic token refresh
2. **Environment Variables**: Use .env files for credentials
3. **Error Handling**: Implement proper error handling in your code
4. **Logging**: Add logging to track authentication issues
5. **Monitoring**: Monitor API response codes

---

*This guide should help you resolve the 401 Unauthorized error and get your authentication working properly.*

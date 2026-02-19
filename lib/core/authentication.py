import requests as rq
import time
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
import urllib.parse as urlparse
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from pyotp import TOTP
import traceback
from selenium.webdriver.common.keys import Keys

# Load environment variables
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, ".env")
load_dotenv(env_path)


def check_existing_token():
    """Check if access token file exists and contains a valid token"""
    access_token_file = os.path.join(current_dir, "accessToken.txt")
    if os.path.exists(access_token_file):
        # Check if file was modified today or not
        file_mtime = datetime.fromtimestamp(os.path.getmtime(access_token_file))
        today = datetime.now().date()
        current_time = datetime.now()
        
        print(f"Access token file last modified: {file_mtime.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Current time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Today's date: {today}")
        
        if file_mtime.date() < today:
            print(f"Access token file is from {file_mtime.strftime('%Y-%m-%d')} (not from today). Proceeding with login...")
            return False

        # Additional check: If token is from before 7:00 AM and now is after 7:00 AM, force refresh
        # This prevents using stale tokens generated at midnight/early morning
        if current_time.hour >= 7 and file_mtime.hour < 7:
             print(f"Access token is from {file_mtime.strftime('%H:%M')} (pre-market). Forcing refresh for trading session.")
             return False
        
        with open(access_token_file, "r") as file:
            existing_token = file.read().strip()
        if existing_token and len(existing_token) > 10:  # Basic validation
            print(f"Access token already exists: {existing_token[:10]}...")
            print("Skipping login process. Using existing token.")
            return True
        else:
            print("Access token file exists but is empty or invalid. Proceeding with login...")
            return False
    else:
        print("❌ No access token found. Proceeding with login...")
        return False

def save_access_token(token):
    """Save access token to file"""
    access_token_file = os.path.join(current_dir, "accessToken.txt")
    with open(access_token_file, "w") as file:
        file.write(token)
    print(f"Access token saved to {access_token_file}")
    print(f"Access Token: {token}")


def validate_token(token):
    """Validate token by making a lightweight API call"""
    try:
        url = "https://api-v2.upstox.com/user/profile"
        headers = {
            'Accept': 'application/json',
            'Authorization': f'Bearer {token}',
            'Api-Version': '2.0'
        }
        response = rq.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            print("✅ Token validated successfully via API.")
            return True
        
        print(f"⚠️ Token validation failed. Status: {response.status_code}")
        try:
            err_json = response.json()
            print(f"   Response: {err_json}")
        except:
            print(f"   Response: {response.text[:100]}")
            
        return False
    except Exception as e:
        print(f"❌ Token validation error: {e}")
        return False

def get_access_token(auto_refresh=True):
    """
    Read access token from file, validate it, and auto-refresh if needed.
    """
    access_token_file = os.path.join(current_dir, "accessToken.txt")
    token = None
    
    # 1. Try to read from file
    if check_existing_token():
        with open(access_token_file, "r") as file:
            token = file.read().strip()
            
    # 2. Try Env Var
    if not token:
        token = os.getenv("UPSTOX_ACCESS_TOKEN")
        
    if token and validate_token(token):
        return token
        
    if not auto_refresh:
        return None
        
    # 4. Refresh if Invalid
    print("🔄 Token is missing or invalid. Triggering auto-refresh...")
    
    # Remove old file if it was explicitly tried and failed
    if token and os.path.exists(access_token_file):
        try:
            print(f"🧹 Removing invalid token file: {access_token_file}")
            os.remove(access_token_file)
        except Exception as e:
            print(f"⚠️ Failed to remove stale token file: {e}")
            
    try:
        new_token = perform_authentication()
        if new_token:
            save_access_token(new_token)
            return new_token
    except Exception as e:
        print(f"❌ Auto-refresh failed: {e}")
        traceback.print_exc()
        
    return None


def perform_authentication():
    """Perform Upstox authentication and return access token"""
    print("Starting authentication process...")
    
    # Get environment variables
    api_key = os.getenv("client_id")
    secret_key = os.getenv("client_secret")
    ruri = os.getenv("ruri")
    
    if not all([api_key, secret_key, ruri]):
        raise ValueError("Missing required environment variables. Please check your .env file.")
    
    # Get Credentials from .env
    mobile_no = os.getenv("mobile_no")
    totp_key = os.getenv("totp_key")
    pin = os.getenv("pin")
    
    if not all([mobile_no, pin]):
        raise ValueError("Missing mobile_no or pin in .env file.")

    # Generate or fetch OTP
    if totp_key and totp_key != "YOUR_TOTP_KEY_HERE":
        try:
            current_otp = TOTP(totp_key).now()
            print("Successfully generated dynamic TOTP.")
        except Exception as e:
            print(f"Error generating TOTP: {e}. Falling back to default.")
            current_otp = os.getenv("otp", "647243")
    else:
        current_otp = os.getenv("otp", "647243")
    
    print("Using OTP:", current_otp)
    
    # Selenium setup
    options = webdriver.ChromeOptions()
    # options.add_argument("--no-sandbox")
    # options.add_argument('--headless')  # uncomment if you want headless
    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 10)
    
    try:
        # Navigate to Upstox login
        auth_url = f"https://api-v2.upstox.com/login/authorization/dialog?response_type=code&client_id={api_key}&redirect_uri={ruri}"
        driver.get(auth_url)
        
        # Enter mobile number and request OTP
        mobile_field = wait.until(
            EC.presence_of_element_located((By.XPATH, '//input[@type="text"]'))
        )
        mobile_field.clear()
        mobile_field.send_keys(mobile_no)
        
        get_otp_btn = wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="getOtp"]')))
        driver.execute_script("arguments[0].click();", get_otp_btn)
        
        # Wait a little and enter TOTP
        time.sleep(2)
        otp_field = wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="otpNum"]')))
        otp_field.clear()
        otp_field.send_keys(current_otp)
        
        continue_btn = wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="continueBtn"]')))
        driver.execute_script("arguments[0].click();", continue_btn)
        
        # Enter PIN
        time.sleep(2)
        pin_field = wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="pinCode"]')))
        pin_field.clear()
        pin_field.send_keys(pin)
        
        pin_btn = wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="pinContinueBtn"]')))
        driver.execute_script("arguments[0].click();", pin_btn)
        
        # Extract authorization code from URL
        time.sleep(2)
        token_url = driver.current_url
        
        parsed = urlparse.urlparse(token_url)
        code = urlparse.parse_qs(parsed.query).get("code")
        if not code:
            raise ValueError("Authorization code not found in URL")
        code = code[0]
        
        # Exchange code for access token
        token_url = "https://api-v2.upstox.com/login/authorization/token"
        headers = {
            "accept": "application/json",
            "Api-Version": "2.0",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        
        data = {
            "code": code,
            "client_id": api_key,
            "client_secret": secret_key,
            "redirect_uri": ruri,
            "grant_type": "authorization_code",
        }
        
        response = rq.post(token_url, headers=headers, data=data)
        jsr = response.json()
        
        # Extract and return access token
        access_token = jsr.get("access_token")
        if not access_token:
            raise ValueError(f"Failed to retrieve access token: {jsr}")
        
        return access_token
        
    finally:
        driver.quit()


if __name__ == "__main__":
    """Run authentication when script is executed directly"""
    if check_existing_token():
        print("✅ Valid token already exists. No need to re-authenticate.")
    else:
        print("🔐 Starting authentication process...")
        try:
            access_token = perform_authentication()
            save_access_token(access_token)
            print("✅ Authentication successful!")
        except Exception as e:
            print(f"❌ Authentication failed: {e}")
            import traceback
            traceback.print_exc()

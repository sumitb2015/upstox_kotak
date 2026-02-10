import sys
import os
import traceback
import time
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from pyotp import TOTP
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load env manually to ensure we have them
current_dir = os.path.dirname(os.path.abspath(__file__))
# Assuming this script is in tools/, env is in lib/core/.env?
# Actually script is in tools/. Parent is upstox. lib/core/.env is in upstox/lib/core
env_path = os.path.join(os.path.dirname(current_dir), 'lib', 'core', '.env')
load_dotenv(env_path)

def perform_auth_debug():
    print("Starting authentication process (DEBUG MODE)...")
    
    api_key = os.getenv("client_id")
    ruri = os.getenv("ruri")
    mobile_no = os.getenv("mobile_no")
    totp_key = os.getenv("totp_key")
    pin = os.getenv("pin")
    
    print(f"Mobile: {mobile_no}")
    print(f"PIN: {pin}")
    
    current_otp = TOTP(totp_key).now()
    print(f"Generated OTP: {current_otp}")

    options = webdriver.ChromeOptions()
    # options.add_argument('--headless') 
    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 15) # Increased timeout
    
    try:
        auth_url = f"https://api-v2.upstox.com/login/authorization/dialog?response_type=code&client_id={api_key}&redirect_uri={ruri}"
        driver.get(auth_url)
        print("Navigated to auth URL")
        
        # Mobile
        print("Waiting for mobile input...")
        wait.until(EC.presence_of_element_located((By.XPATH, '//input[@type="text"]'))).send_keys(mobile_no)
        wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="getOtp"]'))).click()
        print("Clicked Get OTP")
        
        # OTP
        time.sleep(2)
        print("Waiting for OTP input...")
        wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="otpNum"]'))).send_keys(current_otp)
        wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="continueBtn"]'))).click()
        print(f"Entered OTP {current_otp} and clicked Continue")
        
        # PIN
        time.sleep(2)
        print("Waiting for PIN input...")
        # This is where it failed before
        wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="pinCode"]'))).send_keys(pin)
        wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="pinContinueBtn"]'))).click()
        print("Entered PIN and clicked Continue")
        
        print("Success! (Stopping here for debug)")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        traceback.print_exc()
        
        # Capture Page Source
        with open("auth_error_page.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        print("Saved auth_error_page.html")
        
        # Capture text specific to errors
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text
            print("--- BODY TEXT ---")
            print(body_text)
            print("-----------------")
        except:
            pass

    finally:
        driver.quit()

if __name__ == "__main__":
    perform_auth_debug()

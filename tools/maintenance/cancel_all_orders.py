"""
Script to cancel all open orders.
"""
from lib.core.authentication import check_existing_token, perform_authentication, save_access_token
from lib.api.order_management import cancel_all_orders
from lib.core.config import Config

def main():
    print("🚀 Starting cancellation of all open orders...")
    
    # Enable verbose for cancellation details
    Config.set_verbose(True)
    
    # Step 1: Authentication
    try:
        if check_existing_token():
            print("✅ Using existing access token")
            with open("lib/core/accessToken.txt", "r") as file:
                access_token = file.read().strip()
        else:
            print("🔄 Performing new authentication...")
            access_token = perform_authentication()
            save_access_token(access_token)
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        return

    # Step 2: Cancel Orders
    print("\n🗑️  Cancelling all open orders...")
    results = cancel_all_orders(access_token)
    
    if not results:
        print("\n✅ No open orders found or cancellation process completed empty.")
    else:
        print(f"\n✅ Completed cancellation process for {len(results)} orders.")

if __name__ == "__main__":
    main()

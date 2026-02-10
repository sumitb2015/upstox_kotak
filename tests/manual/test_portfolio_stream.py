from lib.api.streaming import UpstoxStreamer
import time

def test_portfolio_stream():
    # Load access token
    try:
        with open("lib/core/accessToken.txt", "r") as file:
            access_token = file.read().strip()
    except FileNotFoundError:
        print("Access token file not found. Run authentication first.")
        return

    # Initialize Streamer
    streamer = UpstoxStreamer(access_token)

    # Define callbacks
    def on_order_update(order):
        print(f"\n📦 ORDER UPDATE:")
        print(f"   Order ID: {order.get('order_id')}")
        print(f"   Status: {order.get('status')}")
        print(f"   Symbol: {order.get('trading_symbol')}")
        print(f"   Type: {order.get('transaction_type')}")
        print(f"   Qty: {order.get('filled_quantity')}/{order.get('quantity')}")
        print(f"   Avg Price: ₹{order.get('average_price', 0):.2f}")

    def on_position_update(position):
        print(f"\n📊 POSITION UPDATE:")
        print(f"   Symbol: {position.get('trading_symbol')}")
        print(f"   Qty: {position.get('quantity')}")
        print(f"   Avg Price: ₹{position.get('average_price', 0):.2f}")
        print(f"   P&L: ₹{position.get('pnl', 0):.2f}")

    # Connect to portfolio stream
    streamer.connect_portfolio(
        order_update=True,
        position_update=True,
        holding_update=False,
        gtt_update=False,
        on_order=on_order_update,
        on_position=on_position_update
    )

    print("--- Streaming portfolio updates for 30 seconds ---")
    print("Place an order from the Upstox app to see live updates...")
    time.sleep(30)

    # Clean up
    streamer.disconnect_all()
    print("\nTest completed.")

if __name__ == "__main__":
    test_portfolio_stream()

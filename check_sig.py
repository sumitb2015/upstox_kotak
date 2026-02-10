import upstox_client
import inspect

try:
    sig = inspect.signature(upstox_client.MarketQuoteApi.get_full_market_quote)
    print(f"Signature: {sig}")
except Exception as e:
    print(f"Error getting signature: {e}")

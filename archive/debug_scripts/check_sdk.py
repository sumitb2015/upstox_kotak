import upstox_client
import inspect

print("SDK Version:", getattr(upstox_client, "__version__", "Unknown"))
print("\nAvailable APIs:")
for name, obj in inspect.getmembers(upstox_client):
    if name.endswith('Api') and inspect.isclass(obj):
        print(f"- {name}")

print("\nOrderApi Methods:")
try:
    for name, _ in inspect.getmembers(upstox_client.OrderApi):
        if not name.startswith('_'):
            print(f"- {name}")
except AttributeError:
    print("OrderApi not found")

print("\nMarketQuoteApi Methods:")
try:
    for name, _ in inspect.getmembers(upstox_client.MarketQuoteApi):
        if not name.startswith('_'):
            print(f"- {name}")
except AttributeError:
    print("MarketQuoteApi not found")

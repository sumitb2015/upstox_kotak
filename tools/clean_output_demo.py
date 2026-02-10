#!/usr/bin/env python3
"""
Demo script showing the clean output format for the trading strategy
"""

def demo_clean_output():
    """Demonstrate the clean single-line output format"""
    print("=" * 80)
    print("CLEAN TRADING STRATEGY OUTPUT DEMO")
    print("=" * 80)
    print()
    print("Instead of verbose output like:")
    print("🎯 STRANGLE: Checking entry opportunities...")
    print("Spot price: 25188.05, ATM strike: 25200")
    print("💰 SAFE OTM: Checking opportunities...")
    print("Spot price: 25187.65, ATM strike: 25200")
    print("✅ Option chain API is working")
    print("🔍 Checking 5 active positions for ratio violations...")
    print("   Checking strike 25150: CE=False, PE=False")
    print("   Checking strike 25200: CE=False, PE=False")
    print("   ✅ Found active straddle: CE at 25300, PE at 25100")
    print("   📊 Active straddle prices: CE(25300)=₹6.8, PE(25100)=₹5.9")
    print("   🔑 Instrument keys: CE=NSE_FO|47761, PE=NSE_FO|47754")
    print("   ⚖️  Active straddle ratio: 0.868 (threshold: 0.40)")
    print()
    print("You now get clean single-line output:")
    print("[12:50:23] 25300₹6.7 25100₹5.8 R:0.87 P&L:₹-668 T:₹3000 N:₹25189")
    print("[12:50:42] 25300₹6.9 25100₹6.1 R:0.88 P&L:₹-675 T:₹3000 N:₹25191")
    print()
    print("Format: [Time] CE_Strike₹Price PE_Strike₹Price R:Ratio P&L:₹Amount T:₹Target N:₹NIFTY")
    print()
    print("Key Benefits:")
    print("✅ Single line per update - easy to read")
    print("✅ Essential information only")
    print("✅ No verbose debug messages")
    print("✅ Clean console output")
    print("✅ Easy to parse and log")
    print()
    print("To enable clean output, run:")
    print("python main.py")
    print()
    print("To enable verbose output (for debugging), modify main.py:")
    print("run_short_straddle_strategy(access_token, nse_data, verbose=True)")
    print("=" * 80)

if __name__ == "__main__":
    demo_clean_output()

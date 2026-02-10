"""
Strategy configuration and display utilities
"""


def display_strategy_configuration():
    """Display comprehensive strategy configuration"""
    print("\n" + "="*50)
    print("STRATEGY CONFIGURATION")
    print("="*50)
    print("🎯 Strategy: Intraday Short Straddle")
    print("📊 Underlying: NIFTY")
    print("📦 Lot Size: 1 lot")
    print("💰 Profit Target: ₹3000")
    print("⚖️  Ratio Threshold: 0.6")
    print("🔄 Management: Square off losing side when ratio < 0.6")
    print("📏 Strike Movement: 1 strike (50 points)")
    print("⏱️  Duration: Until market close (3:15 PM)")
    print("🔄 Check Interval: 5 seconds")
    print("🛡️  Risk Management: Automatic position adjustment")

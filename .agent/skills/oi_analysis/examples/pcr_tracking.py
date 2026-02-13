
"""
Example: Tracking Strike-Wise PCR using CumulativeOIAnalyzer
"""
import sys
import os

# Add project root to path (adjusted for where this script might be run from)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../')))

from lib.core.authentication import get_access_token
from lib.oi_analysis.cumulative_oi_analysis import CumulativeOIAnalyzer

def track_pcr():
    token = get_access_token()
    if not token:
        print("❌ No token available")
        return

    analyzer = CumulativeOIAnalyzer(token)
    
    # Get PCR structure for +/- 500 points
    print("📊 Fetching PCR Data (Offset 500)...")
    data = analyzer.get_strike_pcr_structure(offset=500)
    
    if "error" in data:
        print(f"❌ Error: {data['error']}")
        return

    atm = data['atm']
    print(f"📍 ATM Strike: {atm}")
    
    print(f"\n{'Strike':<10} | {'PCR':<6} | {'Sentiment':<10}")
    print("-" * 35)
    
    # Iterate through detailed list
    for item in data['details']:
        strike = item['strike']
        pcr = item['pcr']
        
        sentiment = "Neutral"
        if pcr > 1.2: sentiment = "Bullish"
        elif pcr < 0.8: sentiment = "Bearish"
        
        # Highlight ATM
        prefix = "👉" if strike == atm else "  "
        print(f"{prefix} {strike:<8} | {pcr:<6.2f} | {sentiment:<10}")

if __name__ == "__main__":
    track_pcr()

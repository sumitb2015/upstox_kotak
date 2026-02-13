import sys
import os

# Add skill script to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.cpr_utils import calculate_cpr

def main():
    # Example: Previous Day OHLC for Nifty
    pdh = 24500.50
    pdl = 24320.10
    pdc = 24450.75
    
    levels = calculate_cpr(pdh, pdl, pdc)
    
    print("-" * 30)
    print("🚀 NIFTY DAILY CPR LEVELS")
    print("-" * 30)
    print(f"Top Central (TC):  {levels['TC']}")
    print(f"Pivot (P):         {levels['P']}")
    print(f"Bottom Central (BC):{levels['BC']}")
    print("-" * 30)
    print(f"Resistance 1:      {levels['R1']}")
    print(f"Support 1:         {levels['S1']}")
    print("-" * 30)
    
    # Interpretation
    range_width = levels['CPR_TOP'] - levels['CPR_BOTTOM']
    print(f"CPR Width: {range_width:.2f} points")
    if range_width < 30:
        print("💡 Status: Narrow CPR - Potential Breakout Day!")
    elif range_width > 100:
        print("💡 Status: Wide CPR - Potentially Sideways Day.")

if __name__ == "__main__":
    main()

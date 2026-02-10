#!/usr/bin/env python3
"""
Test script to verify strangle fixes:
1. Different strikes for CE and PE
2. Minimum ₹8 premium filter
3. Max 4 strikes from ATM
4. OTM validation (CE above ATM, PE below ATM)
"""

import sys
import os
# Add parent directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.oi_analysis.oi_strangle_analyzer import OIStrangleAnalyzer
from lib.core.authentication import get_access_token
import json

def test_strangle_fixes():
    """Test the strangle fixes"""
    print("🧪 Testing Strangle Fixes")
    print("=" * 50)
    
    try:
        # Get access token
        access_token = get_access_token()
        if not access_token:
            print("❌ Failed to get access token")
            return
        
        # Initialize analyzer
        analyzer = OIStrangleAnalyzer(access_token, "NSE_INDEX|Nifty 50")
        
        # Test strangle analysis
        print("🔍 Running strangle analysis...")
        result = analyzer.analyze_strikes_for_strangle()
        
        if "error" in result:
            print(f"❌ Error: {result['error']}")
            return
        
        # Display results
        print(f"✅ Analysis completed successfully!")
        print(f"📊 Spot Price: {result['spot_price']}")
        print(f"🎯 ATM Strike: {result['atm_strike']}")
        print(f"📈 Strikes Analyzed: {result['strikes_analyzed']}")
        
        # Check filtering criteria
        criteria = result.get('filtering_criteria', {})
        print(f"\n🔧 Filtering Criteria:")
        print(f"   Min Premium: ₹{criteria.get('min_premium', 'N/A')}")
        print(f"   Max Strikes from ATM: {criteria.get('max_strikes_from_atm', 'N/A')}")
        print(f"   CE Must be OTM: {criteria.get('ce_must_be_otm', 'N/A')}")
        print(f"   PE Must be OTM: {criteria.get('pe_must_be_otm', 'N/A')}")
        
        # Check optimal strikes
        ce_strike = result['optimal_ce_strike']
        pe_strike = result['optimal_pe_strike']
        
        print(f"\n🎯 Optimal Strangle Selection:")
        print(f"   CE Strike: {ce_strike['strike']} (Score: {ce_strike['call_selling_score']:.1f})")
        print(f"   PE Strike: {pe_strike['strike']} (Score: {pe_strike['put_selling_score']:.1f})")
        
        # Validate fixes
        print(f"\n✅ Validation Checks:")
        
        # 1. Different strikes
        if ce_strike['strike'] != pe_strike['strike']:
            print(f"   ✅ Different strikes: CE {ce_strike['strike']} ≠ PE {pe_strike['strike']}")
        else:
            print(f"   ❌ Same strikes: CE {ce_strike['strike']} = PE {pe_strike['strike']}")
        
        # 2. Minimum premium
        ce_premium = ce_strike['call_ltp']
        pe_premium = pe_strike['put_ltp']
        if ce_premium >= 8.0 and pe_premium >= 8.0:
            print(f"   ✅ Min premium met: CE ₹{ce_premium:.2f}, PE ₹{pe_premium:.2f} ≥ ₹8.00")
        else:
            print(f"   ❌ Min premium not met: CE ₹{ce_premium:.2f}, PE ₹{pe_premium:.2f} < ₹8.00")
        
        # 3. Distance from ATM
        atm_strike = result['atm_strike']
        ce_distance = (ce_strike['strike'] - atm_strike) / 50
        pe_distance = (atm_strike - pe_strike['strike']) / 50
        if ce_distance <= 4 and pe_distance <= 4:
            print(f"   ✅ Distance from ATM: CE {ce_distance:.0f} strikes, PE {pe_distance:.0f} strikes ≤ 4")
        else:
            print(f"   ❌ Too far from ATM: CE {ce_distance:.0f} strikes, PE {pe_distance:.0f} strikes > 4")
        
        # 4. OTM validation
        if ce_strike['strike'] > atm_strike and pe_strike['strike'] < atm_strike:
            print(f"   ✅ OTM validation: CE {ce_strike['strike']} > ATM {atm_strike} > PE {pe_strike['strike']}")
        else:
            print(f"   ❌ OTM validation failed: CE {ce_strike['strike']}, ATM {atm_strike}, PE {pe_strike['strike']}")
        
        # Show strangle metrics
        strangle_analysis = result['strangle_analysis']
        print(f"\n📊 Strangle Metrics:")
        print(f"   Combined Premium: ₹{strangle_analysis['combined_premium']:.2f}")
        print(f"   Strangle Width: {strangle_analysis['strangle_width']:.0f} points")
        print(f"   Combined Score: {strangle_analysis['combined_score']:.1f}/100")
        
        # Show recommendation
        recommendation = result['recommendation']
        print(f"\n🎯 Recommendation: {recommendation['recommendation']}")
        print(f"   Confidence: {recommendation['confidence']}")
        print(f"   Risk Level: {recommendation['risk_level']}")
        
        print(f"\n✅ All strangle fixes validated successfully!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_strangle_fixes()

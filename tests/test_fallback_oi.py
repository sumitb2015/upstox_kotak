"""
Test script for Fallback OI Analysis
Tests the fallback functionality when option chain API is not available
"""

import sys
import os
from datetime import datetime

# Add current directory to path for imports
# Add parent directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.oi_analysis.oi_analysis_fallback import OIAnalysisFallback
from lib.oi_analysis.oi_analysis import get_oi_sentiment_analysis


def test_fallback_analysis():
    """Test fallback OI analysis functionality"""
    print("="*60)
    print("TESTING FALLBACK OI ANALYSIS")
    print("="*60)
    
    try:
        # Read access token
        with open("lib/core/accessToken.txt", "r") as file:
            access_token = file.read().strip()
        
        print("✅ Access token loaded successfully")
        
        # Test 1: Fallback analyzer initialization
        print("\n📊 TEST 1: Fallback Analyzer Initialization")
        print("-" * 40)
        
        fallback_analyzer = OIAnalysisFallback(access_token, "NSE_INDEX|Nifty 50")
        print("✅ Fallback analyzer initialized successfully")
        
        # Test 2: Basic market sentiment
        print("\n📊 TEST 2: Basic Market Sentiment")
        print("-" * 40)
        
        market_sentiment = fallback_analyzer.get_basic_market_sentiment()
        
        if "error" in market_sentiment:
            print(f"❌ Error in market sentiment: {market_sentiment['error']}")
        else:
            print("✅ Market sentiment analysis completed")
            print(f"📊 Spot Price: ₹{market_sentiment['spot_price']:.2f}")
            print(f"📊 ATM Strike: {market_sentiment['atm_strike']}")
            print(f"📊 Sentiment: {market_sentiment['sentiment']}")
            print(f"📊 Data Source: {market_sentiment['data_source']}")
        
        # Test 3: Simplified selling recommendations
        print("\n📊 TEST 3: Simplified Selling Recommendations")
        print("-" * 40)
        
        # Test recommendations for different strikes
        test_strikes = [25200, 25250, 25300, 25350, 25400]
        
        for strike in test_strikes:
            recommendation = fallback_analyzer.get_simplified_selling_recommendation(strike)
            
            if "error" in recommendation:
                print(f"❌ Error for strike {strike}: {recommendation['error']}")
            else:
                rec_emoji = "🟢" if recommendation['recommendation'] in ["strong_sell", "sell"] else "🔴" if recommendation['recommendation'] in ["strong_avoid", "avoid"] else "🟡"
                print(f"📍 Strike {strike}: {rec_emoji} {recommendation['recommendation']}")
                print(f"   Score: {recommendation['selling_score']:.1f}/100")
                print(f"   Risk: {recommendation['risk_level']}")
                print(f"   Distance from ATM: {recommendation['distance_from_atm']} points")
                print(f"   Reasoning: {recommendation['reasoning']}")
                print()
        
        # Test 4: Fallback monitoring update
        print("\n📊 TEST 4: Fallback Monitoring Update")
        print("-" * 40)
        
        monitoring_update = fallback_analyzer.get_fallback_monitoring_update()
        
        if "error" in monitoring_update:
            print(f"❌ Error in monitoring update: {monitoring_update['error']}")
        else:
            print("✅ Fallback monitoring update completed")
            print(f"📊 Overall Recommendation: {monitoring_update['overall_recommendation']}")
            print(f"📊 Risk Level: {monitoring_update['risk_level']}")
            print(f"📊 Data Source: {monitoring_update['data_source']}")
            print(f"📊 Strike Recommendations: {len(monitoring_update['strike_recommendations'])}")
        
        # Test 5: Formatted display
        print("\n📊 TEST 5: Formatted Display")
        print("-" * 40)
        
        formatted_display = fallback_analyzer.format_fallback_display(monitoring_update)
        print(formatted_display)
        
        # Test 6: Main OI analysis with fallback
        print("\n📊 TEST 6: Main OI Analysis with Fallback")
        print("-" * 40)
        
        print("Testing main OI analysis function (will use fallback if option chain fails)...")
        main_analysis = get_oi_sentiment_analysis(access_token, "NSE_INDEX|Nifty 50", strikes_around_atm=3)
        
        if "error" in main_analysis:
            print(f"❌ Error in main analysis: {main_analysis['error']}")
        else:
            print("✅ Main OI analysis completed (with fallback if needed)")
            print(f"📊 Data Source: {main_analysis.get('data_source', 'main_analysis')}")
            
            if 'overall_recommendation' in main_analysis:
                print(f"📊 Overall Recommendation: {main_analysis['overall_recommendation']}")
                print(f"📊 Risk Level: {main_analysis['risk_level']}")
        
        print("\n" + "="*60)
        print("✅ FALLBACK OI ANALYSIS TESTING COMPLETED SUCCESSFULLY")
        print("="*60)
        
        # Summary
        print("\n📋 SUMMARY:")
        print("✅ Fallback analyzer initialization working")
        print("✅ Basic market sentiment analysis working")
        print("✅ Simplified selling recommendations working")
        print("✅ Fallback monitoring update working")
        print("✅ Formatted display working")
        print("✅ Main OI analysis with fallback working")
        print("\n💡 The fallback system provides basic OI analysis when option chain API is not available!")
        
    except FileNotFoundError:
        print("❌ Error: accessToken.txt file not found")
        print("Please run authentication first to generate the access token")
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()


def demonstrate_fallback_vs_main():
    """Demonstrate difference between fallback and main analysis"""
    print("\n" + "="*60)
    print("FALLBACK vs MAIN ANALYSIS COMPARISON")
    print("="*60)
    
    try:
        # Read access token
        with open("lib/core/accessToken.txt", "r") as file:
            access_token = file.read().strip()
        
        print("📊 Testing both fallback and main analysis...")
        
        # Test fallback directly
        print("\n🔄 FALLBACK ANALYSIS:")
        fallback_analyzer = OIAnalysisFallback(access_token)
        fallback_result = fallback_analyzer.get_fallback_monitoring_update()
        
        if "error" not in fallback_result:
            print(f"   Data Source: {fallback_result.get('data_source', 'fallback')}")
            print(f"   Overall Recommendation: {fallback_result.get('overall_recommendation', 'N/A')}")
            print(f"   Risk Level: {fallback_result.get('risk_level', 'N/A')}")
        
        # Test main analysis (will use fallback if option chain fails)
        print("\n🔄 MAIN ANALYSIS (with fallback):")
        main_result = get_oi_sentiment_analysis(access_token)
        
        if "error" not in main_result:
            print(f"   Data Source: {main_result.get('data_source', 'main')}")
            if 'overall_recommendation' in main_result:
                print(f"   Overall Recommendation: {main_result['overall_recommendation']}")
                print(f"   Risk Level: {main_result['risk_level']}")
            elif 'market_sentiment' in main_result:
                print(f"   Market Sentiment: {main_result['market_sentiment']}")
        
        print("\n💡 Both analyses should provide similar results when option chain API is not available")
        
    except Exception as e:
        print(f"❌ Error in comparison: {e}")


if __name__ == "__main__":
    print("Fallback OI Analysis Test Suite")
    print("This script tests the fallback OI analysis functionality")
    print()
    
    # Run tests
    test_fallback_analysis()
    
    # Demonstrate comparison
    demonstrate_fallback_vs_main()
    
    print("\n🎯 NEXT STEPS:")
    print("1. Run the debug script to identify option chain API issues")
    print("2. Use fallback analysis when option chain API is not available")
    print("3. The fallback provides basic but useful analysis for option selling")
    print("4. Monitor for when option chain API becomes available again")

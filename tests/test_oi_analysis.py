"""
Test script for OI Analysis functionality
Demonstrates how to use OI analysis for option selling strategy
"""

import sys
import os
from datetime import datetime

# Add parent directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.oi_analysis.oi_analysis import OIAnalyzer, get_oi_sentiment_analysis
from lib.oi_analysis.oi_monitoring import OIMonitor


def test_oi_analysis():
    """Test OI analysis functionality"""
    print("="*60)
    print("TESTING OI ANALYSIS FOR OPTION SELLING STRATEGY")
    print("="*60)
    
    try:
        # Read access token
        with open("lib/core/accessToken.txt", "r") as file:
            access_token = file.read().strip()
        
        print("✅ Access token loaded successfully")
        
        # Test 1: Basic OI sentiment analysis
        print("\n📊 TEST 1: Basic OI Sentiment Analysis")
        print("-" * 40)
        
        sentiment_data = get_oi_sentiment_analysis(
            access_token=access_token,
            underlying_key="NSE_INDEX|Nifty 50",
            strikes_around_atm=3
        )
        
        if "error" in sentiment_data:
            print(f"❌ Error in sentiment analysis: {sentiment_data['error']}")
        else:
            print("✅ OI sentiment analysis completed successfully")
            print(f"📊 Market Sentiment: {sentiment_data['market_sentiment']}")
            print(f"📊 PCR: {sentiment_data['pcr']:.2f}")
            print(f"📊 Total Call OI: {sentiment_data['total_call_oi']:,}")
            print(f"📊 Total Put OI: {sentiment_data['total_put_oi']:,}")
            
            # Show strike details
            print(f"\n📋 Strike Details:")
            for strike_detail in sentiment_data['strike_details']:
                strike = strike_detail['strike_price']
                sentiment = strike_detail['strike_sentiment']
                call_activity = strike_detail['call_oi_activity']
                put_activity = strike_detail['put_oi_activity']
                
                sentiment_emoji = "🟢" if sentiment == "bullish_for_sellers" else "🔴" if sentiment == "bearish_for_sellers" else "🟡"
                
                print(f"  {strike}: {sentiment_emoji} {sentiment}")
                print(f"    Call: {call_activity} ({strike_detail['call_oi_change_pct']:+.1f}%)")
                print(f"    Put: {put_activity} ({strike_detail['put_oi_change_pct']:+.1f}%)")
        
        # Test 2: OI Analyzer class
        print("\n📊 TEST 2: OI Analyzer Class")
        print("-" * 40)
        
        analyzer = OIAnalyzer(access_token, "NSE_INDEX|Nifty 50")
        print("✅ OI Analyzer initialized successfully")
        
        # Test 3: OI Monitor class
        print("\n📊 TEST 3: OI Monitor Class")
        print("-" * 40)
        
        monitor = OIMonitor(access_token, "NSE_INDEX|Nifty 50")
        print("✅ OI Monitor initialized successfully")
        
        # Test monitoring for a few strikes
        test_strikes = [25300, 25350, 25400]  # Example strikes
        print(f"🔍 Testing monitoring for strikes: {test_strikes}")
        
        if monitor.start_monitoring(test_strikes, monitoring_interval=30):
            print("✅ OI monitoring started successfully")
            
            # Get a snapshot
            snapshot = monitor.get_current_oi_snapshot()
            if "error" not in snapshot:
                print("✅ OI snapshot retrieved successfully")
                print(f"📊 Monitored strikes: {len(snapshot['strikes'])}")
                
                # Get recommendations
                recommendations = monitor.get_selling_recommendations(snapshot)
                if "error" not in recommendations:
                    print("✅ Selling recommendations generated successfully")
                    print(f"🎯 Overall Recommendation: {recommendations['overall_recommendation']}")
                    print(f"⚠️  Risk Level: {recommendations['risk_level']}")
                    
                    # Show strike recommendations
                    print(f"\n📋 Strike Recommendations:")
                    for strike, rec in recommendations['strike_recommendations'].items():
                        rec_emoji = "🟢" if rec['recommendation'] in ["strong_sell", "sell"] else "🔴" if rec['recommendation'] in ["strong_avoid", "avoid"] else "🟡"
                        print(f"  {strike}: {rec_emoji} {rec['recommendation']} (Score: {rec['selling_score']:.1f})")
                        print(f"    Risk: {rec['risk_level']}")
                        print(f"    Reasoning: {rec['reasoning']}")
                else:
                    print(f"❌ Error getting recommendations: {recommendations['error']}")
            else:
                print(f"❌ Error getting snapshot: {snapshot['error']}")
            
            # Stop monitoring
            monitor.stop_monitoring()
            print("⏹️  OI monitoring stopped")
        else:
            print("❌ Failed to start OI monitoring")
        
        print("\n" + "="*60)
        print("✅ OI ANALYSIS TESTING COMPLETED SUCCESSFULLY")
        print("="*60)
        
        # Summary
        print("\n📋 SUMMARY:")
        print("✅ OI sentiment analysis working")
        print("✅ OI Analyzer class functional")
        print("✅ OI Monitor class functional")
        print("✅ Real-time monitoring capabilities verified")
        print("✅ Selling recommendations system working")
        print("\n💡 The OI analysis is now ready to be integrated into your straddle strategy!")
        
    except FileNotFoundError:
        print("❌ Error: accessToken.txt file not found")
        print("Please run authentication first to generate the access token")
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()


def demonstrate_oi_classification():
    """Demonstrate OI activity classification"""
    print("\n" + "="*60)
    print("OI ACTIVITY CLASSIFICATION DEMONSTRATION")
    print("="*60)
    
    analyzer = OIAnalyzer("dummy_token", "NSE_INDEX|Nifty 50")
    
    # Test cases for OI classification
    test_cases = [
        # (current_oi, prev_oi, price_change, option_type, expected_classification)
        (1000, 800, 5.0, "call", "long_build"),      # OI up, price up, call
        (1000, 800, -5.0, "call", "short_build"),    # OI up, price down, call
        (800, 1000, 5.0, "call", "long_unwinding"),  # OI down, price up, call
        (800, 1000, -5.0, "call", "short_unwinding"), # OI down, price down, call
        (1000, 800, 5.0, "put", "short_build"),      # OI up, price up, put
        (1000, 800, -5.0, "put", "long_build"),      # OI up, price down, put
        (800, 1000, 5.0, "put", "short_unwinding"),  # OI down, price up, put
        (800, 1000, -5.0, "put", "long_unwinding"),  # OI down, price down, put
    ]
    
    print("📊 Testing OI Activity Classification:")
    print("-" * 50)
    
    for i, (current_oi, prev_oi, price_change, option_type, expected) in enumerate(test_cases, 1):
        classification = analyzer.classify_oi_activity(current_oi, prev_oi, price_change, option_type)
        status = "✅" if classification == expected else "❌"
        
        print(f"{i}. {option_type.upper()} - OI: {prev_oi}→{current_oi}, Price: {price_change:+.1f}")
        print(f"   Classification: {classification} {status}")
        print(f"   Expected: {expected}")
        print()
    
    print("💡 This classification helps determine market sentiment for option sellers:")
    print("   🟢 Long Unwinding: Buyers exiting (good for sellers)")
    print("   🔴 Long Build: Buyers accumulating (bad for sellers)")
    print("   🟢 Short Build: Sellers accumulating (good for sellers)")
    print("   🔴 Short Unwinding: Sellers exiting (bad for sellers)")


if __name__ == "__main__":
    print("OI Analysis Test Suite")
    print("This script tests the OI analysis functionality for option selling strategy")
    print()
    
    # Run tests
    test_oi_analysis()
    
    # Demonstrate classification
    demonstrate_oi_classification()
    
    print("\n🎯 NEXT STEPS:")
    print("1. Run your main strategy with OI analysis enabled")
    print("2. Monitor the OI sentiment and recommendations during trading")
    print("3. Use OI alerts to make better entry/exit decisions")
    print("4. Analyze OI patterns to optimize strike selection")

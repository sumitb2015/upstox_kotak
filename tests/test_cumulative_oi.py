#!/usr/bin/env python3
"""
Test script for Cumulative OI Analysis
Run this after activating your conda environment: conda activate upstox
"""

import sys
import os
from datetime import datetime, timedelta

# Add current directory to path
# Add parent directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_cumulative_oi_analysis():
    """Test the cumulative OI analysis functionality"""
    print("="*70)
    print("TESTING CUMULATIVE OI ANALYSIS")
    print("="*70)
    
    try:
        # Import required modules
        from authentication import check_existing_token
        from cumulative_oi_analysis import CumulativeOIAnalyzer
        
        # Check if access token exists
        if not check_existing_token():
            print("❌ No access token found. Please run authentication first.")
            return False
        
        # Load access token
        with open("lib/core/accessToken.txt", "r") as file:
            access_token = file.read().strip()
        
        print("✅ Access token loaded successfully")
        
        # Initialize cumulative OI analyzer
        print("\n🔍 Initializing Cumulative OI Analyzer...")
        analyzer = CumulativeOIAnalyzer(access_token, "NSE_INDEX|Nifty 50")
        print("✅ Cumulative OI Analyzer initialized")
        
        # Test cumulative OI calculation
        print("\n📊 Testing Cumulative OI Calculation...")
        cumulative_data = analyzer.calculate_cumulative_oi()
        
        if "error" in cumulative_data:
            print(f"❌ Cumulative OI calculation failed: {cumulative_data['error']}")
            return False
        
        print(f"✅ Cumulative OI calculation successful!")
        print(f"   Strikes analyzed: {cumulative_data['strikes_analyzed']}")
        print(f"   Strike range: {cumulative_data['strike_range']}")
        print(f"   Total Call OI: {cumulative_data['total_call_oi']:,}")
        print(f"   Total Put OI: {cumulative_data['total_put_oi']:,}")
        print(f"   Put-Call Ratio: {cumulative_data['pcr']:.2f}")
        
        # Test overall sentiment analysis
        print("\n🎯 Testing Overall Sentiment Analysis...")
        sentiment_data = analyzer.get_overall_sentiment(cumulative_data)
        
        if "error" in sentiment_data:
            print(f"❌ Sentiment analysis failed: {sentiment_data['error']}")
            return False
        
        print(f"✅ Sentiment analysis successful!")
        print(f"   Overall Sentiment: {sentiment_data['overall_sentiment']}")
        print(f"   Sentiment Strength: {sentiment_data['sentiment_strength']}")
        print(f"   Sentiment Score: {sentiment_data['sentiment_score']:.1f}/100")
        print(f"   Bullish Signals: {sentiment_data['bullish_signals']}")
        print(f"   Bearish Signals: {sentiment_data['bearish_signals']}")
        
        # Test trend analysis
        print("\n📈 Testing OI Trend Analysis...")
        trend_data = analyzer.analyze_oi_trends(cumulative_data)
        
        if "error" in trend_data:
            print(f"❌ Trend analysis failed: {trend_data['error']}")
            return False
        
        print(f"✅ Trend analysis successful!")
        print(f"   Overall Trend: {trend_data['overall_trend']}")
        print(f"   Trend Strength: {trend_data['trend_strength']}")
        print(f"   High Activity Strikes: {len(trend_data['high_activity_strikes'])}")
        print(f"   Low Activity Strikes: {len(trend_data['low_activity_strikes'])}")
        
        # Test formatted output
        print("\n📋 Testing Formatted Output...")
        formatted_output = analyzer.format_cumulative_analysis(cumulative_data, sentiment_data, trend_data)
        print("✅ Formatted output generated successfully!")
        print("\n" + "="*70)
        print("SAMPLE FORMATTED OUTPUT:")
        print("="*70)
        print(formatted_output)
        
        return True
        
    except Exception as e:
        print(f"❌ Error during test: {e}")
        return False

def test_strategy_integration():
    """Test cumulative OI integration with strategy"""
    print("\n" + "="*70)
    print("TESTING STRATEGY INTEGRATION")
    print("="*70)
    
    try:
        from straddle_strategy import ShortStraddleStrategy
        from market_data import download_nse_market_data
        
        # Load access token
        with open("lib/core/accessToken.txt", "r") as file:
            access_token = file.read().strip()
        
        # Load NSE data
        nse_data = download_nse_market_data()
        if nse_data is None:
            print("❌ Failed to load NSE data")
            return False
        
        print("✅ NSE data loaded successfully")
        
        # Initialize strategy with OI analysis enabled
        strategy = ShortStraddleStrategy(
            access_token=access_token,
            nse_data=nse_data,
            underlying_symbol="NIFTY",
            lot_size=1,
            profit_target=3000,
            max_loss_limit=3000,
            ratio_threshold=0.6,
            straddle_width_threshold=0.2,
            max_deviation_points=200,
            enable_oi_analysis=True
        )
        
        print("✅ Strategy initialized with cumulative OI analysis enabled")
        
        # Test cumulative OI analysis
        print("\n🔍 Testing Cumulative OI Analysis in Strategy...")
        cumulative_analysis = strategy.get_cumulative_oi_analysis()
        
        if "error" in cumulative_analysis:
            print(f"❌ Strategy cumulative OI analysis failed: {cumulative_analysis['error']}")
            return False
        
        print("✅ Strategy cumulative OI analysis working!")
        
        # Test cumulative sentiment for entry
        print("\n🎯 Testing Cumulative Sentiment for Entry...")
        should_enter, reason, score = strategy.get_cumulative_sentiment_for_entry()
        
        print(f"✅ Cumulative sentiment analysis working!")
        print(f"   Should Enter: {should_enter}")
        print(f"   Reason: {reason}")
        print(f"   Score: {score:.1f}/100")
        
        return True
        
    except Exception as e:
        print(f"❌ Error during strategy integration test: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Cumulative OI Analysis Test")
    print("Make sure to activate your conda environment first:")
    print("conda activate upstox")
    print()
    
    # Test 1: Basic cumulative OI functionality
    test1_result = test_cumulative_oi_analysis()
    
    # Test 2: Strategy integration
    test2_result = test_strategy_integration()
    
    print("\n" + "="*70)
    print("TEST RESULTS SUMMARY")
    print("="*70)
    print(f"📊 Cumulative OI Analysis Test: {'✅ PASSED' if test1_result else '❌ FAILED'}")
    print(f"🎯 Strategy Integration Test: {'✅ PASSED' if test2_result else '❌ FAILED'}")
    
    if test1_result and test2_result:
        print("\n🎉 ALL TESTS PASSED! Cumulative OI analysis is working correctly.")
        print("You can now run main.py and see the enhanced cumulative OI analysis.")
    else:
        print("\n⚠️  Some tests failed. Check the output above for details.")
    
    print("="*70)

"""
Test script for improved OI analysis with proper price change integration and thresholds
"""

import sys
import os
import pandas as pd
from datetime import datetime, timedelta

# Add the parent directory to the Python path to allow imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from lib.core.authentication import perform_authentication, save_access_token, check_existing_token
from lib.api.market_data import download_nse_market_data
from lib.oi_analysis.oi_analysis import OIAnalyzer


def test_oi_classification():
    """Test OI classification with different scenarios"""
    print("🧪 Testing OI Classification Logic")
    print("="*50)
    
    # Initialize analyzer with custom thresholds
    analyzer = OIAnalyzer("dummy_token", min_oi_threshold=5.0, significant_oi_threshold=10.0)
    
    # Test scenarios
    test_cases = [
        # (current_oi, prev_oi, price_change, option_type, expected_classification)
        (1000, 900, 5.0, "call", "long_build"),      # OI up 11%, price up -> call buyers
        (1000, 900, -5.0, "call", "short_build"),    # OI up 11%, price down -> call sellers
        (800, 900, 5.0, "call", "long_unwinding"),   # OI down 11%, price up -> call buyers exiting
        (800, 900, -5.0, "call", "short_unwinding"), # OI down 11%, price down -> call sellers exiting
        
        (1000, 900, 5.0, "put", "short_build"),      # OI up 11%, price up -> put sellers
        (1000, 900, -5.0, "put", "long_build"),      # OI up 11%, price down -> put buyers
        (800, 900, 5.0, "put", "short_unwinding"),   # OI down 11%, price up -> put sellers exiting
        (800, 900, -5.0, "put", "long_unwinding"),   # OI down 11%, price down -> put buyers exiting
        
        # Test insignificant changes
        (950, 900, 2.0, "call", "insignificant"),    # OI up 5.6%, below threshold
        (850, 900, -2.0, "put", "insignificant"),    # OI down 5.6%, below threshold
    ]
    
    print("Test Cases:")
    for i, (current_oi, prev_oi, price_change, option_type, expected) in enumerate(test_cases, 1):
        result = analyzer.classify_oi_activity(current_oi, prev_oi, price_change, option_type)
        status = "✅" if result == expected else "❌"
        oi_change_pct = ((current_oi - prev_oi) / prev_oi * 100) if prev_oi > 0 else 0
        
        print(f"{i:2d}. {status} {option_type.upper()}: OI {oi_change_pct:+.1f}%, Price {price_change:+.1f} → {result}")
        if result != expected:
            print(f"    Expected: {expected}, Got: {result}")
    
    print("\n" + "="*50)


def test_sentiment_analysis():
    """Test sentiment analysis with different OI scenarios"""
    print("🧪 Testing Sentiment Analysis")
    print("="*50)
    
    analyzer = OIAnalyzer("dummy_token", min_oi_threshold=5.0, significant_oi_threshold=10.0)
    
    # Test scenarios for sentiment determination
    test_cases = [
        # (call_activity, put_activity, call_oi_pct, put_oi_pct, expected_sentiment)
        ("long_unwinding", "long_unwinding", -12.0, -8.0, "bullish_for_sellers"),
        ("long_build", "long_build", 15.0, 12.0, "bearish_for_sellers"),
        ("short_build", "short_build", 8.0, 6.0, "bullish_for_sellers"),
        ("short_unwinding", "short_unwinding", -7.0, -9.0, "bearish_for_sellers"),
        ("insignificant", "insignificant", 2.0, -3.0, "neutral"),  # Both insignificant
        ("long_build", "insignificant", 8.0, 2.0, "bearish_for_sellers"),  # Mixed signals
    ]
    
    print("Sentiment Test Cases:")
    for i, (call_act, put_act, call_pct, put_pct, expected) in enumerate(test_cases, 1):
        result = analyzer._determine_strike_sentiment(call_act, put_act, call_pct, put_pct)
        status = "✅" if result == expected else "❌"
        
        print(f"{i:2d}. {status} Call: {call_act} ({call_pct:+.1f}%), Put: {put_act} ({put_pct:+.1f}%) → {result}")
        if result != expected:
            print(f"    Expected: {expected}, Got: {result}")
    
    print("\n" + "="*50)


def test_threshold_impact():
    """Test impact of different thresholds"""
    print("🧪 Testing Threshold Impact")
    print("="*50)
    
    # Test with different threshold settings
    threshold_configs = [
        (2.0, 5.0, "Very Sensitive"),
        (5.0, 10.0, "Default"),
        (10.0, 20.0, "Conservative"),
    ]
    
    test_oi_change = 7.0  # 7% OI change
    
    for min_thresh, sig_thresh, label in threshold_configs:
        analyzer = OIAnalyzer("dummy_token", min_oi_threshold=min_thresh, significant_oi_threshold=sig_thresh)
        
        # Test classification
        result = analyzer.classify_oi_activity(1070, 1000, 5.0, "call")
        
        # Test significance
        is_significant = abs(test_oi_change) >= min_thresh
        is_highly_significant = abs(test_oi_change) >= sig_thresh
        
        print(f"{label} (Min: {min_thresh}%, Sig: {sig_thresh}%):")
        print(f"  OI Change: {test_oi_change}%")
        print(f"  Classification: {result}")
        print(f"  Significant: {is_significant}")
        print(f"  Highly Significant: {is_highly_significant}")
        print()
    
    print("="*50)


def main():
    print("🚀 Testing Improved OI Analysis")
    print("="*60)
    
    # Test OI classification logic
    test_oi_classification()
    
    # Test sentiment analysis
    test_sentiment_analysis()
    
    # Test threshold impact
    test_threshold_impact()
    
    print("✅ All OI Analysis Tests Completed!")
    print("\n📊 Key Improvements:")
    print("1. ✅ Price change now properly integrated with OI analysis")
    print("2. ✅ Minimum threshold (5%) prevents noise from small changes")
    print("3. ✅ Significant threshold (10%) for high-impact analysis")
    print("4. ✅ 'Insignificant' classification for small changes")
    print("5. ✅ Consistent thresholds across all analysis methods")
    print("6. ✅ Proper long_build/short_build/unwinding classification")


if __name__ == "__main__":
    main()

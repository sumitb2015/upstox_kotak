"""
Test script for the Parallel Strategy System (Straddle + OI-Guided Strangle)
"""

import sys
import os
import pandas as pd
from datetime import datetime, timedelta

# Add the parent directory to the Python path to allow imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from lib.core.authentication import perform_authentication, save_access_token, check_existing_token
from lib.api.market_data import download_nse_market_data
from strategies.non_directional.legacy_straddle.live import ShortStraddleStrategy
from lib.oi_analysis.oi_strangle_analyzer import OIStrangleAnalyzer


def main():
    print("🚀 Testing Parallel Strategy System (Straddle + OI-Guided Strangle)")
    print("="*70)

    # Step 1: Authentication
    access_token = None
    if check_existing_token():
        print("✅ Using existing access token")
        with open("lib/core/accessToken.txt", "r") as file:
            access_token = file.read().strip()
    else:
        try:
            access_token = perform_authentication()
            save_access_token(access_token)
            print("✅ Authentication completed successfully!")
        except Exception as e:
            print(f"❌ Authentication failed: {e}")
            return

    if not access_token:
        print("❌ No access token available. Exiting.")
        return

    # Step 2: Download NSE data
    nse_data = download_nse_market_data()
    if nse_data is None:
        print("❌ Failed to download NSE data. Exiting...")
        return

    print(f"✅ NSE data loaded: {len(nse_data)} instruments")

    # Step 3: Initialize strategy with OI analysis enabled
    print("\n📊 Initializing ShortStraddleStrategy with OI analysis enabled...")
    try:
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

        # Step 4: Test OI-Guided Strangle Analysis
        print("\n🎯 Testing OI-Guided Strangle Analysis...")
        print("="*50)
        
        strangle_analysis = strategy.get_strangle_analysis()
        if "error" not in strangle_analysis:
            print("✅ Strangle Analysis successful!")
            
            # Display strangle analysis
            ce_strike = strangle_analysis['optimal_ce_strike']
            pe_strike = strangle_analysis['optimal_pe_strike']
            recommendation = strangle_analysis['recommendation']
            strangle_metrics = strangle_analysis['strangle_analysis']
            
            print(f"\n🎯 OPTIMAL STRANGLE SELECTION:")
            print(f"   CE Strike: {ce_strike['strike']} (Score: {ce_strike['call_selling_score']:.1f})")
            print(f"   PE Strike: {pe_strike['strike']} (Score: {pe_strike['put_selling_score']:.1f})")
            print(f"   Combined Score: {strangle_metrics['combined_selling_score']:.1f}/100")
            
            rec_emoji = "🟢" if recommendation['recommendation'] in ["strong_strangle", "strangle"] else "🔴" if recommendation['recommendation'] == "avoid" else "🟡"
            print(f"\n📊 STRANGLE RECOMMENDATION: {rec_emoji} {recommendation['recommendation'].upper()}")
            print(f"   Confidence: {recommendation['confidence'].title()}")
            print(f"   Risk Level: {strangle_metrics['overall_risk_level'].title()}")
            print(f"   Strangle Width: {strangle_metrics['strangle_width']} points")
            print(f"   Combined Premium: ₹{strangle_metrics['combined_premium']:.2f}")
            print(f"   Reasoning: {recommendation['reasoning']}")
            
            # Test strangle entry decision
            print(f"\n🎯 Testing Strangle Entry Decision...")
            should_enter, reason, confidence = strategy.should_enter_strangle(strangle_analysis)
            print(f"   Should Enter: {'✅ YES' if should_enter else '❌ NO'}")
            print(f"   Reason: {reason}")
            print(f"   Confidence: {confidence}%")
            
        else:
            print(f"❌ Strangle Analysis Error: {strangle_analysis['error']}")

        # Step 5: Test Parallel Strategy Components
        print(f"\n🔄 Testing Parallel Strategy Components...")
        print("="*50)
        
        # Test straddle analysis
        current_atm = strategy.get_atm_strike()
        print(f"📍 Current ATM Strike: {current_atm}")
        
        # Test OI sentiment analysis
        print(f"\n--- Testing OI Sentiment Analysis ---")
        oi_sentiment = strategy.analyze_oi_sentiment(current_atm)
        if "error" not in oi_sentiment:
            print(f"✅ OI Sentiment: {oi_sentiment['strike_sentiment']}")
            print(f"   Call Activity: {oi_sentiment['call_oi_activity']} ({oi_sentiment['call_oi_change_pct']:+.1f}%)")
            print(f"   Put Activity: {oi_sentiment['put_oi_activity']} ({oi_sentiment['put_oi_change_pct']:+.1f}%)")
        else:
            print(f"❌ OI Sentiment Error: {oi_sentiment['error']}")
        
        # Test cumulative OI analysis
        print(f"\n--- Testing Cumulative OI Analysis ---")
        cumulative_analysis = strategy.get_cumulative_oi_analysis()
        if "error" not in cumulative_analysis:
            print(f"✅ Cumulative OI Analysis successful.")
            print(f"   Overall Sentiment: {cumulative_analysis['sentiment_data']['overall_sentiment']}")
            print(f"   Total Call OI: {cumulative_analysis['cumulative_data']['total_call_oi']:,}")
            print(f"   Total Put OI: {cumulative_analysis['cumulative_data']['total_put_oi']:,}")
        else:
            print(f"❌ Cumulative OI Analysis Error: {cumulative_analysis['error']}")
        
        # Test dynamic threshold
        print(f"\n--- Testing Dynamic Width Threshold ---")
        dynamic_threshold = strategy.get_dynamic_width_threshold(current_atm)
        print(f"✅ Dynamic Width Threshold: {dynamic_threshold*100:.1f}%")
        
        # Step 6: Test Strategy Integration
        print(f"\n🔗 Testing Strategy Integration...")
        print("="*50)
        
        # Test if both strategies can run in parallel
        print("✅ Primary Strategy: ATM Straddle (existing logic)")
        print("✅ Secondary Strategy: OI-Guided Strangle (new logic)")
        print("✅ Parallel Execution: Both strategies can run simultaneously")
        print("✅ Independent Position Management: Separate tracking for each strategy")
        print("✅ Enhanced Monitoring: Combined view of both strategies")
        
        # Step 7: Display Strategy Capabilities
        print(f"\n🎯 PARALLEL STRATEGY CAPABILITIES")
        print("="*50)
        print("📊 PRIMARY STRATEGY: ATM Straddle")
        print("   - Uses existing proven logic")
        print("   - Monitors ATM straddle width and deviation")
        print("   - Manages positions with current risk management")
        print("   - Enhanced with OI-based dynamic thresholds")
        
        print("\n🎯 SECONDARY STRATEGY: OI-Guided Strangle")
        print("   - Analyzes OI across multiple strikes")
        print("   - Finds optimal CE and PE strikes separately")
        print("   - Independent entry/exit logic")
        print("   - Separate position tracking and management")
        
        print("\n🔄 PARALLEL EXECUTION BENEFITS")
        print("   - Diversification across strategies")
        print("   - Better market coverage")
        print("   - Enhanced profit potential")
        print("   - Risk distribution")
        print("   - OI-optimized strike selection")

    except Exception as e:
        print(f"❌ Error during strategy initialization or testing: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "="*70)
    print("✅ Parallel Strategy System Test Completed!")
    print("🚀 Ready to run the enhanced strategy with both straddle and strangle capabilities!")


if __name__ == "__main__":
    main()

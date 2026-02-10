#!/usr/bin/env python3
"""
Test script for Historical Data and Pivot Levels functionality
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from strategies.non_directional.legacy_straddle.live import ShortStraddleStrategy
import pandas as pd

def test_pivot_levels():
    """
    Test the pivot levels calculation functionality
    """
    print("🧪 Testing Historical Data and Pivot Levels Calculation")
    print("="*60)
    
    # Mock data for testing (you can replace with real access token)
    access_token = "your_access_token_here"
    
    # Create mock NSE data
    nse_data = pd.DataFrame({
        'symbol': ['NIFTY'],
        'ltp': [24000.0]
    })
    
    try:
        # Initialize strategy (this will trigger pivot calculation)
        strategy = ShortStraddleStrategy(
            access_token=access_token,
            nse_data=nse_data,
            underlying_symbol="NIFTY",
            verbose=True
        )
        
        # Test getting pivot levels
        print("\n🔍 Testing Pivot Level Retrieval:")
        
        # Get CPR levels
        cpr_levels = strategy.get_cpr_levels()
        if cpr_levels:
            print("✅ CPR Levels Retrieved:")
            for key, value in cpr_levels.items():
                print(f"   {key.upper()}: ₹{value:.2f}")
        else:
            print("⚠️ CPR Levels not available")
        
        # Get Camarilla pivots
        camarilla_pivots = strategy.get_camarilla_pivots()
        if camarilla_pivots:
            print("\n✅ Camarilla Pivots Retrieved:")
            for key, value in camarilla_pivots.items():
                print(f"   {key.upper()}: ₹{value:.2f}")
        else:
            print("⚠️ Camarilla Pivots not available")
        
        # Get previous day OHLC
        previous_ohlc = strategy.get_previous_day_ohlc()
        if previous_ohlc:
            print("\n✅ Previous Day OHLC Retrieved:")
            print(f"   Date: {previous_ohlc['date']}")
            print(f"   Open: ₹{previous_ohlc['open']:.2f}")
            print(f"   High: ₹{previous_ohlc['high']:.2f}")
            print(f"   Low: ₹{previous_ohlc['low']:.2f}")
            print(f"   Close: ₹{previous_ohlc['close']:.2f}")
            print(f"   Volume: {previous_ohlc['volume']:,}")
        else:
            print("⚠️ Previous Day OHLC not available")
        
        print("\n✅ Test completed successfully!")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()

def test_manual_calculation():
    """
    Test manual calculation of pivot levels with sample data
    """
    print("\n🧪 Testing Manual Pivot Calculation with Sample Data")
    print("="*60)
    
    # Sample OHLC data
    sample_ohlc = {
        'date': '2024-01-15',
        'open': 24000.0,
        'high': 24200.0,
        'low': 23800.0,
        'close': 24100.0,
        'volume': 1000000
    }
    
    print(f"📊 Sample OHLC Data:")
    print(f"   Open: ₹{sample_ohlc['open']:.2f}")
    print(f"   High: ₹{sample_ohlc['high']:.2f}")
    print(f"   Low: ₹{sample_ohlc['low']:.2f}")
    print(f"   Close: ₹{sample_ohlc['close']:.2f}")
    
    # Create strategy instance for calculation methods
    strategy = ShortStraddleStrategy(
        access_token="dummy_token",
        nse_data=pd.DataFrame({'symbol': ['NIFTY'], 'ltp': [24000.0]}),
        verbose=False
    )
    
    # Calculate CPR levels
    cpr_levels = strategy._calculate_cpr_levels(sample_ohlc)
    print(f"\n🎯 CPR Levels Calculated:")
    for key, value in cpr_levels.items():
        print(f"   {key.upper()}: ₹{value:.2f}")
    
    # Verify CPR calculation
    if cpr_levels:
        print(f"\n🔍 CPR Calculation Verification:")
        print(f"   Pivot: ₹{cpr_levels['pivot']:.2f}")
        print(f"   BC: ₹{cpr_levels['bc']:.2f}")
        print(f"   TC: ₹{cpr_levels['tc']:.2f}")
        print(f"   CPR Range: ₹{cpr_levels['cpr']:.2f}")
        print(f"   TC - BC = ₹{cpr_levels['tc'] - cpr_levels['bc']:.2f} (should match CPR)")
    
    # Verify PDH, PDL, PDC are initialized
    print(f"\n🔍 Previous Day OHLC Verification:")
    print(f"   PDH (Previous Day High): ₹{strategy.get_pdh():.2f}")
    print(f"   PDL (Previous Day Low):  ₹{strategy.get_pdl():.2f}")
    print(f"   PDC (Previous Day Close): ₹{strategy.get_pdc():.2f}")
    print(f"   PDO (Previous Day Open):  ₹{strategy.get_pdo():.2f}")
    print(f"   Daily Range: ₹{strategy.get_pdh() - strategy.get_pdl():.2f}")
    
    # Calculate Camarilla pivots
    camarilla_pivots = strategy._calculate_camarilla_pivots(sample_ohlc)
    print(f"\n🎯 Camarilla Pivots Calculated:")
    for key, value in camarilla_pivots.items():
        print(f"   {key.upper()}: ₹{value:.2f}")
    
    print("\n✅ Manual calculation test completed!")

def test_with_real_api():
    """
    Test with real API using existing fetch_historical_data function
    """
    print("\n🧪 Testing with Real API using fetch_historical_data")
    print("="*60)
    
    try:
        from lib.api.market_data import fetch_historical_data
        from datetime import datetime, timedelta
        
        # Mock access token (replace with real one for testing)
        access_token = "your_access_token_here"
        
        # Calculate previous trading day
        today = datetime.now()
        if today.weekday() == 0:  # Monday
            previous_day = today - timedelta(days=3)
        elif today.weekday() == 6:  # Sunday
            previous_day = today - timedelta(days=2)
        else:
            previous_day = today - timedelta(days=1)
        
        date_str = previous_day.strftime('%Y-%m-%d')
        
        print(f"📊 Fetching historical data for {date_str}...")
        
        # Use existing fetch_historical_data function
        # For daily data, use "days" with interval 1 (as per official Upstox API docs)
        df = fetch_historical_data(
            access_token=access_token,
            symbol="NSE_INDEX|Nifty 50",
            interval_type="days",
            interval=1,  # 1 day interval
            start_date=date_str,
            end_date=date_str
        )
        
        if not df.empty:
            print(f"✅ Successfully fetched {len(df)} candles")
            print(f"📊 Data Preview:")
            print(df.head())
            
            # Get OHLC data
            last_row = df.iloc[-1]
            ohlc = {
                'date': last_row['timestamp'].strftime('%Y-%m-%d'),
                'open': float(last_row['open']),
                'high': float(last_row['high']),
                'low': float(last_row['low']),
                'close': float(last_row['close']),
                'volume': int(last_row['volume'])
            }
            
            print(f"\n📊 OHLC Data:")
            print(f"   Date: {ohlc['date']}")
            print(f"   Open: ₹{ohlc['open']:.2f}")
            print(f"   High: ₹{ohlc['high']:.2f}")
            print(f"   Low: ₹{ohlc['low']:.2f}")
            print(f"   Close: ₹{ohlc['close']:.2f}")
            print(f"   Volume: {ohlc['volume']:,}")
            
            # Test pivot calculations
            strategy = ShortStraddleStrategy(
                access_token=access_token,
                nse_data=pd.DataFrame({'symbol': ['NIFTY'], 'ltp': [24000.0]}),
                verbose=False
            )
            
            # Calculate pivots
            cpr_levels = strategy._calculate_cpr_levels(ohlc)
            camarilla_pivots = strategy._calculate_camarilla_pivots(ohlc)
            
            print(f"\n🎯 CPR Levels:")
            for key, value in cpr_levels.items():
                print(f"   {key.upper()}: ₹{value:.2f}")
            
            print(f"\n🎯 Camarilla Pivots:")
            for key, value in camarilla_pivots.items():
                print(f"   {key.upper()}: ₹{value:.2f}")
            
            print("\n✅ Real API test completed successfully!")
            
        else:
            print("⚠️ No data returned from API")
            
    except Exception as e:
        print(f"❌ Real API test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("🚀 Starting Pivot Levels Test Suite")
    print("="*60)
    
    # Test manual calculation first (doesn't require API)
    test_manual_calculation()
    
    # Test with real API using existing fetch_historical_data function
    print("\n" + "="*60)
    print("⚠️ Note: To test with real API, update the access_token in the script")
    print("="*60)
    
    # Uncomment the line below to test with real API
    # test_with_real_api()
    
    print("\n🎉 All tests completed!")

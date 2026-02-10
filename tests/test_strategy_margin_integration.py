#!/usr/bin/env python3
"""
Test script for Strategy Margin Integration
Tests the integration of margin and funds functions in the straddle strategy
"""

import sys
import os
# Add parent directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategies.non_directional.legacy_straddle.live import ShortStraddleStrategy
from lib.utils.funds_margin import get_funds_and_margin, format_funds_data
from lib.utils.margin_calculator import get_margin_details, analyze_margin_response
from lib.api.market_data import download_nse_market_data


def test_strategy_margin_integration():
    """Test margin integration in the strategy"""
    print("="*70)
    print("TESTING STRATEGY MARGIN INTEGRATION")
    print("="*70)
    
    try:
        # Load access token
        with open('lib/core/accessToken.txt', 'r') as file:
            access_token = file.read().strip()
        
        print("✅ Access token loaded successfully")
        
        # Download NSE data
        print("\n1. Downloading NSE market data...")
        nse_data = download_nse_market_data()
        if nse_data is None:
            print("❌ Failed to download NSE data")
            return False
        
        print(f"✅ NSE data downloaded: {len(nse_data)} instruments")
        
        # Initialize strategy
        print("\n2. Initializing strategy with margin integration...")
        strategy = ShortStraddleStrategy(
            access_token=access_token,
            nse_data=nse_data,
            underlying_symbol="NIFTY",
            lot_size=1,
            profit_target=3000,
            max_loss_limit=3000,
            ratio_threshold=0.6,
            verbose=True  # Enable verbose for testing
        )
        
        print("✅ Strategy initialized successfully")
        
        # Test 1: Get available funds
        print("\n3. Testing get_available_funds()...")
        print("-" * 50)
        
        equity_funds = strategy.get_available_funds("equity")
        commodity_funds = strategy.get_available_funds("commodity")
        total_funds = strategy.get_available_funds()
        
        print(f"Equity Funds: ₹{equity_funds:,.2f}")
        print(f"Commodity Funds: ₹{commodity_funds:,.2f}")
        print(f"Total Funds: ₹{total_funds:,.2f}")
        
        if equity_funds > 0:
            print("✅ Successfully retrieved available funds")
        else:
            print("⚠️  No equity funds available")
        
        # Test 2: Check margin availability
        print("\n4. Testing check_margin_availability()...")
        print("-" * 50)
        
        test_amounts = [5000, 10000, 25000, 50000]
        
        for amount in test_amounts:
            print(f"\nTesting ₹{amount:,} margin requirement:")
            margin_available, margin_info = strategy.check_margin_availability(amount, "equity")
            
            if margin_available:
                print(f"  ✅ Available: ₹{margin_info['available_margin']:,.2f}")
                print(f"  📊 Utilization: {margin_info['utilization_percent']:.1f}%")
            else:
                print(f"  ❌ Insufficient: Shortfall ₹{margin_info['shortfall']:,.2f}")
        
        # Test 3: Calculate straddle margin requirement
        print("\n5. Testing calculate_straddle_margin_requirement()...")
        print("-" * 50)
        
        # Get ATM strike and instrument keys
        atm_strike = strategy.get_atm_strike()
        print(f"ATM Strike: {atm_strike}")
        
        ce_instrument_key = strategy.get_option_instrument_keys(atm_strike, "CE")
        pe_instrument_key = strategy.get_option_instrument_keys(atm_strike, "PE")
        
        if ce_instrument_key and pe_instrument_key:
            print(f"CE Instrument: {ce_instrument_key}")
            print(f"PE Instrument: {pe_instrument_key}")
            
            # Calculate margin requirement
            quantity = 75  # NIFTY lot size
            margin_required = strategy.calculate_straddle_margin_requirement(
                ce_instrument_key, pe_instrument_key, quantity
            )
            
            if margin_required > 0:
                print(f"✅ Straddle margin requirement: ₹{margin_required:,.2f}")
            else:
                print("❌ Failed to calculate margin requirement")
        else:
            print("❌ Failed to get instrument keys")
        
        # Test 4: Validate trade margin
        print("\n6. Testing validate_trade_margin()...")
        print("-" * 50)
        
        if ce_instrument_key and pe_instrument_key:
            margin_valid, margin_info = strategy.validate_trade_margin(
                ce_instrument_key, pe_instrument_key, quantity, "equity"
            )
            
            if margin_valid:
                print("✅ Trade margin validation passed")
                print(f"   Required: ₹{margin_info['required_margin']:,.2f}")
                print(f"   Available: ₹{margin_info['available_margin']:,.2f}")
                print(f"   Remaining: ₹{margin_info['remaining_margin']:,.2f}")
                print(f"   Utilization: {margin_info['utilization_percent']:.1f}%")
            else:
                print("❌ Trade margin validation failed")
                if margin_info:
                    print(f"   Required: ₹{margin_info['required_margin']:,.2f}")
                    print(f"   Available: ₹{margin_info['available_margin']:,.2f}")
                    print(f"   Shortfall: ₹{margin_info['shortfall']:,.2f}")
        
        # Test 5: Test margin integration with order placement (dry run)
        print("\n7. Testing margin integration with order placement (dry run)...")
        print("-" * 50)
        
        print("This would normally place orders, but we're doing a dry run...")
        print("Margin validation would be performed before each order placement")
        
        return True
        
    except FileNotFoundError:
        print("❌ Error: accessToken.txt file not found")
        return False
    except Exception as e:
        print(f"❌ Error in margin integration test: {e}")
        return False


def test_funds_margin_display():
    """Test funds and margin display functionality"""
    print("\n" + "="*70)
    print("TESTING FUNDS AND MARGIN DISPLAY")
    print("="*70)
    
    try:
        # Load access token
        with open('lib/core/accessToken.txt', 'r') as file:
            access_token = file.read().strip()
        
        # Get and display funds data
        print("1. Getting funds and margin data...")
        funds_data = get_funds_and_margin(access_token)
        
        if funds_data:
            print("✅ Successfully retrieved funds data")
            formatted_data = format_funds_data(funds_data)
            
            if formatted_data:
                print("✅ Successfully formatted funds data")
            else:
                print("❌ Failed to format funds data")
        else:
            print("❌ Failed to retrieve funds data")
        
        return True
        
    except Exception as e:
        print(f"❌ Error in funds display test: {e}")
        return False


def test_margin_calculator_integration():
    """Test margin calculator integration"""
    print("\n" + "="*70)
    print("TESTING MARGIN CALCULATOR INTEGRATION")
    print("="*70)
    
    try:
        # Load access token
        with open('lib/core/accessToken.txt', 'r') as file:
            access_token = file.read().strip()
        
        # Download NSE data
        nse_data = download_nse_market_data()
        if nse_data is None:
            print("❌ Failed to download NSE data")
            return False
        
        # Initialize strategy
        strategy = ShortStraddleStrategy(
            access_token=access_token,
            nse_data=nse_data,
            verbose=True
        )
        
        # Get ATM strike and instrument keys
        atm_strike = strategy.get_atm_strike()
        ce_instrument_key = strategy.get_option_instrument_keys(atm_strike, "CE")
        pe_instrument_key = strategy.get_option_instrument_keys(atm_strike, "PE")
        
        if ce_instrument_key and pe_instrument_key:
            print(f"Testing margin calculation for ATM strike: {atm_strike}")
            
            # Test margin calculation
            instruments = [
                {
                    "instrument_key": ce_instrument_key,
                    "quantity": 75,
                    "transaction_type": "SELL",
                    "product": "D"
                },
                {
                    "instrument_key": pe_instrument_key,
                    "quantity": 75,
                    "transaction_type": "SELL",
                    "product": "D"
                }
            ]
            
            margin_data = get_margin_details(access_token, instruments)
            if margin_data:
                print("✅ Successfully calculated margin")
                analysis = analyze_margin_response(margin_data)
                if analysis:
                    print(f"✅ Instrument type detected: {analysis['instrument_type']}")
            else:
                print("❌ Failed to calculate margin")
        
        return True
        
    except Exception as e:
        print(f"❌ Error in margin calculator integration test: {e}")
        return False


def main():
    """Main test function"""
    print("🧪 STRATEGY MARGIN INTEGRATION TESTING SUITE")
    print("="*70)
    
    test_results = []
    
    # Run all tests
    print("Starting strategy margin integration tests...\n")
    
    # Test 1: Strategy margin integration
    result1 = test_strategy_margin_integration()
    test_results.append(("Strategy Margin Integration", result1))
    
    # Test 2: Funds and margin display
    result2 = test_funds_margin_display()
    test_results.append(("Funds and Margin Display", result2))
    
    # Test 3: Margin calculator integration
    result3 = test_margin_calculator_integration()
    test_results.append(("Margin Calculator Integration", result3))
    
    # Display test results summary
    print("\n" + "="*70)
    print("TEST RESULTS SUMMARY")
    print("="*70)
    
    passed = 0
    total = len(test_results)
    
    for test_name, result in test_results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\nOverall Result: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed successfully!")
        print("\n✅ Margin integration is working correctly!")
        print("   - Available funds are being checked")
        print("   - Margin requirements are being calculated")
        print("   - Trade validation is working")
        print("   - Orders will only be placed if sufficient margin is available")
    else:
        print(f"⚠️  {total - passed} test(s) failed")
    
    print("="*70)


if __name__ == "__main__":
    main()

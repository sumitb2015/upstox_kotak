#!/usr/bin/env python3
"""
Test script for Funds and Margin functionality
Tests all functions in funds_margin.py module
"""

import sys
import os
# Add parent directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.utils.funds_margin import (
    get_funds_and_margin,
    get_equity_funds,
    get_commodity_funds,
    format_funds_data,
    check_margin_availability_for_order,
    get_margin_utilization_summary
)
from lib.utils.margin_calculator import (
    get_margin_details,
    get_option_delivery_margin,
    get_mcx_delivery_margin,
    check_margin_availability,
    analyze_margin_response
)


def test_funds_and_margin_basic():
    """Test basic funds and margin functionality"""
    print("="*70)
    print("TESTING FUNDS AND MARGIN - BASIC FUNCTIONALITY")
    print("="*70)
    
    try:
        # Load access token
        with open('lib/core/accessToken.txt', 'r') as file:
            access_token = file.read().strip()
        
        print("✅ Access token loaded successfully")
        
        # Test 1: Get all funds and margin data
        print("\n1. Testing get_funds_and_margin() - All segments:")
        print("-" * 50)
        funds_data = get_funds_and_margin(access_token)
        
        if funds_data:
            print("✅ Successfully retrieved funds and margin data")
            print(f"Status: {funds_data.get('status', 'Unknown')}")
            
            # Format and display the data
            formatted_data = format_funds_data(funds_data)
            if formatted_data:
                print("✅ Successfully formatted funds data")
            else:
                print("❌ Failed to format funds data")
        else:
            print("❌ Failed to retrieve funds and margin data")
            return False
        
        # Test 2: Get equity funds only
        print("\n2. Testing get_equity_funds() - Equity segment only:")
        print("-" * 50)
        equity_funds = get_equity_funds(access_token)
        
        if equity_funds:
            print("✅ Successfully retrieved equity funds")
            print(f"Equity Available Margin: ₹{equity_funds.get('available_margin', 0):,.2f}")
            print(f"Equity Used Margin: ₹{equity_funds.get('used_margin', 0):,.2f}")
        else:
            print("❌ Failed to retrieve equity funds")
        
        # Test 3: Get commodity funds only
        print("\n3. Testing get_commodity_funds() - Commodity segment only:")
        print("-" * 50)
        commodity_funds = get_commodity_funds(access_token)
        
        if commodity_funds:
            print("✅ Successfully retrieved commodity funds")
            print(f"Commodity Available Margin: ₹{commodity_funds.get('available_margin', 0):,.2f}")
            print(f"Commodity Used Margin: ₹{commodity_funds.get('used_margin', 0):,.2f}")
        else:
            print("❌ Failed to retrieve commodity funds")
        
        return True
        
    except FileNotFoundError:
        print("❌ Error: accessToken.txt file not found")
        return False
    except Exception as e:
        print(f"❌ Error in basic test: {e}")
        return False


def test_margin_availability_checks():
    """Test margin availability checking functionality"""
    print("\n" + "="*70)
    print("TESTING MARGIN AVAILABILITY CHECKS")
    print("="*70)
    
    try:
        # Load access token
        with open('lib/core/accessToken.txt', 'r') as file:
            access_token = file.read().strip()
        
        # Test different margin requirements
        test_amounts = [1000, 5000, 10000, 50000, 100000]
        
        for amount in test_amounts:
            print(f"\nTesting margin availability for ₹{amount:,}:")
            print("-" * 40)
            
            # Test equity segment
            equity_check = check_margin_availability_for_order(access_token, amount, "equity")
            if equity_check:
                status = "✅ Available" if equity_check['margin_available'] else "❌ Insufficient"
                print(f"Equity: {status}")
            
            # Test commodity segment
            commodity_check = check_margin_availability_for_order(access_token, amount, "commodity")
            if commodity_check:
                status = "✅ Available" if commodity_check['margin_available'] else "❌ Insufficient"
                print(f"Commodity: {status}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error in margin availability test: {e}")
        return False


def test_margin_utilization_summary():
    """Test margin utilization summary functionality"""
    print("\n" + "="*70)
    print("TESTING MARGIN UTILIZATION SUMMARY")
    print("="*70)
    
    try:
        # Load access token
        with open('lib/core/accessToken.txt', 'r') as file:
            access_token = file.read().strip()
        
        # Get utilization summary
        summary = get_margin_utilization_summary(access_token)
        
        if summary:
            print("✅ Successfully generated margin utilization summary")
            
            # Display summary details
            print(f"\nEquity Status: {summary['equity']['status']}")
            print(f"Commodity Status: {summary['commodity']['status']}")
            print(f"Total Status: {summary['total']['status']}")
            
            return True
        else:
            print("❌ Failed to generate margin utilization summary")
            return False
        
    except Exception as e:
        print(f"❌ Error in utilization summary test: {e}")
        return False


def test_margin_calculator_integration():
    """Test integration with margin calculator"""
    print("\n" + "="*70)
    print("TESTING MARGIN CALCULATOR INTEGRATION")
    print("="*70)
    
    try:
        # Load access token
        with open('lib/core/accessToken.txt', 'r') as file:
            access_token = file.read().strip()
        
        # Test margin calculation for sample instruments
        print("\n1. Testing NIFTY option margin calculation:")
        print("-" * 50)
        
        # Sample NIFTY option (replace with actual instrument key)
        nifty_instrument = "NSE_FO|54524"  # This might need to be updated with actual key
        nifty_quantity = 75
        
        nifty_margin = get_option_delivery_margin(access_token, nifty_instrument, nifty_quantity, "BUY")
        if nifty_margin:
            print("✅ Successfully calculated NIFTY option margin")
            analyze_margin_response(nifty_margin)
        else:
            print("❌ Failed to calculate NIFTY option margin")
        
        print("\n2. Testing MCX delivery margin calculation:")
        print("-" * 50)
        
        # Sample MCX instrument (replace with actual instrument key)
        mcx_instrument = "MCX_FO|435356"  # This might need to be updated with actual key
        mcx_quantity = 1
        
        mcx_margin = get_mcx_delivery_margin(access_token, mcx_instrument, mcx_quantity, "BUY")
        if mcx_margin:
            print("✅ Successfully calculated MCX delivery margin")
            analyze_margin_response(mcx_margin)
        else:
            print("❌ Failed to calculate MCX delivery margin")
        
        return True
        
    except Exception as e:
        print(f"❌ Error in margin calculator integration test: {e}")
        return False


def test_comprehensive_funds_analysis():
    """Test comprehensive funds analysis"""
    print("\n" + "="*70)
    print("TESTING COMPREHENSIVE FUNDS ANALYSIS")
    print("="*70)
    
    try:
        # Load access token
        with open('lib/core/accessToken.txt', 'r') as file:
            access_token = file.read().strip()
        
        # Get comprehensive funds data
        print("1. Getting comprehensive funds data...")
        funds_data = get_funds_and_margin(access_token)
        
        if not funds_data:
            print("❌ Failed to get funds data")
            return False
        
        # Format and analyze
        formatted_data = format_funds_data(funds_data)
        if not formatted_data:
            print("❌ Failed to format funds data")
            return False
        
        # Get utilization summary
        print("\n2. Getting margin utilization summary...")
        summary = get_margin_utilization_summary(access_token)
        
        if not summary:
            print("❌ Failed to get utilization summary")
            return False
        
        # Test margin availability for different scenarios
        print("\n3. Testing margin availability scenarios...")
        
        # Get available margins
        equity_available = formatted_data.get('equity', {}).get('available_margin', 0)
        commodity_available = formatted_data.get('commodity', {}).get('available_margin', 0)
        total_available = formatted_data.get('totals', {}).get('total_available_margin', 0)
        
        # Test scenarios
        scenarios = [
            {"name": "Small Order (₹1,000)", "amount": 1000},
            {"name": "Medium Order (₹10,000)", "amount": 10000},
            {"name": "Large Order (₹50,000)", "amount": 50000},
            {"name": "Very Large Order (₹100,000)", "amount": 100000}
        ]
        
        for scenario in scenarios:
            print(f"\nTesting {scenario['name']}:")
            print("-" * 30)
            
            # Test equity
            if equity_available > 0:
                equity_check = check_margin_availability_for_order(
                    access_token, scenario['amount'], "equity"
                )
                if equity_check:
                    status = "✅" if equity_check['margin_available'] else "❌"
                    print(f"Equity: {status} {equity_check['utilization_percent']:.1f}% utilization")
            
            # Test commodity
            if commodity_available > 0:
                commodity_check = check_margin_availability_for_order(
                    access_token, scenario['amount'], "commodity"
                )
                if commodity_check:
                    status = "✅" if commodity_check['margin_available'] else "❌"
                    print(f"Commodity: {status} {commodity_check['utilization_percent']:.1f}% utilization")
        
        print("\n✅ Comprehensive funds analysis completed successfully")
        return True
        
    except Exception as e:
        print(f"❌ Error in comprehensive analysis test: {e}")
        return False


def main():
    """Main test function"""
    print("🧪 FUNDS AND MARGIN TESTING SUITE")
    print("="*70)
    
    test_results = []
    
    # Run all tests
    print("Starting funds and margin tests...\n")
    
    # Test 1: Basic functionality
    result1 = test_funds_and_margin_basic()
    test_results.append(("Basic Functionality", result1))
    
    # Test 2: Margin availability checks
    result2 = test_margin_availability_checks()
    test_results.append(("Margin Availability Checks", result2))
    
    # Test 3: Margin utilization summary
    result3 = test_margin_utilization_summary()
    test_results.append(("Margin Utilization Summary", result3))
    
    # Test 4: Margin calculator integration
    result4 = test_margin_calculator_integration()
    test_results.append(("Margin Calculator Integration", result4))
    
    # Test 5: Comprehensive analysis
    result5 = test_comprehensive_funds_analysis()
    test_results.append(("Comprehensive Analysis", result5))
    
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
    else:
        print(f"⚠️  {total - passed} test(s) failed")
    
    print("="*70)


if __name__ == "__main__":
    main()

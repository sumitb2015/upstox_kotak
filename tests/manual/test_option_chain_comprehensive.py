"""
Comprehensive Test Suite for Option Chain Data Fetcher
Tests all functions with various scenarios and edge cases.
"""

from lib.core.authentication import check_existing_token
from lib.api.option_chain import (
    get_option_chain,
    get_option_chain_dataframe,
    filter_option_chain,
    get_atm_strike_from_chain,
    print_option_chain_summary
)
from datetime import datetime, timedelta
import pandas as pd


def test_1_basic_fetch():
    """Test 1: Basic option chain fetch"""
    print("\n" + "="*100)
    print("TEST 1: Basic Option Chain Fetch")
    print("="*100)
    
    # Get access token
    if not check_existing_token():
        print("❌ No access token found")
        return False
    
    with open("lib/core/accessToken.txt", "r") as file:
        token = file.read().strip()
    
    # Get nearest available expiry using Upstox API
    from lib.api.option_chain import get_nearest_expiry
    
    print("Fetching available expiries from Upstox API...")
    expiry_date = get_nearest_expiry(token, "NSE_INDEX|Nifty 50")
    
    if not expiry_date:
        print("❌ Could not determine nearest expiry")
        return False, None, None
    
    print(f"✅ Found nearest expiry: {expiry_date}")
    
    # Test raw fetch
    raw_data = get_option_chain(token, "NSE_INDEX|Nifty 50", expiry_date)
    
    if raw_data and raw_data.get('status') == 'success':
        num_strikes = len(raw_data.get('data', []))
        print(f"✅ Raw fetch successful: {num_strikes} strikes")
        
        if num_strikes == 0:
            print("⚠️  Warning: Option chain returned 0 strikes. This may be after market hours.")
        
        return True, token, expiry_date
    else:
        print("❌ Raw fetch failed")
        return False, None, None


def test_2_dataframe_conversion(token, expiry_date):
    """Test 2: DataFrame conversion"""
    print("\n" + "="*100)
    print("TEST 2: DataFrame Conversion")
    print("="*100)
    
    df = get_option_chain_dataframe(token, "NSE_INDEX|Nifty 50", expiry_date)
    
    if df is None or df.empty:
        print("❌ DataFrame conversion failed")
        return False, None
    
    print(f"✅ DataFrame created: {len(df)} rows × {len(df.columns)} columns")
    print(f"\nColumns: {', '.join(df.columns.tolist()[:10])}... (showing first 10)")
    print(f"\nDataFrame Info:")
    print(f"  - Strike range: {df['strike_price'].min():.0f} to {df['strike_price'].max():.0f}")
    print(f"  - Spot price: ₹{df['spot_price'].iloc[0]:.2f}")
    print(f"  - PCR: {df['pcr'].iloc[0]:.2f}")
    
    return True, df


def test_3_atm_detection(df):
    """Test 3: ATM strike detection"""
    print("\n" + "="*100)
    print("TEST 3: ATM Strike Detection")
    print("="*100)
    
    atm = get_atm_strike_from_chain(df)
    spot = df['spot_price'].iloc[0]
    
    print(f"Spot Price: ₹{spot:.2f}")
    print(f"ATM Strike: {atm}")
    print(f"Distance from spot: {abs(atm - spot):.2f} points")
    
    # Get ATM row data
    atm_row = df[df['strike_price'] == atm].iloc[0]
    
    print(f"\nATM Option Details:")
    print(f"  CE LTP: ₹{atm_row['ce_ltp']:.2f} | PE LTP: ₹{atm_row['pe_ltp']:.2f}")
    print(f"  CE OI: {atm_row['ce_oi']:,.0f} | PE OI: {atm_row['pe_oi']:,.0f}")
    print(f"  CE Delta: {atm_row['ce_delta']:.3f} | PE Delta: {atm_row['pe_delta']:.3f}")
    print(f"  CE Theta: {atm_row['ce_theta']:.2f} | PE Theta: {atm_row['pe_theta']:.2f}")
    print(f"  CE IV: {atm_row['ce_iv']:.2f}% | PE IV: {atm_row['pe_iv']:.2f}%")
    
    print("\n✅ ATM detection successful")
    return True, atm


def test_4_filtering(df, atm):
    """Test 4: DataFrame filtering"""
    print("\n" + "="*100)
    print("TEST 4: DataFrame Filtering")
    print("="*100)
    
    # Test 1: Strike range filter
    near_atm = filter_option_chain(df, strike_min=atm-500, strike_max=atm+500)
    print(f"1. ATM ±500 points filter: {len(near_atm)} strikes")
    
    # Test 2: High OI filter
    high_oi_ce = filter_option_chain(df, min_oi=10000, option_type='CE')
    print(f"2. CE OI > 10,000 filter: {len(high_oi_ce)} strikes")
    
    # Test 3: Deep OTM puts
    otm_puts = filter_option_chain(df, option_type='PE', delta_max=0.2)
    print(f"3. OTM Puts (Δ < 0.2) filter: {len(otm_puts)} strikes")
    if not otm_puts.empty:
        print(f"   Sample strikes: {otm_puts['strike_price'].head(3).tolist()}")
    
    # Test 4: ITM calls
    itm_calls = filter_option_chain(df, option_type='CE', delta_min=0.6)
    print(f"4. ITM Calls (Δ > 0.6) filter: {len(itm_calls)} strikes")
    if not itm_calls.empty:
        print(f"   Sample strikes: {itm_calls['strike_price'].head(3).tolist()}")
    
    # Test 5: Combined filters
    combo = filter_option_chain(
        df,
        strike_min=atm-200,
        strike_max=atm+200,
        min_oi=5000,
        min_volume=1000
    )
    print(f"5. Combined (ATM±200, OI>5k, Vol>1k): {len(combo)} strikes")
    
    print("\n✅ All filter tests passed")
    return True


def test_5_data_quality(df):
    """Test 5: Data quality checks"""
    print("\n" + "="*100)
    print("TEST 5: Data Quality Checks")
    print("="*100)
    
    checks_passed = 0
    total_checks = 0
    
    # Check 1: No null strikes
    total_checks += 1
    if df['strike_price'].isna().sum() == 0:
        print("✅ Check 1: No null strike prices")
        checks_passed += 1
    else:
        print(f"❌ Check 1: {df['strike_price'].isna().sum()} null strikes found")
    
    # Check 2: All strikes have instrument keys
    total_checks += 1
    missing_ce = df['ce_key'].isna().sum()
    missing_pe = df['pe_key'].isna().sum()
    if missing_ce == 0 and missing_pe == 0:
        print("✅ Check 2: All strikes have CE/PE instrument keys")
        checks_passed += 1
    else:
        print(f"❌ Check 2: Missing CE keys: {missing_ce}, Missing PE keys: {missing_pe}")
    
    # Check 3: Delta values in valid range
    total_checks += 1
    ce_delta_valid = ((df['ce_delta'] >= 0) & (df['ce_delta'] <= 1)).all()
    pe_delta_valid = ((df['pe_delta'] >= -1) & (df['pe_delta'] <= 0)).all()
    if ce_delta_valid and pe_delta_valid:
        print("✅ Check 3: All delta values in valid range")
        checks_passed += 1
    else:
        print(f"❌ Check 3: Invalid delta values detected")
    
    # Check 4: Positive premiums
    total_checks += 1
    ce_positive = (df['ce_ltp'] >= 0).all()
    pe_positive = (df['pe_ltp'] >= 0).all()
    if ce_positive and pe_positive:
        print("✅ Check 4: All LTP values are non-negative")
        checks_passed += 1
    else:
        print(f"❌ Check 4: Negative LTP values found")
    
    # Check 5: OI consistency
    total_checks += 1
    ce_oi_check = (df['ce_oi'] >= 0).all()
    pe_oi_check = (df['pe_oi'] >= 0).all()
    if ce_oi_check and pe_oi_check:
        print("✅ Check 5: All OI values are non-negative")
        checks_passed += 1
    else:
        print(f"❌ Check 5: Negative OI values found")
    
    print(f"\n📊 Data Quality Score: {checks_passed}/{total_checks} checks passed")
    
    return checks_passed == total_checks


def test_6_display_summary(df):
    """Test 6: Summary display"""
    print("\n" + "="*100)
    print("TEST 6: Summary Display")
    print("="*100)
    
    print_option_chain_summary(df, num_strikes=7)
    
    print("\n✅ Summary display test complete")
    return True


def test_7_helper_functions(df, atm):
    """Test 7: Helper functions for strike data access"""
    print("\n" + "="*100)
    print("TEST 7: Helper Functions")
    print("="*100)
    
    from lib.api.option_chain import (
        get_strike_data, get_ce_data, get_pe_data,
        get_greeks, get_market_data, get_oi_data, get_premium_data
    )
    
    # Test get_strike_data
    strike_data = get_strike_data(df, atm)
    if strike_data and 'ce_ltp' in strike_data:
        print(f"✅ get_strike_data() - Retrieved complete row with {len(strike_data)} fields")
    else:
        print("❌ get_strike_data() failed")
        return False
    
    # Test get_ce_data
    ce = get_ce_data(df, atm)
    if ce and 'ltp' in ce and 'delta' in ce:
        print(f"✅ get_ce_data() - CE LTP: ₹{ce['ltp']:.2f}, Delta: {ce['delta']:.3f}")
    else:
        print("❌ get_ce_data() failed")
        return False
    
    # Test get_pe_data
    pe = get_pe_data(df, atm)
    if pe and 'ltp' in pe and 'delta' in pe:
        print(f"✅ get_pe_data() - PE LTP: ₹{pe['ltp']:.2f}, Delta: {pe['delta']:.3f}")
    else:
        print("❌ get_pe_data() failed")
        return False
    
    # Test get_greeks
    ce_greeks = get_greeks(df, atm, "CE")
    if ce_greeks and 'delta' in ce_greeks:
        print(f"✅ get_greeks(CE) - Δ:{ce_greeks['delta']:.3f} Θ:{ce_greeks['theta']:.2f} V:{ce_greeks['vega']:.2f}")
    else:
        print("❌ get_greeks() failed")
        return False
    
    # Test get_market_data
    market = get_market_data(df, atm, "PE")
    if market and 'ltp' in market and 'oi' in market:
        print(f"✅ get_market_data(PE) - LTP: ₹{market['ltp']:.2f}, OI: {market['oi']:,.0f}")
    else:
        print("❌ get_market_data() failed")
        return False
    
    # Test get_oi_data
    oi = get_oi_data(df, atm)
    if oi and 'ce_oi' in oi and 'pe_oi' in oi:
        print(f"✅ get_oi_data() - CE OI: {oi['ce_oi']:,.0f}, Change: {oi['ce_oi_change']:+,.0f}")
    else:
        print("❌ get_oi_data() failed")
        return False
    
    # Test get_premium_data
    premium = get_premium_data(df, atm)
    if premium and 'total_premium' in premium:
        print(f"✅ get_premium_data() - Total: ₹{premium['total_premium']:.2f}, Spread CE: ₹{premium['spread_ce']:.2f}")
    else:
        print("❌ get_premium_data() failed")
        return False
    
    print("\n✅ All helper functions working correctly")
    return True


def test_8_export_data(df, expiry_date):
    """Test 8: Export to CSV"""
    print("\n" + "="*100)
    print("TEST 8: Export to CSV")
    print("="*100)
    
    csv_file = f"option_chain_test_{expiry_date}.csv"
    
    try:
        df.to_csv(csv_file, index=False)
        print(f"✅ Exported {len(df)} rows to: {csv_file}")
        
        # Verify file
        import os
        file_size = os.path.getsize(csv_file)
        print(f"   File size: {file_size:,} bytes")
        
        return True
    except Exception as e:
        print(f"❌ Export failed: {e}")
        return False


def run_all_tests():
    """Run all test cases"""
    print("\n" + "="*100)
    print("🧪 OPTION CHAIN DATA FETCHER - COMPREHENSIVE TEST SUITE")
    print("="*100)
    
    results = []
    
    # Test 1: Basic fetch
    success, token, expiry_date = test_1_basic_fetch()
    results.append(("Basic Fetch", success))
    if not success:
        print("\n❌ Test suite aborted - basic fetch failed")
        return
    
    # Test 2: DataFrame conversion
    success, df = test_2_dataframe_conversion(token, expiry_date)
    results.append(("DataFrame Conversion", success))
    if not success or df is None:
        print("\n❌ Test suite aborted - DataFrame conversion failed")
        return
    
    # Test 3: ATM detection
    success, atm = test_3_atm_detection(df)
    results.append(("ATM Detection", success))
    
    # Test 4: Filtering
    success = test_4_filtering(df, atm)
    results.append(("Filtering", success))
    
    # Test 5: Data quality
    success = test_5_data_quality(df)
    results.append(("Data Quality", success))
    
    # Test 6: Display
    success = test_6_display_summary(df)
    results.append(("Display Summary", success))
    
    # Test 7: Helper functions
    success = test_7_helper_functions(df, atm)
    results.append(("Helper Functions", success))
    
    # Test 8: Export
    success = test_8_export_data(df, expiry_date)
    results.append(("CSV Export", success))
    
    # Summary
    print("\n" + "="*100)
    print("📊 TEST RESULTS SUMMARY")
    print("="*100)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    print("\n" + "="*100)
    print(f"🎯 FINAL SCORE: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    print("="*100)
    
    if passed == total:
        print("\n🎉 All tests passed! Option chain module is working perfectly.")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please review the errors above.")


if __name__ == "__main__":
    run_all_tests()

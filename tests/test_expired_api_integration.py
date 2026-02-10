"""
Integration test for expired API functions.

This test demonstrates the workflow:
1. Fetch expiries for Nifty 50
2. Fetch option contracts for a specific expiry
3. Find ATM strike and filter contracts
4. Fetch historical candles for a specific instrument
"""

import sys
import os

# Add root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.core.authentication import get_access_token
from lib.api.expired_data import (
    get_expired_expiry_dates,
    get_expired_option_contracts,
    get_expired_historical_candles,
    find_atm_strike,
    get_contract_by_criteria,
    filter_contracts_by_moneyness
)


def test_expired_api_workflow():
    """Test the complete expired API workflow"""
    
    # Get access token
    access_token = get_access_token()
    if not access_token:
        print("❌ No access token available. Please authenticate first.")
        return
    
    print("✅ Access token loaded\n")
    
    # Step 1: Fetch expiries
    print("=" * 60)
    print("STEP 1: Fetching expiries for Nifty 50")
    print("=" * 60)
    
    expiries = get_expired_expiry_dates(
        access_token,
        "NSE_INDEX|Nifty 50",
        from_date="2024-10-01",
        to_date="2024-12-31"
    )
    
    print(f"Found {len(expiries)} expiries")
    print(f"Sample: {expiries[:5]}\n")
    
    if not expiries:
        print("❌ No expiries found. Exiting.")
        return
    
    # Step 2: Fetch option contracts for first expiry
    test_expiry = expiries[0]
    print("=" * 60)
    print(f"STEP 2: Fetching option contracts for {test_expiry}")
    print("=" * 60)
    
    contracts = get_expired_option_contracts(
        access_token,
        "NSE_INDEX|Nifty 50",
        test_expiry
    )
    
    if not contracts:
        print("❌ No contracts found. Exiting.")
        return
    
    print(f"Found {len(contracts)} contracts")
    print(f"Sample contract: {contracts[0]}\n")
    
    # Step 3: Find ATM strike (assuming spot was around 25000)
    print("=" * 60)
    print("STEP 3: Finding ATM strike and filtering")
    print("=" * 60)
    
    test_spot = 25000
    atm_strike = find_atm_strike(contracts, test_spot)
    print(f"ATM Strike for spot {test_spot}: {atm_strike}")
    
    # Get specific contract
    ce_contract = get_contract_by_criteria(contracts, atm_strike, 'CE')
    pe_contract = get_contract_by_criteria(contracts, atm_strike, 'PE')
    
    if ce_contract:
        print(f"ATM CE: {ce_contract['trading_symbol']} - {ce_contract['instrument_key']}")
    if pe_contract:
        print(f"ATM PE: {pe_contract['trading_symbol']} - {pe_contract['instrument_key']}")
    
    # Filter by moneyness (0-5% OTM)
    otm_contracts = filter_contracts_by_moneyness(contracts, test_spot, 0, 5)
    print(f"\nContracts within 0-5% OTM: {len(otm_contracts)}\n")
    
    # Step 4: Fetch historical candles
    if ce_contract:
        print("=" * 60)
        print("STEP 4: Fetching historical candles")
        print("=" * 60)
        
        instrument_key = ce_contract['instrument_key']
        print(f"Instrument: {instrument_key}")
        
        # Fetch 1-minute candles for the expiry date
        candles_df = get_expired_historical_candles(
            access_token,
            instrument_key,
            '1minute',
            test_expiry,  # from_date
            test_expiry,  # to_date (same day)
            return_dataframe=True
        )
        
        if candles_df is not None and not candles_df.empty:
            print(f"\n✅ Fetched {len(candles_df)} candles")
            print("\nFirst 5 candles:")
            print(candles_df.head())
            print("\nLast 5 candles:")
            print(candles_df.tail())
        else:
            print("❌ No candles found")
    
    print("\n" + "=" * 60)
    print("✅ TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    test_expired_api_workflow()

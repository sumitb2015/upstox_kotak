"""
Option Chain Data Fetcher Module

Fetch full option chain data for NIFTY or any underlying symbol
and provide it as a pandas DataFrame for use in strategies.
"""

import upstox_client
from upstox_client.rest import ApiException
import pandas as pd
from typing import Optional, Dict, List
import logging

# Configure logger
logger = logging.getLogger(__name__)

def _get_api_client(access_token):
    configuration = upstox_client.Configuration()
    configuration.access_token = access_token
    return upstox_client.ApiClient(configuration)

def get_expiries(access_token: str, instrument_key: str = "NSE_INDEX|Nifty 50") -> Optional[List[str]]:
    """
    Get all available expiry dates for an instrument using Upstox SDK.
    """
    api_instance = upstox_client.OptionsApi(_get_api_client(access_token))
    
    try:
        # SDK method to get option contracts
        api_response = api_instance.get_option_contracts(instrument_key=instrument_key)
        
        # api_response.data is a list of contract objects
        if api_response.data:
            expiries = set()
            for contract in api_response.data:
                # Access attributes directly on the object
                if hasattr(contract, 'expiry') and contract.expiry:
                    expiries.add(contract.expiry)
            return sorted(list(expiries))
        else:
            return []
            
    except ApiException as e:
        logger.error(f"ApiException fetching expiries: {e}")
        return None
    except Exception as e:
        logger.error(f"Error fetching expiries: {e}")
        return None


def get_nearest_expiry(access_token: str, instrument_key: str = "NSE_INDEX|Nifty 50") -> Optional[str]:
    """
    Get the nearest available expiry date for an instrument.
    """
    expiries = get_expiries(access_token, instrument_key)
    
    if expiries and len(expiries) > 0:
        return expiries[0]
    else:
        print(f"❌ No expiries found for {instrument_key}")
        return None


def get_option_chain(access_token: str, instrument_key: str, expiry_date: str) -> Optional[Dict]:
    """
    Fetch raw option chain data from Upstox API using SDK.
    Using get_put_call_option_chain for consistency.
    """
    api_instance = upstox_client.OptionsApi(_get_api_client(access_token))
    
    try:
        api_response = api_instance.get_put_call_option_chain(instrument_key, expiry_date)
        
        # Structure result to match previous return format (dict with 'data' key)
        # The SDK returns a wrapper with .data which is a list.
        # However, the previous implementation used v2/option/chain which returned a specific structure.
        # We need to adapt the SDK response to match what the consumers expect, OR update consumers.
        # Currently, consumers expect 'data' key with list of strike objects.
        
        if api_response.status == "success":
             # We can return the dict representation of the response
             return api_response.to_dict()
        return None
        
    except ApiException as e:
        logger.error(f"ApiException fetching option chain: {e}")
        return None
    except Exception as e:
        logger.error(f"Error fetching option chain: {e}")
        return None


def get_option_chain_dataframe(access_token: str, instrument_key: str, expiry_date: str) -> Optional[pd.DataFrame]:
    """
    Fetch option chain and return as a flattened pandas DataFrame.
    """
    chain_data = get_option_chain(access_token, instrument_key, expiry_date)
    
    if not chain_data or 'data' not in chain_data:
        return None
    
    # Flatten the nested structure
    # The SDK to_dict() response structure matches the V2 API JSON structure closely
    rows = []
    for strike_data in chain_data['data']:
        # strike_data is a dict here because we called to_dict() earlier
        row = {
            'strike_price': strike_data.get('strike_price'),
            'spot_price': strike_data.get('underlying_spot_price'),
            'pcr': strike_data.get('pcr'),
            'expiry': strike_data.get('expiry'),
            'underlying_key': strike_data.get('underlying_key'),
        }
        
        # Extract Call Option data
        call_opt = strike_data.get('call_options', {})
        row['ce_key'] = call_opt.get('instrument_key')
        
        call_market = call_opt.get('market_data', {})
        row['ce_ltp'] = call_market.get('ltp')
        row['ce_volume'] = call_market.get('volume')
        row['ce_oi'] = call_market.get('oi')
        row['ce_prev_oi'] = call_market.get('prev_oi')
        row['ce_close'] = call_market.get('close_price')
        row['ce_bid'] = call_market.get('bid_price')
        row['ce_ask'] = call_market.get('ask_price')
        row['ce_bid_qty'] = call_market.get('bid_qty')
        row['ce_ask_qty'] = call_market.get('ask_qty')
        
        call_greeks = call_opt.get('option_greeks', {})
        row['ce_delta'] = call_greeks.get('delta')
        row['ce_theta'] = call_greeks.get('theta')
        row['ce_gamma'] = call_greeks.get('gamma')
        row['ce_vega'] = call_greeks.get('vega')
        row['ce_iv'] = call_greeks.get('iv')
        row['ce_pop'] = call_greeks.get('pop')
        
        # Extract Put Option data
        put_opt = strike_data.get('put_options', {})
        row['pe_key'] = put_opt.get('instrument_key')
        
        put_market = put_opt.get('market_data', {})
        row['pe_ltp'] = put_market.get('ltp')
        row['pe_volume'] = put_market.get('volume')
        row['pe_oi'] = put_market.get('oi')
        row['pe_prev_oi'] = put_market.get('prev_oi')
        row['pe_close'] = put_market.get('close_price')
        row['pe_bid'] = put_market.get('bid_price')
        row['pe_ask'] = put_market.get('ask_price')
        row['pe_bid_qty'] = put_market.get('bid_qty')
        row['pe_ask_qty'] = put_market.get('ask_qty')
        
        put_greeks = put_opt.get('option_greeks', {})
        row['pe_delta'] = put_greeks.get('delta')
        row['pe_theta'] = put_greeks.get('theta')
        row['pe_gamma'] = put_greeks.get('gamma')
        row['pe_vega'] = put_greeks.get('vega')
        row['pe_iv'] = put_greeks.get('iv')
        row['pe_pop'] = put_greeks.get('pop')
        
        rows.append(row)
    
    df = pd.DataFrame(rows)
    
    # Sort by strike price
    if not df.empty:
        df = df.sort_values('strike_price').reset_index(drop=True)
    
    return df


def filter_option_chain(df: pd.DataFrame, 
                       strike_min: Optional[float] = None,
                       strike_max: Optional[float] = None,
                       min_oi: Optional[int] = None,
                       min_volume: Optional[int] = None,
                       delta_min: Optional[float] = None,
                       delta_max: Optional[float] = None,
                       option_type: Optional[str] = None) -> pd.DataFrame:
    """
    Filter option chain DataFrame based on various criteria.
    """
    filtered = df.copy()
    
    # Strike price filters
    if strike_min is not None:
        filtered = filtered[filtered['strike_price'] >= strike_min]
    if strike_max is not None:
        filtered = filtered[filtered['strike_price'] <= strike_max]
    
    # Open Interest filters
    if min_oi is not None:
        if option_type == 'CE':
            filtered = filtered[filtered['ce_oi'] >= min_oi]
        elif option_type == 'PE':
            filtered = filtered[filtered['pe_oi'] >= min_oi]
        else:
            filtered = filtered[(filtered['ce_oi'] >= min_oi) | (filtered['pe_oi'] >= min_oi)]
    
    # Volume filters
    if min_volume is not None:
        if option_type == 'CE':
            filtered = filtered[filtered['ce_volume'] >= min_volume]
        elif option_type == 'PE':
            filtered = filtered[filtered['pe_volume'] >= min_volume]
        else:
            filtered = filtered[(filtered['ce_volume'] >= min_volume) | (filtered['pe_volume'] >= min_volume)]
    
    # Delta filters (use absolute value for comparison)
    if delta_min is not None or delta_max is not None:
        if 'ce_delta' in filtered.columns and 'pe_delta' in filtered.columns:
            if option_type == 'CE':
                if delta_min is not None:
                    filtered = filtered[filtered['ce_delta'].abs() >= delta_min]
                if delta_max is not None:
                    filtered = filtered[filtered['ce_delta'].abs() <= delta_max]
            elif option_type == 'PE':
                if delta_min is not None:
                    filtered = filtered[filtered['pe_delta'].abs() >= delta_min]
                if delta_max is not None:
                    filtered = filtered[filtered['pe_delta'].abs() <= delta_max]
            else:
                if delta_min is not None:
                    filtered = filtered[(filtered['ce_delta'].abs() >= delta_min) | (filtered['pe_delta'].abs() >= delta_min)]
                if delta_max is not None:
                    filtered = filtered[(filtered['ce_delta'].abs() <= delta_max) | (filtered['pe_delta'].abs() <= delta_max)]
    
    return filtered.reset_index(drop=True)


def get_atm_strike_from_chain(df: pd.DataFrame) -> Optional[int]:
    """Find ATM Strike"""
    if df.empty:
        return None
    
    spot_price = df['spot_price'].iloc[0]
    
    # Find closest strike to spot
    df['distance_from_spot'] = (df['strike_price'] - spot_price).abs()
    atm_row = df.loc[df['distance_from_spot'].idxmin()]
    
    return int(atm_row['strike_price'])


def print_option_chain_summary(df: pd.DataFrame, num_strikes: int = 10):
    """Print summary"""
    if df.empty:
        print("❌ Option chain is empty")
        return
    
    atm = get_atm_strike_from_chain(df)
    spot = df['spot_price'].iloc[0]
    
    print("\n" + "="*100)
    print(f"📊 OPTION CHAIN SUMMARY - {df['underlying_key'].iloc[0]}")
    print(f"Expiry: {df['expiry'].iloc[0]} | Spot: ₹{spot:.2f} | ATM: {atm} | PCR: {df['pcr'].iloc[0]:.2f}")
    print("="*100)
    
    # Get strikes around ATM
    # Filter for valid rows only
    if not df[df['strike_price'] == atm].empty:
        atm_idx = df[df['strike_price'] == atm].index[0]
        start_idx = max(0, atm_idx - num_strikes)
        end_idx = min(len(df), atm_idx + num_strikes + 1)
        
        display_df = df.iloc[start_idx:end_idx].copy()
        
        # Format for display
        print(f"\n{'Strike':>7} | {'CE LTP':>8} {'CE OI':>10} {'CE Δ':>7} | {'PE LTP':>8} {'PE OI':>10} {'PE Δ':>7}")
        print("-" * 100)
        
        for _, row in display_df.iterrows():
            strike = int(row['strike_price'])
            marker = " ATM" if strike == atm else ""
            
            ce_ltp = row.get('ce_ltp', 0) or 0
            ce_oi = row.get('ce_oi', 0) or 0
            ce_delta = row.get('ce_delta', 0) or 0
            pe_ltp = row.get('pe_ltp', 0) or 0
            pe_oi = row.get('pe_oi', 0) or 0
            pe_delta = row.get('pe_delta', 0) or 0
            
            print(f"{strike:>7}{marker:>4} | "
                  f"₹{ce_ltp:>7.2f} {ce_oi:>10,.0f} {ce_delta:>7.3f} | "
                  f"₹{pe_ltp:>7.2f} {pe_oi:>10,.0f} {pe_delta:>7.3f}")
    
    print("="*100)


def get_strike_data(df: pd.DataFrame, strike: int) -> Optional[Dict]:
    """Get all data for a specific strike."""
    if df.empty: return None
    strike_row = df[df['strike_price'] == strike]
    if strike_row.empty: return None
    return strike_row.iloc[0].to_dict()


def get_ce_data(df: pd.DataFrame, strike: int) -> Optional[Dict]:
    """Get Call Option data for a specific strike."""
    strike_data = get_strike_data(df, strike)
    if not strike_data: return None
    
    return {
        'instrument_key': strike_data.get('ce_key'),
        'ltp': strike_data.get('ce_ltp'),
        'volume': strike_data.get('ce_volume'),
        'oi': strike_data.get('ce_oi'),
        'prev_oi': strike_data.get('ce_prev_oi'),
        'close': strike_data.get('ce_close'),
        'bid': strike_data.get('ce_bid'),
        'ask': strike_data.get('ce_ask'),
        'bid_qty': strike_data.get('ce_bid_qty'),
        'ask_qty': strike_data.get('ce_ask_qty'),
        'delta': strike_data.get('ce_delta'),
        'theta': strike_data.get('ce_theta'),
        'gamma': strike_data.get('ce_gamma'),
        'vega': strike_data.get('ce_vega'),
        'iv': strike_data.get('ce_iv'),
        'pop': strike_data.get('ce_pop')
    }


def get_pe_data(df: pd.DataFrame, strike: int) -> Optional[Dict]:
    """Get Put Option data for a specific strike."""
    strike_data = get_strike_data(df, strike)
    if not strike_data: return None
    
    return {
        'instrument_key': strike_data.get('pe_key'),
        'ltp': strike_data.get('pe_ltp'),
        'volume': strike_data.get('pe_volume'),
        'oi': strike_data.get('pe_oi'),
        'prev_oi': strike_data.get('pe_prev_oi'),
        'close': strike_data.get('pe_close'),
        'bid': strike_data.get('pe_bid'),
        'ask': strike_data.get('pe_ask'),
        'bid_qty': strike_data.get('pe_bid_qty'),
        'ask_qty': strike_data.get('pe_ask_qty'),
        'delta': strike_data.get('pe_delta'),
        'theta': strike_data.get('pe_theta'),
        'gamma': strike_data.get('pe_gamma'),
        'vega': strike_data.get('pe_vega'),
        'iv': strike_data.get('pe_iv'),
        'pop': strike_data.get('pe_pop')
    }


def get_greeks(df: pd.DataFrame, strike: int, option_type: str = "CE") -> Optional[Dict]:
    """Get option Greeks."""
    option_type = option_type.upper()
    if option_type == "CE":
        data = get_ce_data(df, strike)
    elif option_type == "PE":
        data = get_pe_data(df, strike)
    else:
        return None
    
    if not data: return None
    
    return {
        'delta': data.get('delta'),
        'theta': data.get('theta'),
        'gamma': data.get('gamma'),
        'vega': data.get('vega'),
        'iv': data.get('iv'),
        'pop': data.get('pop')
    }


def get_market_data(df: pd.DataFrame, strike: int, option_type: str = "CE") -> Optional[Dict]:
    """Get market data."""
    option_type = option_type.upper()
    if option_type == "CE":
        data = get_ce_data(df, strike)
    elif option_type == "PE":
        data = get_pe_data(df, strike)
    else:
        return None
    
    if not data: return None
    
    return {
        'instrument_key': data.get('instrument_key'),
        'ltp': data.get('ltp'),
        'volume': data.get('volume'),
        'oi': data.get('oi'),
        'prev_oi': data.get('prev_oi'),
        'close': data.get('close'),
        'bid': data.get('bid'),
        'ask': data.get('ask'),
        'bid_qty': data.get('bid_qty'),
        'ask_qty': data.get('ask_qty')
    }


def get_oi_data(df: pd.DataFrame, strike: int) -> Optional[Dict]:
    """Get OI data."""
    strike_data = get_strike_data(df, strike)
    if not strike_data: return None
    
    ce_oi = strike_data.get('ce_oi') or 0
    pe_oi = strike_data.get('pe_oi') or 0
    ce_prev_oi = strike_data.get('ce_prev_oi') or 0
    pe_prev_oi = strike_data.get('pe_prev_oi') or 0
    
    return {
        'ce_oi': ce_oi,
        'pe_oi': pe_oi,
        'ce_prev_oi': ce_prev_oi,
        'pe_prev_oi': pe_prev_oi,
        'ce_oi_change': ce_oi - ce_prev_oi,
        'pe_oi_change': pe_oi - pe_prev_oi,
        'pcr': strike_data.get('pcr')
    }


def get_premium_data(df: pd.DataFrame, strike: int) -> Optional[Dict]:
    """Get premium data."""
    strike_data = get_strike_data(df, strike)
    if not strike_data: return None
    
    ce_ltp = strike_data.get('ce_ltp') or 0
    pe_ltp = strike_data.get('pe_ltp') or 0
    ce_bid = strike_data.get('ce_bid') or 0
    ce_ask = strike_data.get('ce_ask') or 0
    pe_bid = strike_data.get('pe_bid') or 0
    pe_ask = strike_data.get('pe_ask') or 0
    
    return {
        'ce_ltp': ce_ltp,
        'pe_ltp': pe_ltp,
        'ce_bid': ce_bid,
        'ce_ask': ce_ask,
        'pe_bid': pe_bid,
        'pe_ask': pe_ask,
        'total_premium': ce_ltp + pe_ltp,
        'spread_ce': ce_ask - ce_bid,
        'spread_pe': pe_ask - pe_bid
    }


def get_atm_iv(df: pd.DataFrame) -> float:
    """Get ATM IV."""
    try:
        atm_strike = get_atm_strike_from_chain(df)
        if atm_strike:
            greeks_ce = get_greeks(df, atm_strike, "CE")
            if greeks_ce and greeks_ce.get('iv'):
                return greeks_ce['iv']
            
            greeks_pe = get_greeks(df, atm_strike, "PE")
            if greeks_pe and greeks_pe.get('iv'):
                return greeks_pe['iv']
    except Exception as e:
        print(f"⚠️ Could not retrieve ATM IV: {e}")
    
    return 15.0


def calculate_pcr(df: pd.DataFrame) -> float:
    """
    Calculate Total Put-Call Ratio (PCR) from Option Chain.
    PCR = Total Put OI / Total Call OI
    
    Args:
        df (pd.DataFrame): Option Chain DataFrame (must contain 'ce_oi' and 'pe_oi')
        
    Returns:
        float: Total PCR value
    """
    if df.empty:
        return 0.0
        
    try:
        total_pe_oi = df['pe_oi'].sum()
        total_ce_oi = df['ce_oi'].sum()
        
        if total_ce_oi == 0:
            return 0.0
            
        return round(total_pe_oi / total_ce_oi, 4)
    except Exception as e:
        print(f"Error calculating PCR: {e}")
        return 0.0

def calculate_volume_pcr(df: pd.DataFrame) -> float:
    """
    Calculate Total Volume Put-Call Ratio (PCR).
    PCR = Total Put Volume / Total Call Volume
    """
    if df.empty:
        return 0.0
    try:
        total_pe_vol = df['pe_volume'].sum()
        total_ce_vol = df['ce_volume'].sum()
        if total_ce_vol == 0:
            return 0.0
        return round(total_pe_vol / total_ce_vol, 4)
    except Exception as e:
        print(f"Error calculating Volume PCR: {e}")
        return 0.0

def calculate_oi_change_pcr(df: pd.DataFrame) -> float:
    """
    Calculate Total OI Change Put-Call Ratio (PCR).
    PCR = Total Put OI Change / Total Call OI Change
    """
    if df.empty:
        return 0.0
    try:
        pe_chg = (df['pe_oi'] - df['pe_prev_oi']).sum()
        ce_chg = (df['ce_oi'] - df['ce_prev_oi']).sum()
        if ce_chg == 0:
            return 0.0
        return round(pe_chg / ce_chg, 4)
    except Exception as e:
        print(f"Error calculating OI Change PCR: {e}")
        return 0.0

def calculate_max_pain(df: pd.DataFrame) -> Dict:
    """
    Calculate Max Pain Strike and Total Pain Table.
    
    Max Pain is the strike price at which the total value of all options 
    (Calls + Puts) expires worthless (or minimal value).
    
    Algorithm:
    1. For each unique strike in the chain (potential spot price at expiry):
       a. Calculate loss for Call Writers: max(0, PotentialSpot - Strike) * CE_OI
       b. Calculate loss for Put Writers:  max(0, Strike - PotentialSpot) * PE_OI
       c. Total Pain = Sum(Call Pain) + Sum(Put Pain) for ALL strikes against this PotentialSpot
    2. The strike with the MINIMUM Total Pain is the Max Pain Strike.
    """
    if df.empty:
        return {"max_pain_strike": 0, "pain_data": []}
    
    try:
        # Ensure minimal columns exist
        required = ['strike_price', 'ce_oi', 'pe_oi']
        for col in required:
            if col not in df.columns:
                return {"max_pain_strike": 0, "pain_data": []}
                
        # Get unique strikes and sort them
        strikes = sorted(df['strike_price'].unique())
        
        pain_data = [] # List of {strike: <potential_spot>, total_pain: <val>, ce_pain: <val>, pe_pain: <val>}
        
        # Pre-calculate data for faster access (vectorization would be better but loops are fine for <100 strikes)
        ce_ois = df.set_index('strike_price')['ce_oi'].to_dict()
        pe_ois = df.set_index('strike_price')['pe_oi'].to_dict()
        
        for potential_spot in strikes:
            total_ce_pain = 0.0
            total_pe_pain = 0.0
            
            # Calculate pain for THIS potential spot against ALL outstanding contracts
            for k in strikes:
                # Call Pain: Value if Spot > Strike
                if potential_spot > k:
                    total_ce_pain += (potential_spot - k) * ce_ois.get(k, 0)
                    
                # Put Pain: Value if Spot < Strike
                if potential_spot < k:
                    total_pe_pain += (k - potential_spot) * pe_ois.get(k, 0)
            
            pain_data.append({
                "strike": potential_spot,
                "total_pain": total_ce_pain + total_pe_pain,
                "ce_pain": total_ce_pain,
                "pe_pain": total_pe_pain
            })
            
        # Find Strike with Minimum Total Pain
        if not pain_data:
            return {"max_pain_strike": 0, "pain_data": []}
            
        min_pain_entry = min(pain_data, key=lambda x: x['total_pain'])
        
        return {
            "max_pain_strike": min_pain_entry['strike'],
            "pain_data": pain_data
        }
        
    except Exception as e:
        logger.error(f"Error calculating Max Pain: {e}")
        return {"max_pain_strike": 0, "pain_data": []}

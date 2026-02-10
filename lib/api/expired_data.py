from datetime import datetime
import requests
import pandas as pd
from typing import Optional, List, Dict, Union


def make_request(method: str, url: str, headers: dict = None, params: dict = None, data: dict = None) -> Optional[dict]:
    """
    Generic HTTP request helper with error handling.
    
    Args:
        method: HTTP method (GET, POST, PUT)
        url: Request URL
        headers: Request headers
        params: Query parameters
        data: Request body (for POST/PUT)
    
    Returns:
        JSON response dict if successful, None otherwise
    """
    try:
        if method == 'GET':
            response = requests.get(url, headers=headers, params=params)
        elif method == 'POST':
            response = requests.post(url, headers=headers, params=params, json=data)
        elif method == 'PUT':
            response = requests.put(url, headers=headers, params=params, json=data)
        else:
            raise ValueError(f'Invalid HTTP method: {method}')
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ API Error ({response.status_code}): {response.text}")
            return None
    
    except Exception as e:
        print(f"❌ Request failed: {e}")
        return None

def get_expired_expiry_dates(
    access_token: str, 
    instrument_key: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    sort_ascending: bool = True
) -> List[str]:
    """
    Fetch available expired expiry dates for an instrument.
    
    Endpoint: /v2/expired-instruments/expiries
    
    Args:
        access_token: API Access Token
        instrument_key: e.g., "NSE_INDEX|Nifty 50"
        from_date: Optional filter - only return expiries >= this date (YYYY-MM-DD)
        to_date: Optional filter - only return expiries <= this date (YYYY-MM-DD)
        sort_ascending: Sort dates ascending (default True)
    
    Returns:
        List of expiry date strings in YYYY-MM-DD format
    """
    url = "https://api.upstox.com/v2/expired-instruments/expiries"
    params = {'instrument_key': instrument_key}
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {access_token}'
    }
    
    response = make_request('GET', url, headers=headers, params=params)
    if not response or response.get('status') != 'success':
        return []
    
    expiries = response.get('data', [])
    
    # Apply date filtering
    if from_date:
        expiries = [e for e in expiries if e >= from_date]
    if to_date:
        expiries = [e for e in expiries if e <= to_date]
    
    # Sort
    expiries.sort(reverse=not sort_ascending)
    
    return expiries

def get_expired_option_contracts(
    access_token: str, 
    underlying_key: str, 
    expiry_date: str,
    min_strike: Optional[float] = None,
    max_strike: Optional[float] = None,
    option_type: Optional[str] = None
) -> Optional[List[Dict]]:
    """
    Fetch expired option contracts for a specific underlying and expiry date.
    
    Endpoint: /v2/expired-instruments/option/contract
    
    Args:
        access_token: API Access Token
        underlying_key: e.g., "NSE_INDEX|Nifty 50"
        expiry_date: YYYY-MM-DD
        min_strike: Optional minimum strike price filter
        max_strike: Optional maximum strike price filter
        option_type: Optional filter - 'CE' or 'PE' only
    
    Returns:
        List of contract dictionaries containing 'instrument_key', 'strike_price', etc.
    """
    url = "https://api.upstox.com/v2/expired-instruments/option/contract"
    
    params = {
        'instrument_key': underlying_key,
        'expiry_date': expiry_date
    }
    
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {access_token}'
    }
    
    response = make_request('GET', url, headers=headers, params=params)
    if not response or response.get('status') != 'success':
        return None
    
    contracts = response.get('data', [])
    
    # Apply filters
    if min_strike is not None:
        contracts = [c for c in contracts if c.get('strike_price', 0) >= min_strike]
    if max_strike is not None:
        contracts = [c for c in contracts if c.get('strike_price', 0) <= max_strike]
    if option_type:
        contracts = [c for c in contracts if c.get('instrument_type') == option_type]
    
    return contracts

def get_expired_future_contracts(
    access_token: str, 
    underlying_key: str, 
    expiry_date: str
) -> Optional[List[Dict]]:
    """
    Fetch expired future contracts.
    """
    url = "https://api.upstox.com/v2/expired-instruments/future/contract"
    
    params = {
        'instrument_key': underlying_key,
        'expiry_date': expiry_date
    }
    
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {access_token}'
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200 and response.json().get('status') == 'success':
            return response.json().get('data', [])
        return None
    except Exception as e:
        print(f"❌ Exception fetching expired futures: {e}")
        return None

def get_expired_historical_candles(
    access_token: str,
    instrument_key: str,
    interval: str,
    from_date: str,
    to_date: str,
    return_dataframe: bool = False
) -> Union[Optional[List[Dict]], Optional[pd.DataFrame]]:
    """
    Fetch historical candle data for an EXPIRED instrument.
    
    Endpoint: /v2/expired-instruments/historical-candle/{instrument_key}/{interval}/{to_date}/{from_date}
    
    Args:
        access_token: API Access Token
        instrument_key: Full instrument key (e.g., 'NSE_FO|58423|03-10-2024')
        interval: '1minute', '5minute', '30minute', 'day', 'week', 'month'
        from_date: Start date YYYY-MM-DD
        to_date: End date YYYY-MM-DD
        return_dataframe: If True, return pandas DataFrame instead of list
    
    Returns:
        List of candle dicts or DataFrame with columns: timestamp, open, high, low, close, volume, oi
    """
    # Normalize interval format
    interval_map = {
        '1min': '1minute',
        '5min': '5minute',
        '15min': '15minute',
        '30min': '30minute',
        '60min': '60minute',
        '1minute': '1minute',
        '5minute': '5minute',
        '15minute': '15minute',
        '30minute': '30minute',
        '60minute': '60minute',
        'day': 'day',
        'week': 'week',
        'month': 'month'
    }
    
    normalized_interval = interval_map.get(interval.lower(), interval)
    
    # URL Path: .../{instrument_key}/{interval}/{to_date}/{from_date}
    # Note: Upstox puts TO date before FROM date in the URL path
    url = f"https://api.upstox.com/v2/expired-instruments/historical-candle/{instrument_key}/{normalized_interval}/{to_date}/{from_date}"
    
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {access_token}'
    }
    
    response = make_request('GET', url, headers=headers)
    if not response or response.get('status') != 'success':
        return pd.DataFrame() if return_dataframe else None
    
    candles = response.get('data', {}).get('candles', [])
    
    if not candles:
        return pd.DataFrame() if return_dataframe else []
    
    # Format candles
    formatted = []
    for c in candles:
        formatted.append({
            'timestamp': c[0],
            'open': c[1],
            'high': c[2],
            'low': c[3],
            'close': c[4],
            'volume': c[5],
            'oi': c[6] if len(c) > 6 else 0
        })
    
    # Sort ascending by timestamp
    formatted.sort(key=lambda x: x['timestamp'])
    
    if return_dataframe:
        df = pd.DataFrame(formatted)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df
    
    return formatted


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def find_atm_strike(contracts: List[Dict], spot_price: float) -> Optional[float]:
    """
    Find the At-The-Money (ATM) strike price closest to spot price.
    
    Args:
        contracts: List of contract dictionaries
        spot_price: Current spot price
    
    Returns:
        ATM strike price, or None if no contracts
    """
    if not contracts:
        return None
    
    strikes = sorted(set(c.get('strike_price', 0) for c in contracts))
    
    # Find closest strike to spot
    atm_strike = min(strikes, key=lambda x: abs(x - spot_price))
    return atm_strike


def get_contract_by_criteria(
    contracts: List[Dict],
    strike: float,
    option_type: str
) -> Optional[Dict]:
    """
    Find a specific contract by strike and option type.
    
    Args:
        contracts: List of contract dictionaries
        strike: Strike price
        option_type: 'CE' or 'PE'
    
    Returns:
        Contract dict or None if not found
    """
    for contract in contracts:
        if (abs(contract.get('strike_price', 0) - strike) < 0.1 and
            contract.get('instrument_type') == option_type):
            return contract
    return None


def filter_contracts_by_moneyness(
    contracts: List[Dict],
    spot_price: float,
    min_pct_otm: float = 0,
    max_pct_otm: float = 100
) -> List[Dict]:
    """
    Filter contracts by moneyness (Out-of-The-Money percentage).
    
    Args:
        contracts: List of contract dictionaries
        spot_price: Current spot price
        min_pct_otm: Minimum OTM percentage (0 = ATM)
        max_pct_otm: Maximum OTM percentage
    
    Returns:
        Filtered list of contracts
    """
    filtered = []
    
    for contract in contracts:
        strike = contract.get('strike_price', 0)
        opt_type = contract.get('instrument_type')
        
        if opt_type == 'CE':
            # For CE, OTM when strike > spot
            otm_pct = ((strike - spot_price) / spot_price) * 100
        elif opt_type == 'PE':
            # For PE, OTM when strike < spot
            otm_pct = ((spot_price - strike) / spot_price) * 100
        else:
            continue
        
        if min_pct_otm <= otm_pct <= max_pct_otm:
            filtered.append(contract)
    
    return filtered

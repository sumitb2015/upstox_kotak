import requests
import pandas as pd
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import urllib.parse as urlparse

def get_historical_data(access_token: str, instrument_key: str, interval: str, lookback_minutes: int) -> Optional[List[Dict]]:
    """
    Fetch historical candle data using Upstox V3 API logic.
    Wrapper for backward compatibility calling V3 function.
    """
    to_date = datetime.now()
    # Ensure we go back at least 2 days to handle weekends/holidays
    from_date = to_date - timedelta(days=2)
    
    # Map V2 interval strings to V3 unit/value
    unit = "minute"
    value = 1
    
    if "minute" in interval:
        try:
            val_str = interval.replace("minute", "")
            value = int(val_str) if val_str else 1
            unit = "minutes"
        except:
            pass
    elif interval == "day":
        unit = "day"
    elif interval == "week":
        unit = "week"
    elif interval == "month":
        unit = "month"
        
    return get_historical_data_v3(
        access_token, 
        instrument_key, 
        unit, 
        value, 
        from_date.strftime('%Y-%m-%d'), 
        to_date.strftime('%Y-%m-%d')
    )

def get_historical_range(access_token: str, instrument_key: str, interval: str, from_date: str, to_date: str) -> Optional[List[Dict]]:
    """
    Fetch historical data range using Upstox V3 API logic.
    """
    # Map V2 interval strings to V3 unit/value
    unit = "minutes" # Default
    value = 1
    
    if "minute" in interval:
        try:
            val_str = interval.replace("minute", "")
            value = int(val_str) if val_str else 1
        except: pass
    elif interval == "day":
        unit = "days" 

        
    return get_historical_data_v3(
        access_token, 
        instrument_key, 
        unit, 
        value, 
        from_date, 
        to_date
    )

def get_historical_data_v3(access_token: str, instrument_key: str, interval_unit: str, interval_value: int, from_date: str, to_date: str) -> Optional[List[Dict]]:
    """
    Fetch historical candle data using Upstox V3 API.
    
    V3 Endpoint Structure (from https://upstox.com/developer/api-documentation/v3/get-historical-candle-data):
    GET /v2/historical-candle/{instrument_key}/{interval_unit}/{interval_value}/{to_date}/{from_date}
    
    Args:
        access_token: Upstox API access token
        instrument_key: Instrument key (e.g., "NSE_INDEX|Nifty 50")
        interval_unit: Unit of interval - "minute", "day", "week", "month"
        interval_value: Value of interval - e.g., 1, 5, 15, 30, 60
        from_date: Start date in YYYY-MM-DD format
        to_date: End date in YYYY-MM-DD format
        
    Returns:
        List of candle dictionaries or None if failed
        
    Note: V3 uses /v2/ base URL but with different path structure than V2
    """
    
    # V3 uses /v2/ base but with unit/interval structure - Wait, previous testing showed v3 base worked
    # Reverting to v3 base as v2 caused 404
    
    # Fix Unit Mapping (minute -> minutes)
    if interval_unit == "minute":
        interval_unit = "minutes"
        
    encoded_symbol = urlparse.quote(instrument_key, safe='')
    url = f"https://api.upstox.com/v3/historical-candle/{encoded_symbol}/{interval_unit}/{interval_value}/{to_date}/{from_date}"
    
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {access_token}'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"❌ V3 API Error ({response.status_code}): {response.text}")
            return None
            
        data = response.json()
        if data.get('status') == 'success':
            candles = data.get('data', {}).get('candles', [])
            formatted_data = []
            for candle in candles:
                formatted_data.append({
                    'timestamp': candle[0],
                    'open': candle[1],
                    'high': candle[2],
                    'low': candle[3],
                    'close': candle[4],
                    'volume': candle[5],
                    'oi': candle[6] if len(candle) > 6 else 0
                })
            formatted_data.sort(key=lambda x: x['timestamp'])
            return formatted_data
        else:
            print(f"❌ V3 API Response: {data}")
            return None
    except Exception as e:
        print(f"❌ Exception in get_historical_data_v3: {e}")
        import traceback
        traceback.print_exc()
        return None

def get_intraday_data_v3(access_token: str, instrument_key: str, interval_unit: str, interval_value: int) -> Optional[List[Dict]]:
    """
    Fetch INTRADAY candle data using Upstox V3 API.
    
    Endpoint: https://api.upstox.com/v3/historical-candle/intraday/{instrument_key}/{unit}/{interval}
    
    Args:
        access_token: Upstox API access token
        instrument_key: Instrument key
        interval_unit: Unit - "minute" (only suffix 's' if needed, but docs say 'minute' for path?)
                       Browser research says: /minutes/5
                       Let's try 'minutes'
        interval_value: Value - e.g. 1, 5
        
    Returns:
        List of candles for the CURRENT DAY
    """
    # Use 'minutes' as per browser research finding
    unit = interval_unit
    if unit == "minute": unit = "minutes"
    
    encoded_symbol = urlparse.quote(instrument_key, safe='')
    url = f"https://api.upstox.com/v3/historical-candle/intraday/{encoded_symbol}/{unit}/{interval_value}"
    
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {access_token}'
    }
    
    try:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.get(url, headers=headers, timeout=15)
                if response.status_code == 429:
                    # Rate limited — wait and retry
                    retry_after = int(response.headers.get('Retry-After', 2))
                    print(f"⚠️ [UPSTOX] Rate limited on {instrument_key}. Waiting {retry_after}s...")
                    time.sleep(retry_after)
                    continue
                if response.status_code != 200:
                    print(f"❌ Intraday V3 API Error ({response.status_code}): {response.text}")
                    return None
                    
                data = response.json()
                if data.get('status') == 'success':
                    candles = data.get('data', {}).get('candles', [])
                    formatted_data = []
                    for candle in candles:
                        formatted_data.append({
                            'timestamp': candle[0],
                            'open': candle[1],
                            'high': candle[2],
                            'low': candle[3],
                            'close': candle[4],
                            'volume': candle[5],
                            'oi': candle[6] if len(candle) > 6 else 0
                        })
                    # Sort ascending
                    formatted_data.sort(key=lambda x: x['timestamp'])
                    return formatted_data
                else:
                    print(f"❌ Intraday V3 API Response: {data}")
                    return None
            except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as conn_err:
                wait = 2 ** attempt  # 1s, 2s, 4s
                if attempt < max_retries - 1:
                    print(f"⚠️ [UPSTOX] Connection error on {instrument_key} (attempt {attempt+1}/{max_retries}). Retrying in {wait}s... [{conn_err}]")
                    time.sleep(wait)
                else:
                    print(f"❌ [UPSTOX] Max retries exceeded for {instrument_key}: {conn_err}")
                    return None
        return None
    except Exception as e:
        print(f"❌ Exception in get_intraday_data_v3: {e}")
        return None

def get_expired_historical_data(access_token: str, instrument_key: str, expiry_date: str, interval: str, from_date: str, to_date: str) -> Optional[List[Dict]]:
    """
    Fetch historical candle data for EXPIRED instruments.
    This is the only endpoint that reliably returns Open Interest (OI) for option history.
    
    Endpoint: https://api.upstox.com/v2/historical-candle/expired/{instrument_key}/{interval}/{to_date}/{from_date}
    """
    import upstox_client
    from upstox_client.rest import ApiException
    
    configuration = upstox_client.Configuration()
    configuration.access_token = access_token
    
    # Map intervals
    if interval == "minute": interval = "1minute"
    elif interval == "day": interval = "day"
    
    try:
        api_client = upstox_client.ApiClient(configuration)
        expired_api = upstox_client.ExpiredInstrumentApi(api_client)
        
        # Note: instrument_key for expired usually includes expiry suffix e.g. NSE_FO|42391|10-02-2026
        api_response = expired_api.get_expired_historical_candle_data(
            expired_instrument_key=instrument_key,
            interval=interval,
            to_date=to_date,
            from_date=from_date
        )
        
        if api_response.status == 'success' and api_response.data.candles:
            formatted_data = []
            for candle in api_response.data.candles:
                formatted_data.append({
                    'timestamp': candle[0],
                    'open': candle[1],
                    'high': candle[2],
                    'low': candle[3],
                    'close': candle[4],
                    'volume': candle[5],
                    'oi': candle[6] if len(candle) > 6 else 0
                })
            # Sort ascending
            formatted_data.sort(key=lambda x: x['timestamp'])
            return formatted_data
        return None
    except Exception as e:
        print(f"❌ Exception in get_expired_historical_data: {e}")
        return None

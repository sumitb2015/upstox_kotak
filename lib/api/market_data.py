import requests as rq
import pandas as pd
import requests
import upstox_client
from upstox_client.rest import ApiException
import math
from datetime import datetime
from typing import List, Dict, Optional, Union
import io
import gzip

def _get_api_client(access_token):
    configuration = upstox_client.Configuration()
    configuration.access_token = access_token
    return upstox_client.ApiClient(configuration)

def download_nse_market_data():
    """Download and process NSE market data from static file"""
    print("Downloading NSE market data...")
    
    try:
        # Download NSE instruments data using requests (Static file, not API)
        url = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
        response = rq.get(url, stream=True, timeout=10)
        response.raise_for_status()
        
        # Decompress the gzipped data
        with gzip.GzipFile(fileobj=io.BytesIO(response.content)) as gz_file:
            json_data = gz_file.read().decode('utf-8')
        
        # Load data using json module first for safety
        import json
        data = json.loads(json_data)
        
        # Determine structure and create DataFrame
        if isinstance(data, list):
            df = pd.DataFrame(data)
        elif isinstance(data, dict):
            # Try finding the list in keys like 'data', 'params', etc if wrapped
            found_list = None
            for key in ['data', 'instruments', 'result']:
                if key in data and isinstance(data[key], list):
                    found_list = data[key]
                    break
            
            if found_list:
                df = pd.DataFrame(found_list)
            else:
                # Fallback: Treat dict values as rows if applicable
                df = pd.DataFrame([data])
        else:
            print("Unknown JSON structure for NSE data")
            return None

        print(f"NSE market data loaded successfully. Shape: {df.shape}")
        return df
        
    except rq.exceptions.RequestException as e:
        print(f"Error downloading NSE data: {e}")
        return None
    except Exception as e:
        print(f"Error processing NSE data: {e}")
        return None

def get_market_holidays(access_token):
    """Fetch market holidays using Upstox SDK"""
    print("Fetching market holidays...")
    
    try:
        api_instance = upstox_client.MarketHolidaysAndTimingsApi(_get_api_client(access_token))
        
        api_response = api_instance.get_holidays()
        
        print("Market Holidays:")
        if api_response.data:
            for holiday in api_response.data:
                print(f"Holiday: {holiday}")
            return api_response.data
        return []
        
    except Exception as e:
        print(f"Error fetching market holidays: {e}")
        return None

def _fetch_option_chain_data(access_token, underlying_key, expiry):
    """Helper function to fetch raw option chain data from SDK"""
    api_instance = upstox_client.OptionsApi(_get_api_client(access_token))

    try:
        # SDK method get_put_call_option_chain
        api_response = api_instance.get_put_call_option_chain(underlying_key, expiry)
        if not api_response.data:
            print("No option chain data found.")
            return None, None
        return api_response.data, api_response.data[0].underlying_spot_price
    except ApiException as e:
        print("Exception when calling OptionsApi: %s\n" % e)
        return None, None

def _process_option_chain_data(api_data, spot_price, min_strike, max_strike):
    """Helper function to process and flatten option chain data"""
    option_chain_list = []
    
    for item in api_data:
        strike_price = item.strike_price
        if strike_price < min_strike or strike_price > max_strike:
            continue

        # Call option
        if item.call_options:
            call = item.call_options
            call_market = call.market_data
            call_greeks = call.option_greeks
            
            option_chain_list.append({
                "type": "call",
                "instrument_type": "CE",
                "strike_price": strike_price,
                "expiry": item.expiry,
                "underlying": item.underlying_key,
                "underlying_spot": item.underlying_spot_price,
                "pcr": item.pcr,
                "instrument_key": call.instrument_key,
                "ltp": call_market.ltp if call_market else 0,
                "prev_ltp": call_market.close_price if call_market else 0,
                "bid_price": call_market.bid_price if call_market else 0,
                "ask_price": call_market.ask_price if call_market else 0,
                "volume": call_market.volume if call_market else 0,
                "oi": call_market.oi if call_market else 0,
                "prev_oi": call_market.prev_oi if call_market else 0,
                "delta": call_greeks.delta if call_greeks else 0,
                "gamma": call_greeks.gamma if call_greeks else 0,
                "theta": call_greeks.theta if call_greeks else 0,
                "vega": call_greeks.vega if call_greeks else 0,
                "iv": call_greeks.iv if call_greeks else 0,
                "pop": call_greeks.pop if call_greeks else 0,
            })

        # Put option
        if item.put_options:
            put = item.put_options
            put_market = put.market_data
            put_greeks = put.option_greeks
            
            option_chain_list.append({
                "type": "put",
                "instrument_type": "PE",
                "strike_price": strike_price,
                "expiry": item.expiry,
                "underlying": item.underlying_key,
                "underlying_spot": item.underlying_spot_price,
                "pcr": item.pcr,
                "instrument_key": put.instrument_key,
                "ltp": put_market.ltp if put_market else 0,
                "prev_ltp": put_market.close_price if put_market else 0,
                "bid_price": put_market.bid_price if put_market else 0,
                "ask_price": put_market.ask_price if put_market else 0,
                "volume": put_market.volume if put_market else 0,
                "oi": put_market.oi if put_market else 0,
                "prev_oi": put_market.prev_oi if put_market else 0,
                "delta": put_greeks.delta if put_greeks else 0,
                "gamma": put_greeks.gamma if put_greeks else 0,
                "theta": put_greeks.theta if put_greeks else 0,
                "vega": put_greeks.vega if put_greeks else 0,
                "iv": put_greeks.iv if put_greeks else 0,
                "pop": put_greeks.pop if put_greeks else 0,
            })

    # Create and sort DataFrame
    df_option_chain = pd.DataFrame(option_chain_list)
    if not df_option_chain.empty:
        df_option_chain = df_option_chain.sort_values(
            ["strike_price", "type"]
        ).reset_index(drop=True)
    
    return df_option_chain

def get_filtered_option_chain(
    access_token, underlying_key, expiry, strikes_above=10, strikes_below=10
):
    """Fetch and filter the option chain from SDK"""
    # Fetch data
    api_data, spot_price = _fetch_option_chain_data(access_token, underlying_key, expiry)
    if api_data is None:
        return pd.DataFrame()

    # Calculate strike range based on spot price
    min_strike = spot_price - strikes_below * 50
    max_strike = spot_price + strikes_above * 50

    # Process and return data
    return _process_option_chain_data(api_data, spot_price, min_strike, max_strike)

def get_option_chain_atm(
    access_token,
    underlying_key,
    expiry,
    strikes_above=10,
    strikes_below=10,
    strike_interval=50,
):
    """Fetch and filter option chain for ATM ± strikes from SDK"""
    # Fetch data
    api_data, spot_price = _fetch_option_chain_data(access_token, underlying_key, expiry)
    if api_data is None:
        return pd.DataFrame()

    # Calculate ATM strike and range
    atm_strike = round(spot_price / strike_interval) * strike_interval
    min_strike = atm_strike - strikes_below * strike_interval
    max_strike = atm_strike + strikes_above * strike_interval

    # Process and return data
    return _process_option_chain_data(api_data, spot_price, min_strike, max_strike)


def fetch_historical_data(access_token, symbol, interval_type, interval, start_date, end_date):
    """Fetch historical candle data using SDK HistoryApi"""
    print(f"Fetching historical data for {symbol} from {start_date} to {end_date}")
    
    api_instance = upstox_client.HistoryApi(_get_api_client(access_token))
    
    # Convert datetime objects to strings if needed
    if isinstance(start_date, datetime):
        start_date = start_date.strftime("%Y-%m-%d")
    if isinstance(end_date, datetime):
        end_date = end_date.strftime("%Y-%m-%d")
    
    # Ensure start_date is before end_date
    if pd.to_datetime(start_date) > pd.to_datetime(end_date):
        start_date, end_date = end_date, start_date
    
    try:
        # Construct interval string appropriately
        # Upstox API expects: '1minute', '30minute', 'day', 'week', 'month'
        
        # Check if type involves day/week/month (ignore the number '1')
        if 'day' in interval_type or 'week' in interval_type or 'month' in interval_type:
             # Strip 's' just in case (e.g. 'days' -> 'day')
             formatted_interval = interval_type.rstrip('s')
        else:
             # Ensure singular 'minute' if it was passed as 'minutes'
             unit = interval_type.rstrip('s')
             formatted_interval = f"{interval}{unit}" # e.g. '1minute'
        
        api_response = api_instance.get_historical_candle_data1(
            instrument_key=symbol, 
            interval=formatted_interval, 
            to_date=end_date, 
            from_date=start_date, 
            api_version="2.0"
        )
        
        candles = api_response.data.candles
        if not candles:
            print(f"No candle data for {symbol}")
            return pd.DataFrame()
        
        # Create DataFrame
        df = pd.DataFrame(
            candles,
            columns=["timestamp", "open", "high", "low", "close", "volume", "oi"],
        )
        
        # Convert timestamp and remove timezone
        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize(None)
        
        # Add symbol column and sort
        df["symbol"] = symbol
        df = df.sort_values("timestamp").reset_index(drop=True)
        
        print(f"Successfully fetched {len(df)} candles for {symbol}")
        return df
        
    except ApiException as e:
        print(f"API Exception when fetching data for {symbol}: {e}")
        return pd.DataFrame()
    except Exception as e:
        print(f"Exception when fetching data for {symbol}: {e}")
        return pd.DataFrame()

def get_option_expiry_dates(access_token, underlying_key):
    """Fetch expiry dates using SDK OptionsApi"""
    api_instance = upstox_client.OptionsApi(_get_api_client(access_token))
    
    try:
        api_response = api_instance.get_option_contracts(instrument_key=underlying_key)
        
        if api_response.data:
            expiries = set()
            for contract in api_response.data:
                if contract.expiry:
                    expiries.add(contract.expiry)
            return sorted(list(expiries))
        return []
        
    except ApiException as e:
        print(f"API Error fetching expiries: {e}")
        return None

def get_market_status():
    """Manual market status check"""
    # Simple fallback check
    now = datetime.now()
    if now.weekday() >= 5: # Sat/Sun
        return "CLOSED"
    
    start_time = now.replace(hour=9, minute=15, second=0, microsecond=0)
    end_time = now.replace(hour=15, minute=30, second=0, microsecond=0)
    
    if start_time <= now <= end_time:
        return "OPEN"
    else:
        return "CLOSED"

def get_expired_option_contracts(access_token, instrument_key, expiry_date):
    """Get expired options using SDK"""
    api_instance = upstox_client.OptionsApi(_get_api_client(access_token))
    try:
        api_response = api_instance.get_option_contracts(instrument_key=instrument_key, expiry_date=expiry_date)
        if api_response.status == 'success':
            return api_response.data
        return None
    except ApiException as e:
        print(f"Error fetching expired options: {e}")
        return None

def get_expired_future_contracts(access_token, instrument_key):
    """Get expired futures using SDK"""
    api_instance = upstox_client.OptionsApi(_get_api_client(access_token))
    try:
        api_response = api_instance.get_future_contracts(instrument_key)
        return api_response.data
    except ApiException as e:
        print(f"Error fetching expired futures: {e}")
        return None

def get_market_quotes(access_token, instrument_keys):
    """
    Fetch market quotes (LTP) using SDK MarketQuoteApi.
    """
    # Join keys for batch request
    keys_str = ",".join(instrument_keys)
    
    api_instance = upstox_client.MarketQuoteApi(_get_api_client(access_token))
    
    try:
        # SDK supports get_full_market_quote with symbol which can be comma-separated
        api_response = api_instance.get_full_market_quote(symbol=keys_str, api_version='2.0')
        
        if api_response.status == 'success':
            # Returns a dict where keys are instrument keys
            # We need to convert objects to dicts
            data = {}
            for key, quote in api_response.data.items():
                data[key] = quote.to_dict()
            return data
        return {}
            
    except ApiException as e:
        print(f"Error fetching quotes: {e}")
        return {}

def get_market_quote_for_instrument(access_token, instrument_key):
    """
    Fetch full quote for a single instrument and handle key mapping.
    """
    quotes = get_market_quotes(access_token, [instrument_key])
    
    # 1. Direct Lookup
    if instrument_key in quotes:
        return quotes[instrument_key]
        
    # 2. Heuristic Lookup
    for key, data in quotes.items():
        response_token = str(data.get('instrument_token', ''))
        
        if response_token == instrument_key or response_token == instrument_key.split('|')[-1]:
            return data
            
        if key == instrument_key.replace('|', ':'):
            return data

    return None

def get_vwap(access_token, instrument_key):
    """Get VWAP from market quote"""
    quote = get_market_quote_for_instrument(access_token, instrument_key)
    if quote:
        # Upstox V2 field is 'average_price'
        return quote.get('average_price', 0.0)
    return 0.0

def get_ltp(access_token, instrument_key):
    """
    Get Last Traded Price (LTP) for an instrument.
    Wrapper around get_market_quote_for_instrument.
    """
    quote = get_market_quote_for_instrument(access_token, instrument_key)
    if quote:
        # Upstox V2 uses 'last_price' or 'ltp' depending on feed type?
        # MarketQuoteApi returns object with 'last_price'
        # our helper converts to dict.
        # Let's check keys. Typically 'last_price' in REST API.
        return quote.get('last_price', 0.0)

    return 0.0

def get_option_contracts(access_token, instrument_key, expiry_date=None):
    """
    Get option contracts for an instrument key.
    
    Args:
        access_token (str): Upstox Access Token
        instrument_key (str): Underlying instrument key (e.g., 'NSE_INDEX|Nifty 50')
        expiry_date (str, optional): Filter by expiry date (YYYY-MM-DD)
        
    Returns:
        list: List of option contracts or None
    """
    url = 'https://api.upstox.com/v2/option/contract'
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {access_token}'
    }
    params = {'instrument_key': instrument_key}
    
    if expiry_date:
        params['expiry_date'] = expiry_date
        
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        
        if data.get('status') == 'success':
            return data.get('data')
        return None
        
    except requests.RequestException as e:
        print(f"Error fetching option contracts: {e}")
        return None

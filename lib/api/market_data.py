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
import threading
from concurrent.futures import ThreadPoolExecutor

# --- Global Cache for Previous Last Open Interest ---
# Key: instrument_key, Value: prev_oi (float)
PREV_OI_CACHE: Dict[str, float] = {}
_prefetch_executor = ThreadPoolExecutor(max_workers=2)  # Global executor (Reduced to 2 for stability)
_prefetch_lock = threading.Lock()
# Set to track keys currently being fetched to prevent duplicate tasks
FETCH_IN_PROGRESS = set()
FETCH_PROGRESS_LOCK = threading.Lock()


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


def _prefetch_prev_oi_background(access_token, keys):
    """
    Background worker to fetch historical OI for keys missing in cache.
    """
    missing_keys = [k for k in keys if k not in PREV_OI_CACHE]
    if not missing_keys:
        return

    # print(f"⏳ Prefetching historical OI for {len(missing_keys)} contracts...")
    
    # Calculate dates (last 5 days to be safe)
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - pd.Timedelta(days=7)).strftime("%Y-%m-%d")

    def fetch_single(key):
        try:
            # We want DAY candles
            hist_df = fetch_historical_data(access_token, key, "day", 1, start_date, end_date)
            if not hist_df.empty:
                # Logic: same as indices prev close
                # If last candle is today, we want the one before it
                last_row = hist_df.iloc[-1]
                last_date = pd.to_datetime(last_row['timestamp']).date()
                today_date = datetime.now().date()
                
                prev_oi_val = 0
                if last_date == today_date:
                    if len(hist_df) > 1:
                        prev_oi_val = hist_df.iloc[-2]['oi']
                    else:
                        # Only today's candle exists (new contract?), assume 0 prev OI or take today's open OI?
                        # Taking today's open OI is safer than 0 if available, but hist_df has 'open', 'high'... 'oi' is usually closing OI.
                        # If truly new, prev_oi is 0.
                        prev_oi_val = 0 
                else:
                    prev_oi_val = last_row['oi']
                
                with _prefetch_lock:
                    PREV_OI_CACHE[key] = float(prev_oi_val)
                    
        except Exception as e:
            # print(f"Failed to fetch history for {key}: {e}")
            pass
        finally:
            with FETCH_PROGRESS_LOCK:
                if key in FETCH_IN_PROGRESS:
                    FETCH_IN_PROGRESS.remove(key)

    # Submit tasks to executor
    with FETCH_PROGRESS_LOCK:
        for key in missing_keys:
            if key not in FETCH_IN_PROGRESS:
                FETCH_IN_PROGRESS.add(key)
                _prefetch_executor.submit(fetch_single, key)


def get_full_option_chain(access_token, underlying_key, expiry):
    """
    Fetch the COMPLETE option chain (all strikes) and calculate Build Up & Top OI.
    Includes logic to prefetch historical OI for accurate % change.
    """
    # Fetch data
    api_data, spot_price = _fetch_option_chain_data(access_token, underlying_key, expiry)
    if api_data is None:
        return pd.DataFrame()

    # Process all data (No strike filter)
    df = _process_option_chain_data(api_data, spot_price, 0, float('inf'))
    
    if df.empty:
        return df

    # --- 1. Trigger Background Prefetch for missing previous OI ---
    # Extract all instrument keys (CE and PE)
    all_keys = []
    if 'instrument_key' in df.columns:
        all_keys = df['instrument_key'].tolist()
    
    # Fire and forget mechanism
    # We verify if we have keys to fetch. If so, start a daemon thread to submit to executor
    # This prevents blocking the main thread even for submitting tasks
    threading.Thread(target=_prefetch_prev_oi_background, args=(access_token, all_keys), daemon=True).start()

    # --- 2. Enrich with Cached Previous OI ---
    # If we have cached values, override the API's prev_oi (which might be 0 or broken)
    
    def get_cached_prev_oi(row):
        key = row['instrument_key']
        # If Key in Cache, use it. Else use API's prev_oi
        if key in PREV_OI_CACHE:
             return PREV_OI_CACHE[key]
        return row['prev_oi']

    if 'instrument_key' in df.columns:
        # Vectorized map is faster than apply if possible, but dict lookup needs map/apply
        # Use map logic
        df['prev_oi'] = df.apply(get_cached_prev_oi, axis=1)

    # --- Calculate Build Up ---
    # Long Buildup: Price > Prev, OI > Prev
    # Short Buildup: Price < Prev, OI > Prev
    # Short Covering: Price > Prev, OI < Prev
    # Long Unwinding: Price < Prev, OI < Prev
    
    def get_buildup(row):
        price_up = row['ltp'] > row['prev_ltp']
        oi_up = row['oi'] > row['prev_oi']
        
        if price_up and oi_up: return "Long Buildup"
        if not price_up and oi_up: return "Short Buildup"
        if price_up and not oi_up: return "Short Covering"
        if not price_up and not oi_up: return "Long Unwinding"
        return "Neutral"

    df['buildup'] = df.apply(get_buildup, axis=1)

    # --- 3. Enrich with OHLC from MarketQuotes ---
    if all_keys:
        ohlc_map = {}
        chunk_size = 400
        for i in range(0, len(all_keys), chunk_size):
            chunk = all_keys[i:i+chunk_size]
            try:
                quotes = get_market_quotes(access_token, chunk)
                for k, quote_dict in quotes.items():
                    # USE instrument_token because it matches instrument_key (like NSE_FO|45414)
                    # whereas k might be a different format like NSE_FO:NIFTY...
                    token_key = quote_dict.get('instrument_token')
                    if token_key and 'ohlc' in quote_dict and quote_dict['ohlc']:
                        ohlc_map[token_key] = quote_dict['ohlc']
            except Exception as e:
                print(f"Error fetching quotes for OHLC: {e}")
                
        def get_open(row): return ohlc_map.get(row['instrument_key'], {}).get('open', 0)
        def get_high(row): return ohlc_map.get(row['instrument_key'], {}).get('high', 0)
        def get_low(row): return ohlc_map.get(row['instrument_key'], {}).get('low', 0)
        
        df['open'] = df.apply(get_open, axis=1)
        df['high'] = df.apply(get_high, axis=1)
        df['low'] = df.apply(get_low, axis=1)

    return df


def fetch_historical_data(access_token, symbol, interval_type, interval, start_date, end_date):
    """Fetch historical candle data using SDK HistoryApi"""
    # print(f"Fetching historical data for {symbol} from {start_date} to {end_date}")
    
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
        
        # FIX: Ensure we suppress print for background prefetching to avoid console spam
        # Or just keep it. 
        
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
        
        # print(f"Successfully fetched {len(df)} candles for {symbol}")
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

def get_expired_expiries(access_token, instrument_key):
    """Fetch list of past expiry dates for an instrument"""
    api_instance = upstox_client.ExpiredInstrumentApi(_get_api_client(access_token))
    try:
        api_response = api_instance.get_expiries(instrument_key)
        if api_response.status == 'success':
            return api_response.data
        return []
    except ApiException as e:
        print(f"Error fetching expired expiries: {e}")
        return []

def get_expired_option_contracts(access_token, instrument_key, expiry_date):
    """Get expired options using SDK"""
    api_instance = upstox_client.ExpiredInstrumentApi(_get_api_client(access_token))
    try:
        api_response = api_instance.get_expired_option_contracts(instrument_key=instrument_key, expiry_date=expiry_date)
        if api_response.status == 'success':
            return api_response.data
        return None
    except ApiException as e:
        print(f"Error fetching expired options: {e}")
        return None

def get_expired_future_contracts(access_token, instrument_key):
    """Get expired futures using SDK"""
    api_instance = upstox_client.ExpiredInstrumentApi(_get_api_client(access_token))
    try:
        api_response = api_instance.get_expired_future_contracts(instrument_key)
        if api_response.status == 'success':
            return api_response.data
        return []
    except ApiException as e:
        print(f"Error fetching expired futures: {e}")
        return []

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

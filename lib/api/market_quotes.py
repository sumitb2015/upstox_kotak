import upstox_client
from upstox_client.rest import ApiException
import requests
import pandas as pd


def get_full_market_quote(access_token, symbol, api_version="2.0"):
    """
    Get full market quote for a given symbol.
    
    Args:
        access_token (str): The access token obtained from Token API
        symbol (str): The instrument symbol (e.g., 'NSE_FO|47762')
        api_version (str): API version, defaults to "2.0"
    
    Returns:
        dict: Market quote data containing price, depth, OHLC, OI, etc.
    """
    configuration = upstox_client.Configuration()
    configuration.access_token = f"{access_token}"
    
    api_instance = upstox_client.MarketQuoteApi(upstox_client.ApiClient(configuration))
    
    try:
        api_response = api_instance.get_full_market_quote(symbol, api_version)
        return api_response.data
    except ApiException as e:
        print(f"Exception when calling MarketQuoteApi->get_full_market_quote: {e}")
        return None


def get_multiple_market_quotes(access_token, instrument_keys, api_version="2.0"):
    """
    Get full market quotes for multiple symbols.
    
    Args:
        access_token (str): The access token
        instrument_keys (list): List of instrument keys
        api_version (str): API version
    
    Returns:
        dict: Market quote data for all instruments
    """
    symbols = ",".join(instrument_keys)
    return get_full_market_quote(access_token, symbols, api_version)


def extract_market_quote_data(quote_data):
    """
    Extract market quote data into a dictionary format for computation.
    
    Args:
        quote_data (dict): Market quote data from get_full_market_quote
    
    Returns:
        dict: Structured market quote data for computation
    """
    if not quote_data:
        return None
    
    extracted_data = {}
    
    for symbol_key, data in quote_data.items():
        # Extract basic data
        symbol_data = {
            'symbol': getattr(data, 'symbol', 'N/A'),
            'instrument_token': getattr(data, 'instrument_token', 'N/A'),
            'last_price': getattr(data, 'last_price', 0),
            'average_price': getattr(data, 'average_price', 0),
            'net_change': getattr(data, 'net_change', 0),
            'volume': getattr(data, 'volume', 0),
            'oi': getattr(data, 'oi', 0),
            'oi_day_high': getattr(data, 'oi_day_high', 0),
            'oi_day_low': getattr(data, 'oi_day_low', 0),
            'total_buy_quantity': getattr(data, 'total_buy_quantity', 0),
            'total_sell_quantity': getattr(data, 'total_sell_quantity', 0),
            'upper_circuit_limit': getattr(data, 'upper_circuit_limit', 0),
            'lower_circuit_limit': getattr(data, 'lower_circuit_limit', 0),
            'timestamp': getattr(data, 'timestamp', 'N/A')
        }
        
        # Extract OHLC data
        ohlc = getattr(data, 'ohlc', None)
        if ohlc:
            symbol_data['ohlc'] = {
                'open': getattr(ohlc, 'open', 0),
                'high': getattr(ohlc, 'high', 0),
                'low': getattr(ohlc, 'low', 0),
                'close': getattr(ohlc, 'close', 0)
            }
        else:
            symbol_data['ohlc'] = None
        
        # Extract market depth data
        depth = getattr(data, 'depth', None)
        if depth:
            buy_orders = getattr(depth, 'buy', [])
            sell_orders = getattr(depth, 'sell', [])
            
            symbol_data['depth'] = {
                'buy': [
                    {
                        'price': getattr(order, 'price', 0),
                        'quantity': getattr(order, 'quantity', 0),
                        'orders': getattr(order, 'orders', 0)
                    } for order in buy_orders
                ],
                'sell': [
                    {
                        'price': getattr(order, 'price', 0),
                        'quantity': getattr(order, 'quantity', 0),
                        'orders': getattr(order, 'orders', 0)
                    } for order in sell_orders
                ]
            }
        else:
            symbol_data['depth'] = None
        
        extracted_data[symbol_key] = symbol_data
    
    return extracted_data


def format_market_quote(quote_data):
    """
    Format and display market quote data in a readable format.
    
    Args:
        quote_data (dict): Market quote data from get_full_market_quote
    
    Returns:
        dict: Formatted market quote data for computation
    """
    if not quote_data:
        print("No market quote data available")
        return None
    
    # Extract data for computation
    extracted_data = extract_market_quote_data(quote_data)
    
    print("\n" + "="*60)
    print("FULL MARKET QUOTE")
    print("="*60)
    
    for symbol_key, data in extracted_data.items():
        print(f"\nSymbol: {data['symbol']}")
        print(f"Instrument Token: {data['instrument_token']}")
        print(f"Last Price: ₹{data['last_price']:.2f}" if data['last_price'] is not None else "Last Price: N/A")
        print(f"Average Price: ₹{data['average_price']:.2f}" if data['average_price'] is not None else "Average Price: N/A")
        print(f"Net Change: {data['net_change']:.2f}" if data['net_change'] is not None else "Net Change: N/A")
        print(f"Volume: {data['volume']:,}" if data['volume'] is not None else "Volume: N/A")
        print(f"Open Interest: {data['oi']:,}" if data['oi'] is not None else "Open Interest: N/A")
        print(f"OI Day High: {data['oi_day_high']:,}" if data['oi_day_high'] is not None else "OI Day High: N/A")
        print(f"OI Day Low: {data['oi_day_low']:,}" if data['oi_day_low'] is not None else "OI Day Low: N/A")
        print(f"Total Buy Quantity: {data['total_buy_quantity']:,}" if data['total_buy_quantity'] is not None else "Total Buy Quantity: N/A")
        print(f"Total Sell Quantity: {data['total_sell_quantity']:,}" if data['total_sell_quantity'] is not None else "Total Sell Quantity: N/A")
        print(f"Upper Circuit: ₹{data['upper_circuit_limit']:.2f}" if data['upper_circuit_limit'] is not None else "Upper Circuit: N/A")
        print(f"Lower Circuit: ₹{data['lower_circuit_limit']:.2f}" if data['lower_circuit_limit'] is not None else "Lower Circuit: N/A")
        print(f"Timestamp: {data['timestamp']}")
        
        # OHLC Data
        if data['ohlc']:
            print(f"\nOHLC:")
            print(f"  Open: ₹{data['ohlc']['open']:.2f}")
            print(f"  High: ₹{data['ohlc']['high']:.2f}")
            print(f"  Low: ₹{data['ohlc']['low']:.2f}")
            print(f"  Close: ₹{data['ohlc']['close']:.2f}")
        
        # Market Depth
        if data['depth']:
            print(f"\nMarket Depth:")
            
            # Buy side
            if data['depth']['buy']:
                print("  Buy Side:")
                for i, order in enumerate(data['depth']['buy'][:5]):  # Show top 5
                    print(f"    {i+1}. Price: ₹{order['price']:.2f}, "
                          f"Qty: {order['quantity']:,}, "
                          f"Orders: {order['orders']}")
            
            # Sell side
            if data['depth']['sell']:
                print("  Sell Side:")
                for i, order in enumerate(data['depth']['sell'][:5]):  # Show top 5
                    print(f"    {i+1}. Price: ₹{order['price']:.2f}, "
                          f"Qty: {order['quantity']:,}, "
                          f"Orders: {order['orders']}")
    
    print("="*60)
    
    return extracted_data


def get_ltp_quote(access_token, instrument_key):
    """
    Get Last Traded Price (LTP) for a given instrument.
    
    Args:
        access_token (str): The access token obtained from Token API
        instrument_key (str): The instrument key (e.g., 'NSE_EQ|INE848E01016')
    
    Returns:
        dict: LTP data containing last traded price and other basic info
    """
    url = f'https://api.upstox.com/v3/market-quote/ltp'
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {access_token}'
    }
    params = {'instrument_key': instrument_key}
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error getting LTP quote: {e}")
        return None


def get_multiple_ltp_quotes(access_token, instrument_keys):
    """
    Get Last Traded Price (LTP) for multiple instruments.
    
    Args:
        access_token (str): The access token obtained from Token API
        instrument_keys (list): List of instrument keys
    
    Returns:
        dict: LTP data for all instruments
    """
    # Join multiple instrument keys with comma
    # Join multiple instrument keys with comma
    instruments_param = ','.join(instrument_keys)
    url = f'https://api.upstox.com/v3/market-quote/ltp'
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {access_token}'
    }
    params = {'instrument_key': instruments_param}
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error getting multiple LTP quotes: {e}")
        return None


def format_ltp_quote(ltp_data):
    """
    Format and display LTP quote data in a readable format.
    
    Args:
        ltp_data (dict): LTP data from get_ltp_quote or get_multiple_ltp_quotes
    
    Returns:
        dict: Formatted LTP data for computation
    """
    if not ltp_data:
        print("No LTP data available")
        return None
    
    print("\n" + "="*50)
    print("LAST TRADED PRICE (LTP) QUOTES")
    print("="*50)
    
    formatted_data = {}
    
    if 'data' in ltp_data:
        for instrument_key, data in ltp_data['data'].items():
            # Extract LTP data with all available fields
            ltp_info = {
                'instrument_key': instrument_key,
                'last_price': data.get('last_price', 0),
                'instrument_token': data.get('instrument_token', 'N/A'),
                'ltq': data.get('ltq', 0),  # Last Traded Quantity
                'volume': data.get('volume', 0),
                'cp': data.get('cp', 0),  # Change Percentage
                'timestamp': data.get('timestamp', 'N/A')
            }
            
            formatted_data[instrument_key] = ltp_info
            
            print(f"\nInstrument: {instrument_key}")
            print(f"Instrument Token: {ltp_info['instrument_token']}")
            print(f"Last Price: ₹{ltp_info['last_price']:.2f}")
            print(f"Last Traded Quantity: {ltp_info['ltq']:,}")
            print(f"Volume: {ltp_info['volume']:,}")
            print(f"Change Percentage: {ltp_info['cp']:.2f}%")
            print(f"Timestamp: {ltp_info['timestamp']}")
    
    print("="*50)
    return formatted_data


def get_ohlc_quote(access_token, instrument_key, interval="1d"):
    """
    Get OHLC (Open, High, Low, Close) market quote for a given instrument.
    
    Args:
        access_token (str): The access token obtained from Token API
        instrument_key (str): The instrument key (e.g., 'NSE_EQ|INE669E01016')
        interval (str): Time interval for OHLC data (e.g., '1d', '1h', '5m')
    
    Returns:
        dict: OHLC data containing live and previous OHLC data
    """
    url = 'https://api.upstox.com/v3/market-quote/ohlc'
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {access_token}'
    }
    
    params = {
        "instrument_key": instrument_key,
        "interval": interval
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error getting OHLC quote: {e}")
        return None


def get_multiple_ohlc_quotes(access_token, instrument_keys, interval="1d"):
    """
    Get OHLC (Open, High, Low, Close) market quotes for multiple instruments.
    
    Args:
        access_token (str): The access token obtained from Token API
        instrument_keys (list): List of instrument keys
        interval (str): Time interval for OHLC data (e.g., '1d', '1h', '5m')
    
    Returns:
        dict: OHLC data for all instruments
    """
    url = 'https://api.upstox.com/v3/market-quote/ohlc'
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {access_token}'
    }
    
    # Join multiple instrument keys with comma
    instruments_param = ','.join(instrument_keys)
    params = {
        "instrument_key": instruments_param,
        "interval": interval
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error getting multiple OHLC quotes: {e}")
        return None


def format_ohlc_quote(ohlc_data):
    """
    Format and display OHLC quote data in a readable format.
    
    Args:
        ohlc_data (dict): OHLC data from get_ohlc_quote or get_multiple_ohlc_quotes
    
    Returns:
        dict: Formatted OHLC data for computation
    """
    if not ohlc_data:
        print("No OHLC data available")
        return None
    
    print("\n" + "="*60)
    print("OHLC (OPEN, HIGH, LOW, CLOSE) QUOTES")
    print("="*60)
    
    formatted_data = {}
    
    if 'data' in ohlc_data:
        for instrument_key, data in ohlc_data['data'].items():
            # Extract OHLC data
            ohlc_info = {
                'instrument_key': instrument_key,
                'last_price': data.get('last_price', 0),
                'instrument_token': data.get('instrument_token', 'N/A'),
                'prev_ohlc': data.get('prev_ohlc', {}),
                'live_ohlc': data.get('live_ohlc', {})
            }
            
            formatted_data[instrument_key] = ohlc_info
            
            print(f"\nInstrument: {instrument_key}")
            print(f"Instrument Token: {ohlc_info['instrument_token']}")
            print(f"Last Price: ₹{ohlc_info['last_price']:.2f}")
            
            # Previous OHLC
            if ohlc_info['prev_ohlc']:
                prev = ohlc_info['prev_ohlc']
                print(f"\nPrevious OHLC:")
                print(f"  Open: ₹{prev.get('open', 0):.2f}")
                print(f"  High: ₹{prev.get('high', 0):.2f}")
                print(f"  Low: ₹{prev.get('low', 0):.2f}")
                print(f"  Close: ₹{prev.get('close', 0):.2f}")
                print(f"  Volume: {prev.get('volume', 0):,}")
                print(f"  Timestamp: {prev.get('ts', 'N/A')}")
            
            # Live OHLC
            if ohlc_info['live_ohlc']:
                live = ohlc_info['live_ohlc']
                print(f"\nLive OHLC:")
                print(f"  Open: ₹{live.get('open', 0):.2f}")
                print(f"  High: ₹{live.get('high', 0):.2f}")
                print(f"  Low: ₹{live.get('low', 0):.2f}")
                print(f"  Close: ₹{live.get('close', 0):.2f}")
                print(f"  Volume: {live.get('volume', 0):,}")
                print(f"  Timestamp: {live.get('ts', 'N/A')}")
    
    print("="*60)
    return formatted_data


def get_option_greek(access_token, instrument_key):
    """
    Get Option Greek fields for a given instrument.
    
    Args:
        access_token (str): The access token obtained from Token API
        instrument_key (str): The instrument key (e.g., 'NSE_FO|43885')
    
    Returns:
        dict: Option Greek data containing delta, gamma, theta, vega, IV, etc.
    """
    url = f'https://api.upstox.com/v3/market-quote/option-greek?instrument_key={instrument_key}'
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {access_token}'
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error getting option greek: {e}")
        return None


def get_multiple_option_greeks(access_token, instrument_keys):
    """
    Get Option Greek fields for multiple instruments.
    
    Args:
        access_token (str): The access token obtained from Token API
        instrument_keys (list): List of instrument keys
    
    Returns:
        dict: Option Greek data for all instruments
    """
    # Join multiple instrument keys with comma
    instruments_param = ','.join(instrument_keys)
    url = f'https://api.upstox.com/v3/market-quote/option-greek?instrument_key={instruments_param}'
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {access_token}'
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error getting multiple option greeks: {e}")
        return None


def format_option_greek(greek_data):
    """
    Format and display Option Greek data in a readable format.
    
    Args:
        greek_data (dict): Option Greek data from get_option_greek or get_multiple_option_greeks
    
    Returns:
        dict: Formatted Option Greek data for computation
    """
    if not greek_data:
        print("No Option Greek data available")
        return None
    
    print("\n" + "="*60)
    print("OPTION GREEK FIELDS")
    print("="*60)
    
    formatted_data = {}
    
    if 'data' in greek_data:
        for instrument_key, data in greek_data['data'].items():
            # Extract Option Greek data
            greek_info = {
                'instrument_key': instrument_key,
                'last_price': data.get('last_price', 0),
                'instrument_token': data.get('instrument_token', 'N/A'),
                'ltq': data.get('ltq', 0),  # Last Traded Quantity
                'volume': data.get('volume', 0),
                'cp': data.get('cp', 0),  # Change Percentage
                'iv': data.get('iv', 0),  # Implied Volatility
                'vega': data.get('vega', 0),
                'gamma': data.get('gamma', 0),
                'theta': data.get('theta', 0),
                'delta': data.get('delta', 0),
                'oi': data.get('oi', 0)  # Open Interest
            }
            
            formatted_data[instrument_key] = greek_info
            
            print(f"\nInstrument: {instrument_key}")
            print(f"Instrument Token: {greek_info['instrument_token']}")
            print(f"Last Price: ₹{greek_info['last_price']:.2f}")
            print(f"Last Traded Quantity: {greek_info['ltq']:,}")
            print(f"Volume: {greek_info['volume']:,}")
            print(f"Change Percentage: {greek_info['cp']:.2f}%")
            print(f"Open Interest: {greek_info['oi']:,}")
            
            print(f"\nOption Greeks:")
            print(f"  Delta: {greek_info['delta']:.4f}")
            print(f"  Gamma: {greek_info['gamma']:.4f}")
            print(f"  Theta: {greek_info['theta']:.4f}")
            print(f"  Vega: {greek_info['vega']:.4f}")
            print(f"  Implied Volatility: {greek_info['iv']:.4f} ({greek_info['iv']*100:.2f}%)")
    
    print("="*60)
    return formatted_data





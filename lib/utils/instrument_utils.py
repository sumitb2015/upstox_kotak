"""
Instrument utilities for option chain and instrument key management
"""

import pandas as pd

from lib.core.config import Config
from datetime import datetime

def get_option_instrument_key(underlying_symbol, strike_price, option_type, nse_data, expiry_date=None):
    """
    Get instrument key for a specific option (CE/PE) using the existing get_instrument_key logic
    
    Args:
        underlying_symbol (str): The underlying symbol (e.g., "NIFTY")
        strike_price (int): The strike price
        option_type (str): "CE" or "PE"
        nse_data (DataFrame): NSE data DataFrame
        expiry_date (str/date, optional): Specific expiry date to filter by (YYYY-MM-DD or datetime.date)
    
    Returns:
        str: The instrument key for the matching option
    """
    try:
        if nse_data is None:
            if Config.is_verbose():
                print("Error: NSE data is required but not provided")
            return None
            
        # Ensure expiry column is datetime/date if we are filtering by it
        if expiry_date is not None:
            # Defensive cast: Ensure expiry_date is string if it's a numpy string
            if hasattr(expiry_date, 'dtype'):
                expiry_date = str(expiry_date)
            
            if 'expiry' in nse_data.columns and nse_data['expiry'].dtype != 'object':
                 # Don't overwrite the whole column if possible, just ensure type for comparison
                 pass
        
        # Defensive: Ensure strike_price is native int/float
        if hasattr(strike_price, 'dtype'):
            strike_price = int(strike_price) if not isinstance(strike_price, float) else float(strike_price)
        
        # Filter for the specific underlying symbol, strike price, and option type
        mask = (nse_data['underlying_symbol'] == underlying_symbol) & \
               (nse_data['strike_price'] == strike_price) & \
               (nse_data['instrument_type'] == option_type)
               
        filtered_df = nse_data[mask]
        
        if filtered_df.empty:
            if Config.is_verbose():
                print(f"No {option_type} options found for {underlying_symbol} {strike_price}")
            return None
            
        # Filter by expiry if provided
        if expiry_date is not None:
            # Convert expiry_date to string YYYY-MM-DD for comparison if needed
            target_expiry = str(expiry_date)
            
            # Check if dataframe expiry is in MS or String
            # Usually download_nse_market_data normalizes it?
            # Let's assume we can try to match date objects or strings
            
            # Create a copy to avoid SettingWithCopy warning
            filtered_df = filtered_df.copy()
            
            # Convert DF expiry to string YYYY-MM-DD for reliable comparison
            # Robustly handle expiry column format (ms timestamp vs string)
            if filtered_df['expiry'].dtype.kind in 'iuf': # int, uint, or float (timestamps)
                 # Filter out obviously invalid timestamps (too large or negative)
                 # Valid range: 2000-01-01 to 2100-01-01 in milliseconds
                 valid_range = (946684800000, 4102444800000)
                 valid_mask = (filtered_df['expiry'] >= valid_range[0]) & (filtered_df['expiry'] <= valid_range[1])
                 filtered_df = filtered_df[valid_mask].copy()
                 
                 if filtered_df.empty:
                     if Config.is_verbose():
                         print(f"No valid expiry timestamps found for {option_type} {strike_price}")
                     return None
                 
                 # Convert float to int64 to avoid overflow, then to datetime
                 filtered_df['expiry_int'] = filtered_df['expiry'].astype('int64')
                 filtered_df['expiry_str'] = pd.to_datetime(filtered_df['expiry_int'], unit='ms', errors='coerce').dt.strftime('%Y-%m-%d')
            elif filtered_df['expiry'].dtype.kind == 'O': # Object (string or mixed)
                 # Try converting to datetime and back to string to normalize
                 try:
                     filtered_df['expiry_str'] = pd.to_datetime(filtered_df['expiry'], errors='coerce').dt.strftime('%Y-%m-%d')
                 except:
                     filtered_df['expiry_str'] = filtered_df['expiry'].astype(str)
            else:
                 filtered_df['expiry_str'] = filtered_df['expiry'].astype(str)
                 
            # Filter
            mask_exp = (filtered_df['expiry_str'] == target_expiry)
            matches = filtered_df[mask_exp]
            
            # Fallback logic will handle empty matches below
            if matches.empty:
                # Fallback: Find nearest future expiry
                if Config.is_verbose():
                    print(f"⚠️ No exact match for {target_expiry}. Searching for nearest future expiry...")
                
                # Convert target to date object
                try:
                    target_dt = datetime.strptime(target_expiry, '%Y-%m-%d').date()
                    # Convert column to date objects for comparison
                    filtered_df['expiry_date_obj'] = pd.to_datetime(filtered_df['expiry_str']).dt.date
                    
                    # Filter for expiries >= target
                    future_matches = filtered_df[filtered_df['expiry_date_obj'] >= target_dt]
                    
                    if Config.is_verbose():
                        print(f"DEBUG: Target {target_dt} | Future Matches: {len(future_matches)}")
                        if not future_matches.empty:
                             print(f"DEBUG: First Future: {future_matches.iloc[0]['expiry_str']}")
                    
                    if not future_matches.empty:
                        # Sort and pick nearest
                        future_matches = future_matches.sort_values('expiry_date_obj')
                        matches = future_matches.iloc[[0]] # Keep as DF
                        found_nearest = matches.iloc[0]['expiry_str']
                        if Config.is_verbose():
                            print(f"✅ Found nearest expiry: {found_nearest}")
                    else:
                        if Config.is_verbose():
                             print(f"❌ No future expiry found after {target_expiry}")
                        return None
                except Exception as e:
                    print(f"Fallback filtering failed: {e}")
                    return None
            
            filtered_df = matches
        
        # Sort by expiry and get the first (earliest) expiry
        # (If expiry_date was provided, this should just be the one we want)
        sorted_df = filtered_df.sort_values('expiry')
        instrument_key = sorted_df.iloc[0]['instrument_key']
        found_expiry = sorted_df.iloc[0]['expiry']
        
        if Config.is_verbose():
            print(f"Found {option_type} {strike_price}: {instrument_key} (Expiry: {found_expiry})")
        return instrument_key
        
    except Exception as e:
        print(f"Error getting {option_type} instrument key: {e}")
        return None


def get_nifty_option_instrument_keys(nse_data, strike_prices, option_type="CE"):
    """
    Get instrument keys for NIFTY options with specific strikes and type.
    
    Args:
        nse_data (DataFrame): NSE data DataFrame
        strike_prices (list): List of strike prices to search for
        option_type (str): "CE" for Call or "PE" for Put
    
    Returns:
        dict: Dictionary with strike prices as keys and instrument keys as values
    """
    instrument_keys = {}
    
    try:
        if nse_data is None:
            print("Error: NSE data is required but not provided")
            return instrument_keys
        
        # Convert expiry to datetime if needed
        if 'expiry' in nse_data.columns and nse_data['expiry'].dtype != 'object':
            nse_data['expiry'] = pd.to_datetime(nse_data['expiry'], unit='ms').dt.date
        
        for strike in strike_prices:
            # Filter for NIFTY options with specific strike and type
            filtered_df = nse_data[
                (nse_data['underlying_symbol'] == 'NIFTY') & 
                (nse_data['strike_price'] == strike) &
                (nse_data['instrument_type'] == option_type)
            ]
            
            if not filtered_df.empty:
                # Sort by expiry and get the first (earliest) expiry
                sorted_df = filtered_df.sort_values('expiry')
                instrument_key = sorted_df.iloc[0]['instrument_key']
                expiry_date = sorted_df.iloc[0]['expiry']
                
                instrument_keys[strike] = instrument_key
                if Config.is_verbose():
                    print(f"Found {option_type} {strike}: {instrument_key} (Expiry: {expiry_date})")
            else:
                if Config.is_verbose():
                    print(f"No {option_type} options found for NIFTY {strike}")
        
        return instrument_keys
        
    except Exception as e:
        print(f"Error getting NIFTY option instrument keys: {e}")
        return instrument_keys


def get_instrument_key(underlying_symbol="NIFTY", strike_price=25300, nse_data=None):
    """Get instrument key for a specific underlying symbol and strike price
    
    Args:
        underlying_symbol (str): The underlying symbol (e.g., "NIFTY")
        strike_price (int): The strike price to search for
        nse_data (DataFrame): NSE data DataFrame (required)
    
    Returns:
        str: The instrument key for the matching option
        None: If no matching instrument is found
    """
    if Config.is_verbose():
        print(f"Searching for instrument key: {underlying_symbol} {strike_price}")
    
    try:
        if nse_data is None:
            print("Error: NSE data is required but not provided")
            return None
        
        # Convert expiry to datetime and then to date (only if not already converted)
        if 'expiry' in nse_data.columns and nse_data['expiry'].dtype != 'object':
            nse_data['expiry'] = pd.to_datetime(nse_data['expiry'], unit='ms').dt.date
        
        # Filter for the specific underlying symbol and strike price
        filtered_df = nse_data[(nse_data['underlying_symbol'] == underlying_symbol) & 
                              (nse_data['strike_price'] == strike_price)]
        
        if filtered_df.empty:
            if Config.is_verbose():
                print(f"No instruments found for {underlying_symbol} with strike price {strike_price}")
            return None
        
        # Sort by expiry and get the first (earliest) expiry
        sorted_df = filtered_df.sort_values('expiry')
        instrument_key = sorted_df.iloc[0]['instrument_key']
        
        expiry_date = sorted_df.iloc[0]['expiry']
        if Config.is_verbose():
            print(f"Found instrument key: {instrument_key} (Expiry: {expiry_date})")
        
        return instrument_key
        
    except KeyError as e:
        print(f"Required column not found in data: {e}")
        return None
    except Exception as e:
        print(f"Error getting instrument key: {e}")
        return None

def get_future_instrument_key(underlying_symbol="NIFTY", nse_data=None):
    """
    Get instrument key for the nearest future contract of an underlying.
    
    Args:
        underlying_symbol (str): The underlying symbol (e.g., "NIFTY")
        nse_data (DataFrame): NSE data DataFrame
    
    Returns:
        str: Instrument key for the nearest future
    """
    try:
        if nse_data is None: return None
        
        # Filter: Underlying + FUTIDX
        # Use try-except for column access safety
        if 'underlying_symbol' in nse_data.columns:
            mask = (nse_data['underlying_symbol'] == underlying_symbol) & (nse_data['instrument_type'].isin(['FUT', 'FUTIDX']))
        elif 'name' in nse_data.columns:
             mask = (nse_data['name'] == underlying_symbol) & (nse_data['instrument_type'].isin(['FUT', 'FUTIDX']))
        else:
             print("Error: neither 'underlying_symbol' nor 'name' column found")
             return None
            
        filtered = nse_data[mask]
        
        if filtered.empty:
            # Try plain Symbol match if FUTIDX specific fail?
            return None

        # Filter out expired contracts
        # Assuming expiry is in milliseconds (Upstox standard)
        if 'expiry' in filtered.columns:
            current_ms = pd.Timestamp.now().timestamp() * 1000
            filtered = filtered[filtered['expiry'] >= current_ms]
            
        if filtered.empty:
            print("Error: No active future contracts found")
            return None
            
        # Sort by expiry
        sorted_df = filtered.sort_values('expiry')
        
        # Return nearest
        key = sorted_df.iloc[0]['instrument_key']
        date = sorted_df.iloc[0]['expiry']
        if Config.is_verbose():
             print(f"Found Future: {key} ({date})")
        return key
        
    except Exception as e:
        print(f"Error getting Future Key: {e}")
        return None


def get_lot_size(instrument_key, nse_data):
    """
    Get lot size for a given instrument key.
    
    Args:
        instrument_key (str): The instrument key
        nse_data (DataFrame): NSE data DataFrame
    
    Returns:
        int: Lot size for the instrument (default 65 for Nifty if not found)
    """
    try:
        if nse_data is None:
            return 75  # Default Nifty lot size
        
        # Find the row matching the instrument key
        match = nse_data[nse_data['instrument_key'] == instrument_key]
        
        if match.empty:
            return 75  # Default
        
        # Return lot_size from the row
        lot_size = match.iloc[0].get('lot_size', 75)
        return int(lot_size)
        
    except Exception as e:
        print(f"Error getting lot size: {e}")
        return 75  # Default fallback




def get_equity_instrument_key(symbol, nse_data=None):
    """
    Get instrument key for an Equity symbol (Stock).
    
    Args:
        symbol (str): The trading symbol (e.g., "RELIANCE", "HDFCBANK")
        nse_data (DataFrame): NSE data DataFrame
    
    Returns:
        str: Instrument key for the stock
    """
    try:
        if nse_data is None: 
            if Config.is_verbose():
                print("Error: NSE data is required")
            return None
        
        if Config.is_verbose():
            print(f"Searching for Equity: {symbol}")
            
        # 1. Look for NSE_EQ segment exact match
        mask = (nse_data['trading_symbol'] == symbol) & (nse_data['segment'] == 'NSE_EQ')
        matches = nse_data[mask]
        
        if matches.empty:
             # Fallback: Try searching by Name if Symbol match fails
             mask = (nse_data['name'].str.contains(symbol, case=False, na=False)) & (nse_data['segment'] == 'NSE_EQ')
             matches = nse_data[mask]
        
        if matches.empty:
            if Config.is_verbose():
                print(f"No equity instrument found for {symbol}")
            return None

        # If multiple matches, prefer 'EQ' instrument_type
        if len(matches) > 1:
            eq_only = matches[matches['instrument_type'] == 'EQ']
            if not eq_only.empty:
                matches = eq_only
        
        # Return the first match
        key = matches.iloc[0]['instrument_key']
        name = matches.iloc[0]['name']
        
        if Config.is_verbose():
             print(f"Found Equity: {key} ({name})")
             
        return key
        
    except Exception as e:
        print(f"Error getting Equity Key: {e}")
        return None


def get_atm_strike(spot_price, strike_step=50):
    """
    Calculate ATM strike price based on spot price and strike step.
    
    Args:
        spot_price (float): Underlying spot price
        strike_step (int): Strike interval (e.g., 50 for Nifty, 100 for BankNifty)
        
    Returns:
        int: Calculated ATM strike
    """
    return int(round(spot_price / strike_step) * strike_step)

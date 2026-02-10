"""
Margin calculator for option delivery orders and other trading instruments
"""

import requests
import json


def get_margin_details(access_token, instruments):
    """
    Get margin details for option delivery orders and other trading instruments.
    
    Args:
        access_token (str): The access token obtained from Token API
        instruments (list): List of instrument dictionaries with the following structure:
            [
                {
                    "instrument_key": "NSE_FO|54524",
                    "quantity": 1,
                    "transaction_type": "BUY",  # or "SELL"
                    "product": "D"  # D for delivery, I for intraday, etc.
                }
            ]
    
    Returns:
        dict: Margin details response from Upstox API
        None: If request fails
    """
    print("Fetching margin details...")
    
    url = "https://api.upstox.com/v2/charges/margin"
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    data = {
        "instruments": instruments
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Margin details fetched successfully")
            return result
        else:
            print(f"❌ Error fetching margin details: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except requests.RequestException as e:
        print(f"❌ Request error when fetching margin details: {e}")
        return None
    except Exception as e:
        print(f"❌ Exception when fetching margin details: {e}")
        return None


def get_single_instrument_margin(access_token, instrument_key, quantity, transaction_type="BUY", product="D"):
    """
    Get margin details for a single instrument.
    
    Args:
        access_token (str): The access token obtained from Token API
        instrument_key (str): Instrument key (e.g., "NSE_FO|54524")
        quantity (int): Quantity of the instrument
        transaction_type (str): "BUY" or "SELL"
        product (str): Product type ("D" for delivery, "I" for intraday, etc.)
    
    Returns:
        dict: Margin details for the single instrument
        None: If request fails
    """
    instruments = [
        {
            "instrument_key": instrument_key,
            "quantity": quantity,
            "transaction_type": transaction_type,
            "product": product
        }
    ]
    
    return get_margin_details(access_token, instruments)


def format_margin_details(margin_data):
    """
    Format and display margin details in a readable format.
    
    Args:
        margin_data (dict): Margin data from get_margin_details
    
    Returns:
        dict: Formatted margin data for computation
    """
    if not margin_data or margin_data.get('status') != 'success':
        print("❌ No valid margin data available")
        return None
    
    print("\n" + "="*80)
    print("MARGIN DETAILS")
    print("="*80)
    
    data = margin_data.get('data', {})
    
    if not data:
        print("No margin data found")
        return None
    
    # Extract margin information from the response structure
    margins = data.get('margins', [])
    required_margin = data.get('required_margin', 0)
    final_margin = data.get('final_margin', 0)
    
    if not margins:
        print("No margin details found in response")
        return None
    
    # Process each margin entry
    formatted_data = {}
    
    for i, margin_info in enumerate(margins):
        instrument_key = f"instrument_{i+1}"  # Since we don't have individual instrument keys in response
        
        # Extract margin details based on actual API response structure
        instrument_data = {
            'instrument_key': instrument_key,
            'span_margin': margin_info.get('span_margin', 0),
            'exposure_margin': margin_info.get('exposure_margin', 0),
            'equity_margin': margin_info.get('equity_margin', 0),
            'net_buy_premium': margin_info.get('net_buy_premium', 0),
            'additional_margin': margin_info.get('additional_margin', 0),
            'total_margin': margin_info.get('total_margin', 0),
            'tender_margin': margin_info.get('tender_margin', 0),
            'required_margin': required_margin,
            'final_margin': final_margin
        }
        
        formatted_data[instrument_key] = instrument_data
        
        # Display margin breakdown
        print(f"\nInstrument: {instrument_key}")
        print("-" * 50)
        print(f"Required Margin: ₹{required_margin:,.2f}")
        print(f"Final Margin: ₹{final_margin:,.2f}")
        print(f"Total Margin: ₹{instrument_data['total_margin']:,.2f}")
        print(f"Span Margin: ₹{instrument_data['span_margin']:,.2f}")
        print(f"Exposure Margin: ₹{instrument_data['exposure_margin']:,.2f}")
        print(f"Equity Margin: ₹{instrument_data['equity_margin']:,.2f}")
        print(f"Net Buy Premium: ₹{instrument_data['net_buy_premium']:,.2f}")
        print(f"Additional Margin: ₹{instrument_data['additional_margin']:,.2f}")
        print(f"Tender Margin: ₹{instrument_data['tender_margin']:,.2f}")
    
    print("="*80)
    return formatted_data


def check_margin_availability(access_token, instruments, available_funds):
    """
    Check if sufficient margin is available for the given instruments.
    
    Args:
        access_token (str): The access token obtained from Token API
        instruments (list): List of instrument dictionaries
        available_funds (float): Available funds in the account
    
    Returns:
        dict: Margin check results with availability status
    """
    print(f"Checking margin availability against ₹{available_funds:,.2f} available funds...")
    
    margin_data = get_margin_details(access_token, instruments)
    if not margin_data:
        return None
    
    # Extract margin information directly from API response
    data = margin_data.get('data', {})
    required_margin = data.get('required_margin', 0)
    final_margin = data.get('final_margin', 0)
    
    # Use the final_margin as the total margin required
    total_margin_required = final_margin
    
    # Check availability
    margin_available = available_funds >= total_margin_required
    shortfall = max(0, total_margin_required - available_funds)
    
    result = {
        'total_margin_required': total_margin_required,
        'required_margin': required_margin,
        'final_margin': final_margin,
        'available_funds': available_funds,
        'margin_available': margin_available,
        'shortfall': shortfall,
        'margin_utilization_percent': (total_margin_required / available_funds * 100) if available_funds > 0 else 0,
        'raw_margin_data': margin_data
    }
    
    print(f"\n" + "="*50)
    print("MARGIN AVAILABILITY CHECK")
    print("="*50)
    print(f"Required Margin: ₹{required_margin:,.2f}")
    print(f"Final Margin: ₹{final_margin:,.2f}")
    print(f"Total Margin Required: ₹{total_margin_required:,.2f}")
    print(f"Available Funds: ₹{available_funds:,.2f}")
    print(f"Margin Utilization: {result['margin_utilization_percent']:.1f}%")
    
    if margin_available:
        print(f"✅ Sufficient margin available")
        print(f"Remaining funds: ₹{available_funds - total_margin_required:,.2f}")
    else:
        print(f"❌ Insufficient margin")
        print(f"Shortfall: ₹{shortfall:,.2f}")
    
    print("="*50)
    
    return result


def get_option_delivery_margin(access_token, instrument_key, quantity, transaction_type="BUY"):
    """
    Get margin details specifically for option delivery orders.
    
    Args:
        access_token (str): The access token obtained from Token API
        instrument_key (str): Option instrument key (e.g., "NSE_FO|54524")
        quantity (int): Quantity of options (typically 75 for NIFTY)
        transaction_type (str): "BUY" or "SELL"
    
    Returns:
        dict: Margin details for option delivery
    """
    print(f"Getting margin for option delivery: {instrument_key}")
    
    return get_single_instrument_margin(
        access_token=access_token,
        instrument_key=instrument_key,
        quantity=quantity,
        transaction_type=transaction_type,
        product="D"  # D for delivery
    )


def get_mcx_delivery_margin(access_token, instrument_key, quantity, transaction_type="BUY"):
    """
    Get margin details specifically for MCX delivery orders.
    
    Args:
        access_token (str): The access token obtained from Token API
        instrument_key (str): MCX instrument key (e.g., "MCX_FO|435356")
        quantity (int): Quantity of the instrument
        transaction_type (str): "BUY" or "SELL"
    
    Returns:
        dict: Margin details for MCX delivery
    """
    print(f"Getting margin for MCX delivery: {instrument_key}")
    
    return get_single_instrument_margin(
        access_token=access_token,
        instrument_key=instrument_key,
        quantity=quantity,
        transaction_type=transaction_type,
        product="D"  # D for delivery
    )


def get_mcx_futures_margin(access_token, instrument_key, quantity, transaction_type="BUY"):
    """
    Get margin details specifically for MCX futures orders.
    
    Args:
        access_token (str): The access token obtained from Token API
        instrument_key (str): MCX futures instrument key (e.g., "MCX_FO|435356")
        quantity (int): Quantity of the instrument
        transaction_type (str): "BUY" or "SELL"
    
    Returns:
        dict: Margin details for MCX futures
    """
    print(f"Getting margin for MCX futures: {instrument_key}")
    
    return get_single_instrument_margin(
        access_token=access_token,
        instrument_key=instrument_key,
        quantity=quantity,
        transaction_type=transaction_type,
        product="I"  # I for intraday/futures
    )


def get_mcx_options_margin(access_token, instrument_key, quantity, transaction_type="BUY"):
    """
    Get margin details specifically for MCX options orders.
    
    Args:
        access_token (str): The access token obtained from Token API
        instrument_key (str): MCX options instrument key (e.g., "MCX_FO|435356")
        quantity (int): Quantity of the instrument
        transaction_type (str): "BUY" or "SELL"
    
    Returns:
        dict: Margin details for MCX options
    """
    print(f"Getting margin for MCX options: {instrument_key}")
    
    return get_single_instrument_margin(
        access_token=access_token,
        instrument_key=instrument_key,
        quantity=quantity,
        transaction_type=transaction_type,
        product="D"  # D for delivery
    )


def analyze_margin_response(margin_data):
    """
    Analyze margin response to determine instrument type and characteristics.
    
    Args:
        margin_data (dict): Margin data from get_margin_details
    
    Returns:
        dict: Analysis results with instrument type and characteristics
    """
    if not margin_data or margin_data.get('status') != 'success':
        return None
    
    data = margin_data.get('data', {})
    margins = data.get('margins', [])
    
    if not margins:
        return None
    
    margin_info = margins[0]  # Get first margin entry
    
    # Analyze margin characteristics
    span_margin = margin_info.get('span_margin', 0)
    exposure_margin = margin_info.get('exposure_margin', 0)
    net_buy_premium = margin_info.get('net_buy_premium', 0)
    additional_margin = margin_info.get('additional_margin', 0)
    
    # Determine instrument type based on margin characteristics
    instrument_type = "Unknown"
    characteristics = []
    
    if net_buy_premium > 0 and span_margin == 0 and exposure_margin == 0:
        instrument_type = "Options (NSE/BSE)"
        characteristics.append("Premium-based margin (typical for options)")
    elif span_margin > 0 and exposure_margin > 0:
        instrument_type = "MCX Futures/Commodities"
        characteristics.append("Span + Exposure margin (typical for MCX)")
    elif span_margin > 0:
        instrument_type = "Futures"
        characteristics.append("Span margin only")
    elif net_buy_premium > 0:
        instrument_type = "Options"
        characteristics.append("Premium-based margin")
    
    # Additional analysis
    if additional_margin > 0:
        characteristics.append(f"Additional margin: ₹{additional_margin:,.2f}")
    
    if span_margin > 0:
        characteristics.append(f"Span margin: ₹{span_margin:,.2f}")
    
    if exposure_margin > 0:
        characteristics.append(f"Exposure margin: ₹{exposure_margin:,.2f}")
    
    if net_buy_premium > 0:
        characteristics.append(f"Net buy premium: ₹{net_buy_premium:,.2f}")
    
    analysis = {
        'instrument_type': instrument_type,
        'characteristics': characteristics,
        'margin_breakdown': {
            'span_margin': span_margin,
            'exposure_margin': exposure_margin,
            'net_buy_premium': net_buy_premium,
            'additional_margin': additional_margin,
            'total_margin': margin_info.get('total_margin', 0)
        },
        'required_margin': data.get('required_margin', 0),
        'final_margin': data.get('final_margin', 0)
    }
    
    print(f"\n📊 MARGIN ANALYSIS")
    print(f"Instrument Type: {instrument_type}")
    print(f"Characteristics:")
    for char in characteristics:
        print(f"  • {char}")
    
    return analysis


# Example usage
if __name__ == "__main__":
    try:
        # Load access token from file
        with open('lib/core/accessToken.txt', 'r') as file:
            access_token = file.read().strip()
        
        print("="*60)
        print("MARGIN CALCULATOR EXAMPLES")
        print("="*60)
        
        # Example 1: NIFTY option delivery
        print("\n1. NIFTY Option Delivery Margin:")
        nifty_instrument = "NSE_FO|54524"  # Replace with actual instrument key
        nifty_quantity = 75  # NIFTY lot size
        
        nifty_margin = get_option_delivery_margin(access_token, nifty_instrument, nifty_quantity, "BUY")
        if nifty_margin:
            format_margin_details(nifty_margin)
            analyze_margin_response(nifty_margin)
        
        # Example 2: MCX delivery
        print("\n2. MCX Delivery Margin:")
        mcx_instrument = "MCX_FO|435356"  # Replace with actual instrument key
        mcx_quantity = 1  # MCX lot size
        
        mcx_margin = get_mcx_delivery_margin(access_token, mcx_instrument, mcx_quantity, "BUY")
        if mcx_margin:
            format_margin_details(mcx_margin)
            analyze_margin_response(mcx_margin)
        
        # Example 3: MCX futures
        print("\n3. MCX Futures Margin:")
        mcx_futures_margin = get_mcx_futures_margin(access_token, mcx_instrument, mcx_quantity, "BUY")
        if mcx_futures_margin:
            format_margin_details(mcx_futures_margin)
            analyze_margin_response(mcx_futures_margin)
        
        # Example 4: Check margin availability for multiple instruments
        print("\n4. Margin Availability Check:")
        available_funds = 100000  # Example available funds
        
        instruments = [
            {"instrument_key": nifty_instrument, "quantity": nifty_quantity, "transaction_type": "BUY", "product": "D"},
            {"instrument_key": mcx_instrument, "quantity": mcx_quantity, "transaction_type": "BUY", "product": "D"}
        ]
        
        check_result = check_margin_availability(access_token, instruments, available_funds)
        
    except FileNotFoundError:
        print("Error: accessToken.txt file not found")
    except Exception as e:
        print(f"Error: {e}")

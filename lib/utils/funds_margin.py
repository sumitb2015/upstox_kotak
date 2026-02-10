"""
Fund and margin management for equity and commodity markets
"""

import requests
import json


def get_funds_and_margin(access_token, segment=None):
    """
    Get user funds data for both equity and commodity markets.
    
    Args:
        access_token (str): The access token obtained from Token API
        segment (str, optional): Market segment filter. 
            - "SEC" for Equity only
            - "COM" for Commodity only
            - None for both segments
    
    Returns:
        dict: Funds and margin data from Upstox API
        None: If request fails
    """
    print("Fetching funds and margin data...")
    
    url = 'https://api.upstox.com/v2/user/get-funds-and-margin'
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {access_token}'
    }
    
    params = {}
    if segment:
        params['segment'] = segment
        print(f"Filtering for segment: {segment}")
    
    try:
        response = requests.get(url, headers=headers, params=params)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Funds and margin data fetched successfully")
            return result
        else:
            print(f"❌ Error fetching funds and margin: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except requests.RequestException as e:
        print(f"❌ Request error when fetching funds and margin: {e}")
        return None
    except Exception as e:
        print(f"❌ Exception when fetching funds and margin: {e}")
        return None


def get_equity_funds(access_token):
    """
    Get funds data specifically for equity segment.
    
    Args:
        access_token (str): The access token obtained from Token API
    
    Returns:
        dict: Equity funds data
    """
    print("Fetching equity funds data...")
    
    funds_data = get_funds_and_margin(access_token, segment="SEC")
    if funds_data and funds_data.get('status') == 'success':
        return funds_data.get('data', {}).get('equity', {})
    return None


def get_commodity_funds(access_token):
    """
    Get funds data specifically for commodity segment.
    
    Args:
        access_token (str): The access token obtained from Token API
    
    Returns:
        dict: Commodity funds data
    """
    print("Fetching commodity funds data...")
    
    funds_data = get_funds_and_margin(access_token, segment="COM")
    if funds_data and funds_data.get('status') == 'success':
        return funds_data.get('data', {}).get('commodity', {})
    return None


def format_funds_data(funds_data):
    """
    Format and display funds and margin data in a readable format.
    
    Args:
        funds_data (dict): Funds data from get_funds_and_margin
    
    Returns:
        dict: Formatted funds data for computation
    """
    if not funds_data or funds_data.get('status') != 'success':
        print("❌ No valid funds data available")
        return None
    
    print("\n" + "="*80)
    print("FUNDS AND MARGIN DATA")
    print("="*80)
    
    data = funds_data.get('data', {})
    
    if not data:
        print("No funds data found")
        return None
    
    formatted_data = {}
    
    # Process equity data
    equity_data = data.get('equity', {})
    if equity_data:
        print(f"\n📈 EQUITY SEGMENT")
        print("-" * 50)
        
        equity_formatted = {
            'used_margin': equity_data.get('used_margin', 0),
            'payin_amount': equity_data.get('payin_amount', 0),
            'span_margin': equity_data.get('span_margin', 0),
            'adhoc_margin': equity_data.get('adhoc_margin', 0),
            'notional_cash': equity_data.get('notional_cash', 0),
            'available_margin': equity_data.get('available_margin', 0),
            'exposure_margin': equity_data.get('exposure_margin', 0)
        }
        
        formatted_data['equity'] = equity_formatted
        
        print(f"Available Margin: ₹{equity_formatted['available_margin']:,.2f}")
        print(f"Used Margin: ₹{equity_formatted['used_margin']:,.2f}")
        print(f"Payin Amount: ₹{equity_formatted['payin_amount']:,.2f}")
        print(f"Span Margin: ₹{equity_formatted['span_margin']:,.2f}")
        print(f"Exposure Margin: ₹{equity_formatted['exposure_margin']:,.2f}")
        print(f"Adhoc Margin: ₹{equity_formatted['adhoc_margin']:,.2f}")
        print(f"Notional Cash: ₹{equity_formatted['notional_cash']:,.2f}")
    
    # Process commodity data
    commodity_data = data.get('commodity', {})
    if commodity_data:
        print(f"\n🏭 COMMODITY SEGMENT")
        print("-" * 50)
        
        commodity_formatted = {
            'used_margin': commodity_data.get('used_margin', 0),
            'payin_amount': commodity_data.get('payin_amount', 0),
            'span_margin': commodity_data.get('span_margin', 0),
            'adhoc_margin': commodity_data.get('adhoc_margin', 0),
            'notional_cash': commodity_data.get('notional_cash', 0),
            'available_margin': commodity_data.get('available_margin', 0),
            'exposure_margin': commodity_data.get('exposure_margin', 0)
        }
        
        formatted_data['commodity'] = commodity_formatted
        
        print(f"Available Margin: ₹{commodity_formatted['available_margin']:,.2f}")
        print(f"Used Margin: ₹{commodity_formatted['used_margin']:,.2f}")
        print(f"Payin Amount: ₹{commodity_formatted['payin_amount']:,.2f}")
        print(f"Span Margin: ₹{commodity_formatted['span_margin']:,.2f}")
        print(f"Exposure Margin: ₹{commodity_formatted['exposure_margin']:,.2f}")
        print(f"Adhoc Margin: ₹{commodity_formatted['adhoc_margin']:,.2f}")
        print(f"Notional Cash: ₹{commodity_formatted['notional_cash']:,.2f}")
    
    # Calculate totals
    total_available = (equity_data.get('available_margin', 0) + 
                      commodity_data.get('available_margin', 0))
    total_used = (equity_data.get('used_margin', 0) + 
                 commodity_data.get('used_margin', 0))
    total_payin = (equity_data.get('payin_amount', 0) + 
                  commodity_data.get('payin_amount', 0))
    
    print(f"\n💰 TOTAL SUMMARY")
    print("-" * 50)
    print(f"Total Available Margin: ₹{total_available:,.2f}")
    print(f"Total Used Margin: ₹{total_used:,.2f}")
    print(f"Total Payin Amount: ₹{total_payin:,.2f}")
    
    formatted_data['totals'] = {
        'total_available_margin': total_available,
        'total_used_margin': total_used,
        'total_payin_amount': total_payin
    }
    
    print("="*80)
    return formatted_data


def check_margin_availability_for_order(access_token, required_margin, segment="equity"):
    """
    Check if sufficient margin is available for placing an order.
    
    Args:
        access_token (str): The access token obtained from Token API
        required_margin (float): Margin required for the order
        segment (str): "equity" or "commodity"
    
    Returns:
        dict: Margin availability check results
    """
    print(f"Checking margin availability for ₹{required_margin:,.2f} in {segment} segment...")
    
    funds_data = get_funds_and_margin(access_token)
    if not funds_data:
        return None
    
    formatted_data = format_funds_data(funds_data)
    if not formatted_data:
        return None
    
    # Get available margin for the specified segment
    if segment == "equity":
        available_margin = formatted_data.get('equity', {}).get('available_margin', 0)
    elif segment == "commodity":
        available_margin = formatted_data.get('commodity', {}).get('available_margin', 0)
    else:
        # Use total available margin
        available_margin = formatted_data.get('totals', {}).get('total_available_margin', 0)
    
    # Check availability
    margin_available = available_margin >= required_margin
    shortfall = max(0, required_margin - available_margin)
    utilization_percent = (required_margin / available_margin * 100) if available_margin > 0 else 0
    
    result = {
        'required_margin': required_margin,
        'available_margin': available_margin,
        'margin_available': margin_available,
        'shortfall': shortfall,
        'utilization_percent': utilization_percent,
        'segment': segment,
        'remaining_margin': available_margin - required_margin if margin_available else 0
    }
    
    print(f"\n" + "="*50)
    print("MARGIN AVAILABILITY CHECK")
    print("="*50)
    print(f"Segment: {segment.upper()}")
    print(f"Required Margin: ₹{required_margin:,.2f}")
    print(f"Available Margin: ₹{available_margin:,.2f}")
    print(f"Margin Utilization: {utilization_percent:.1f}%")
    
    if margin_available:
        print(f"✅ Sufficient margin available")
        print(f"Remaining margin: ₹{result['remaining_margin']:,.2f}")
    else:
        print(f"❌ Insufficient margin")
        print(f"Shortfall: ₹{shortfall:,.2f}")
    
    print("="*50)
    
    return result


def get_margin_utilization_summary(access_token):
    """
    Get a summary of margin utilization across all segments.
    
    Args:
        access_token (str): The access token obtained from Token API
    
    Returns:
        dict: Margin utilization summary
    """
    print("Generating margin utilization summary...")
    
    funds_data = get_funds_and_margin(access_token)
    if not funds_data:
        return None
    
    formatted_data = format_funds_data(funds_data)
    if not formatted_data:
        return None
    
    equity_data = formatted_data.get('equity', {})
    commodity_data = formatted_data.get('commodity', {})
    totals = formatted_data.get('totals', {})
    
    # Calculate utilization percentages
    equity_utilization = 0
    commodity_utilization = 0
    
    if equity_data.get('available_margin', 0) > 0:
        equity_utilization = (equity_data.get('used_margin', 0) / 
                            equity_data.get('available_margin', 0) * 100)
    
    if commodity_data.get('available_margin', 0) > 0:
        commodity_utilization = (commodity_data.get('used_margin', 0) / 
                               commodity_data.get('available_margin', 0) * 100)
    
    total_utilization = 0
    if totals.get('total_available_margin', 0) > 0:
        total_utilization = (totals.get('total_used_margin', 0) / 
                           totals.get('total_available_margin', 0) * 100)
    
    summary = {
        'equity': {
            'available_margin': equity_data.get('available_margin', 0),
            'used_margin': equity_data.get('used_margin', 0),
            'utilization_percent': equity_utilization,
            'status': 'Good' if equity_utilization < 70 else 'High' if equity_utilization < 90 else 'Critical'
        },
        'commodity': {
            'available_margin': commodity_data.get('available_margin', 0),
            'used_margin': commodity_data.get('used_margin', 0),
            'utilization_percent': commodity_utilization,
            'status': 'Good' if commodity_utilization < 70 else 'High' if commodity_utilization < 90 else 'Critical'
        },
        'total': {
            'available_margin': totals.get('total_available_margin', 0),
            'used_margin': totals.get('total_used_margin', 0),
            'utilization_percent': total_utilization,
            'status': 'Good' if total_utilization < 70 else 'High' if total_utilization < 90 else 'Critical'
        }
    }
    
    print(f"\n📊 MARGIN UTILIZATION SUMMARY")
    print("="*60)
    print(f"Equity Utilization: {equity_utilization:.1f}% ({summary['equity']['status']})")
    print(f"Commodity Utilization: {commodity_utilization:.1f}% ({summary['commodity']['status']})")
    print(f"Total Utilization: {total_utilization:.1f}% ({summary['total']['status']})")
    print("="*60)
    
    return summary


# Example usage
if __name__ == "__main__":
    try:
        # Load access token from file
        with open('lib/core/accessToken.txt', 'r') as file:
            access_token = file.read().strip()
        
        print("="*60)
        print("FUNDS AND MARGIN EXAMPLES")
        print("="*60)
        
        # Example 1: Get all funds and margin data
        print("\n1. All Funds and Margin Data:")
        funds_data = get_funds_and_margin(access_token)
        if funds_data:
            formatted_data = format_funds_data(funds_data)
        
        # Example 2: Get equity funds only
        print("\n2. Equity Funds Only:")
        equity_funds = get_equity_funds(access_token)
        if equity_funds:
            print(f"Equity Available Margin: ₹{equity_funds.get('available_margin', 0):,.2f}")
        
        # Example 3: Get commodity funds only
        print("\n3. Commodity Funds Only:")
        commodity_funds = get_commodity_funds(access_token)
        if commodity_funds:
            print(f"Commodity Available Margin: ₹{commodity_funds.get('available_margin', 0):,.2f}")
        
        # Example 4: Check margin availability for an order
        print("\n4. Margin Availability Check:")
        required_margin = 10000  # Example required margin
        availability_check = check_margin_availability_for_order(access_token, required_margin, "equity")
        
        # Example 5: Get margin utilization summary
        print("\n5. Margin Utilization Summary:")
        utilization_summary = get_margin_utilization_summary(access_token)
        
    except FileNotFoundError:
        print("Error: accessToken.txt file not found")
    except Exception as e:
        print(f"Error: {e}")

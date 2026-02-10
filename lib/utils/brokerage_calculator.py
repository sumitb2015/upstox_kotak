import requests


def get_brokerage_details(access_token, instrument_token, quantity, product, transaction_type, price):
    """
    Get brokerage details for equity futures and options delivery orders.
    
    Args:
        access_token (str): The access token obtained from Token API
        instrument_token (str): Key of the instrument (e.g., 'NSE_FO|35271')
        quantity (int): Quantity with which the order is to be placed
        product (str): Product with which the order is to be placed (e.g., 'D' for delivery)
        transaction_type (str): Indicates whether its a BUY or SELL order
        price (float): Price with which the order is to be placed
    
    Returns:
        dict: Response containing brokerage details
    """
    url = 'https://api.upstox.com/v2/charges/brokerage'
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {access_token}'
    }
    
    params = {
        'instrument_token': instrument_token,
        'quantity': str(quantity),
        'product': product,
        'transaction_type': transaction_type,
        'price': str(price)
    }
    
    response = requests.get(url, headers=headers, params=params)
    
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error: {response.status_code}")
        return response.json()




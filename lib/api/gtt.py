import upstox_client
from upstox_client.rest import ApiException

def place_gtt_order(access_token, instrument_token, quantity, transaction_type, product, type, price, trigger_price):
    """
    Create a GTT order with single or OCO trigger.
    Note: Highly simplified version, check SDK for complex OCO triggers.
    
    Args:
        access_token (str): Access token
        instrument_token (str): Instrument token
        quantity (int): Quantity
        transaction_type (str): 'BUY' or 'SELL'
        product (str): 'D' or 'I'
        type (str): 'SINGLE' or 'OCO'
        price (float): Execution price
        trigger_price (float): Trigger price
    """
    configuration = upstox_client.Configuration()
    configuration.access_token = access_token
    api_instance = upstox_client.OrderApiV3(upstox_client.ApiClient(configuration))
    
    # This is a placeholder for the actual payload structure which can be complex
    # Refer to https://upstox.com/developer/api-documentation/#tag/GTT-Order
    # for the detailed JSON structure.
    
    # Example body (simplified)
    body = {
        "instrument_token": instrument_token,
        "quantity": quantity,
        "transaction_type": transaction_type,
        "product": product,
        "type": type,
        "rules": [
            {
                "strategy": "ENTRY",
                "trigger_price": trigger_price,
                "price": price
            }
        ]
    }
    
    try:
        # The SDK might have a GttOrderRequest class
        api_response = api_instance.place_gtt_order(body)
        return api_response.data
    except ApiException as e:
        print(f"Exception when calling OrderApiV3->place_gtt_order: {e}")
        return None

def cancel_gtt_order(access_token, gtt_order_id):
    """
    Cancel a GTT order.
    """
    configuration = upstox_client.Configuration()
    configuration.access_token = access_token
    api_instance = upstox_client.OrderApiV3(upstox_client.ApiClient(configuration))
    
    try:
        api_response = api_instance.cancel_gtt_order(gtt_order_id)
        return api_response.data
    except ApiException as e:
        print(f"Exception when calling OrderApiV3->cancel_gtt_order: {e}")
        return None

def get_gtt_order_details(access_token, gtt_order_id):
    """
    Get GTT order details.
    """
    configuration = upstox_client.Configuration()
    configuration.access_token = access_token
    api_instance = upstox_client.OrderApiV3(upstox_client.ApiClient(configuration))
    
    try:
        api_response = api_instance.get_gtt_order_details(gtt_order_id)
        return api_response.data
    except ApiException as e:
        print(f"Exception when calling OrderApiV3->get_gtt_order_details: {e}")
        return None

def modify_gtt_order(access_token, gtt_order_id, quantity=None, price=None, trigger_price=None):
    """
    Modify an existing GTT order.
    
    Args:
        access_token (str): Access token
        gtt_order_id (str): GTT order ID to modify
        quantity (int, optional): New quantity
        price (float, optional): New execution price
        trigger_price (float, optional): New trigger price
        
    Returns:
        dict: Modified GTT order details or None if error
    """
    configuration = upstox_client.Configuration()
    configuration.access_token = access_token
    api_instance = upstox_client.OrderApiV3(upstox_client.ApiClient(configuration))
    
    # Build modification payload
    body = {}
    if quantity is not None:
        body['quantity'] = quantity
    if price is not None:
        body['price'] = price
    if trigger_price is not None:
        body['trigger_price'] = trigger_price
    
    try:
        api_response = api_instance.modify_gtt_order(gtt_order_id, body)
        print(f"✅ GTT order {gtt_order_id} modified successfully")
        return api_response.data
    except ApiException as e:
        print(f"Exception when calling OrderApiV3->modify_gtt_order: {e}")
        return None

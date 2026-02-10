import upstox_client
from upstox_client.rest import ApiException
import pandas as pd

def get_holdings(access_token):
    """
    Fetches the list of all holdings in the user's account.
    
    Args:
        access_token (str): The access token obtained from Token API
        
    Returns:
        pd.DataFrame: Holdings data
    """
    configuration = upstox_client.Configuration()
    configuration.access_token = access_token
    api_instance = upstox_client.PortfolioApi(upstox_client.ApiClient(configuration))
    
    try:
        api_response = api_instance.get_holdings("2.0")
        if not api_response.data:
            return pd.DataFrame()
        
        # Convert objects to dicts for DataFrame
        holdings_list = []
        for holding in api_response.data:
            holdings_list.append({
                'trading_symbol': holding.trading_symbol,
                'isin': holding.isin,
                'quantity': holding.quantity,
                'last_price': holding.last_price,
                'pnl': holding.pnl,
                'product': holding.product,
                'average_price': holding.average_price,
                'collateral_quantity': holding.collateral_quantity,
                'collateral_type': holding.collateral_type
            })
        return pd.DataFrame(holdings_list)
    except ApiException as e:
        print(f"Exception when calling PortfolioApi->get_holdings: {e}")
        return pd.DataFrame()

def get_positions(access_token):
    """
    Retrieves both day-wise and net positions.
    
    Args:
        access_token (str): The access token obtained from Token API
        
    Returns:
        pd.DataFrame: Positions data
    """
    configuration = upstox_client.Configuration()
    configuration.access_token = access_token
    api_instance = upstox_client.PortfolioApi(upstox_client.ApiClient(configuration))
    
    try:
        api_response = api_instance.get_positions("2.0")
        if not api_response.data:
            return pd.DataFrame()
        
        positions_list = []
        for pos in api_response.data:
            positions_list.append({
                'trading_symbol': pos.trading_symbol,
                'instrument_token': pos.instrument_token,
                'product': pos.product,
                'quantity': pos.quantity,
                'last_price': pos.last_price,
                'buy_price': pos.buy_price,
                'sell_price': pos.sell_price,
                'pnl': pos.pnl,
                'realised_profit': pos.realised_profit,
                'unrealised_profit': pos.unrealised_profit,
                'buy_quantity': pos.buy_quantity,
                'sell_quantity': pos.sell_quantity
            })
        return pd.DataFrame(positions_list)
    except ApiException as e:
        print(f"Exception when calling PortfolioApi->get_positions: {e}")
        return pd.DataFrame()

def convert_position(access_token, instrument_key, new_product, old_product, transaction_type, quantity):
    """
    Convert position between products (e.g., from Intraday to Delivery).
    
    Args:
        access_token (str): The access token
        instrument_key (str): Instrument key
        new_product (str): New product type (e.g., 'D' or 'I')
        old_product (str): Old product type
        transaction_type (str): 'BUY' or 'SELL'
        quantity (int): Quantity to convert
        
    Returns:
        dict: API response
    """
    configuration = upstox_client.Configuration()
    configuration.access_token = access_token
    api_instance = upstox_client.PortfolioApi(upstox_client.ApiClient(configuration))
    
    body = upstox_client.ConvertPositionRequest(
        instrument_token=instrument_key,
        new_product=new_product,
        old_product=old_product,
        transaction_type=transaction_type,
        quantity=quantity
    )
    
    try:
        api_response = api_instance.convert_positions(body, "2.0")
        return api_response
    except ApiException as e:
        print(f"Exception when calling PortfolioApi->convert_positions: {e}")
        return None

import upstox_client
from upstox_client.rest import ApiException
import pandas as pd
from lib.core.config import Config
import time

def _get_api_client(access_token):
    """Helper to get configured API client"""
    configuration = upstox_client.Configuration()
    configuration.access_token = access_token
    return upstox_client.ApiClient(configuration)

def get_order_book(access_token):
    """
    Fetch order book (all orders) using Upstox SDK.
    """
    print("Fetching order book...")
    api_instance = upstox_client.OrderApi(_get_api_client(access_token))
    
    try:
        api_response = api_instance.get_order_book()
        
        if not api_response.data:
            print("No orders found in order book")
            return pd.DataFrame()
        
        # Convert to DataFrame
        # The SDK returns objects, we need to convert them to dicts
        orders_list = [order.to_dict() for order in api_response.data]
        df_orders = pd.DataFrame(orders_list)
        
        # Convert timestamp columns to datetime if they exist
        # SDK might return them as strings or datetime objects already
        # We'll check and convert standard columns
        time_cols = ["order_timestamp", "exchange_timestamp", "status_update_timestamp"]
        for col in time_cols:
            if col in df_orders.columns:
                df_orders[col] = pd.to_datetime(df_orders[col], errors='coerce')
        
        print(f"Successfully fetched {len(df_orders)} orders")
        return df_orders
        
    except ApiException as e:
        print(f"Exception when calling OrderApi->get_order_book: {e}")
        return pd.DataFrame()
    except Exception as e:
        print(f"Error fetching order book: {e}")
        return pd.DataFrame()

def get_order_summary(access_token):
    """
    Get a summary of orders with key information.
    """
    print("Fetching order summary...")
    
    df_orders = get_order_book(access_token)
    if df_orders.empty:
        return pd.DataFrame()
    
    # Create summary with key fields
    # Note: SDK field names might be camelCase or snake_case depending on version, 
    # but to_dict() usually standardizes to snake_case equivalent of JSON response
    summary_columns = [
        "order_id", "trading_symbol", "transaction_type", "order_type", 
        "quantity", "filled_quantity", "pending_quantity", "price", 
        "average_price", "status", "status_message", "order_timestamp"
    ]
    
    # Filter to only include columns that exist
    available_columns = [col for col in summary_columns if col in df_orders.columns]
    df_summary = df_orders[available_columns].copy()
    
    print(f"Order summary created with {len(df_summary)} orders")
    return df_summary

def place_order(access_token, instrument_token, quantity=75, transaction_type="BUY", order_type="MARKET", 
                price=0.0, product="D", validity="DAY", disclosed_quantity=0, trigger_price=0.0, 
                is_amo=False, slice=True, tag="string"):
    """
    Place an order using Upstox SDK.
    """
    if Config.is_verbose():
        print(f"Placing {transaction_type} order for {quantity} units of {instrument_token}")
    
    api_instance = upstox_client.OrderApi(_get_api_client(access_token))
    
    # Construct the request body
    # Only include non-zero/non-empty values where necessary to avoid API rejection
    body = upstox_client.PlaceOrderRequest(
        quantity=int(quantity),
        product=product,
        validity=validity,
        price=float(price),
        tag=tag,
        instrument_token=instrument_token,
        order_type=order_type,
        transaction_type=transaction_type,
        disclosed_quantity=int(disclosed_quantity),
        trigger_price=float(trigger_price),
        is_amo=is_amo
    )
    
    try:
        api_response = api_instance.place_order(body, api_version='2.0')
        
        if api_response.status == "success":
            # api_response.data is typically an object with order_id
            order_id = api_response.data.order_id
            
            if Config.is_verbose():
                print(f"Order placed successfully! Order ID: {order_id}")
            
            # Return a dict to match previous return signature expectation
            return api_response.to_dict()
        else:
            print(f"Order placement failed: {api_response}")
            return None
            
    except ApiException as e:
        print(f"Exception when calling OrderApi->place_order: {e}")
        return None
    except Exception as e:
        print(f"Error placing order: {e}")
        return None

def modify_order(access_token, order_id, quantity=None, price=None, order_type=None, trigger_price=None, validity=None):
    """
    Modify an existing open order using SDK.
    """
    print(f"Modifying order: {order_id}")
    api_instance = upstox_client.OrderApi(_get_api_client(access_token))
    
    body = upstox_client.ModifyOrderRequest(
        order_id=order_id,
        quantity=int(quantity) if quantity is not None else None,
        price=float(price) if price is not None else None,
        order_type=order_type,
        trigger_price=float(trigger_price) if trigger_price is not None else None,
        validity=validity
    )
    
    try:
        api_response = api_instance.modify_order(body, api_version='2.0')
        return api_response.to_dict()
    except ApiException as e:
        print(f"Exception when calling OrderApi->modify_order: {e}")
        return None
    except Exception as e:
        print(f"Error modifying order: {e}")
        return None

def get_order_details(access_token, order_id):
    """
    Get details for a specific Order ID.
    """
    api_instance = upstox_client.OrderApi(_get_api_client(access_token))
    
    try:
        api_response = api_instance.get_order_details(order_id=order_id, api_version='2.0')
        if api_response.data:
             # Convert list of history items to details
             return [item.to_dict() for item in api_response.data]
        return None
    except ApiException as e:
        print(f"Exception when calling OrderApi->get_order_details: {e}")
        return None

def exit_positions(access_token, instrument_key=None, product=None):
    """
    Square off positions (Not fully supported by SDK in one go usually, but we check OrderApi).
    SDK has exit_positions method? Checked: Yes, it has exit_positions.
    """
    api_instance = upstox_client.OrderApi(_get_api_client(access_token))
    
    tag = "exit_all" 
    # The SDK method signature might vary: exit_positions(tag=tag, instrument_token=..., product=...)
    
    try:
        # Check if we can target specific instrument or all
        # Passing None for optional args to exit all matching (or filtered)
        api_response = api_instance.exit_positions(
            tag=tag,
            instrument_token=instrument_key,
            product=product,
            api_version='2.0'
        )
        return api_response.to_dict()
    except ApiException as e:
        print(f"Exception when calling OrderApi->exit_positions: {e}")
        return None

def place_multi_order(access_token, orders):
    """
    Place multiple orders. SDK supports place_multi_order.
    orders: List of dictionary params for place_order
    """
    api_instance = upstox_client.OrderApi(_get_api_client(access_token))
    
    # Convert dict orders to PlaceOrderRequest objects
    multi_order_request_list = []
    for order in orders:
        # Map fields
        req = upstox_client.PlaceOrderRequest(
            quantity=int(order.get('quantity')),
            product=order.get('product', 'D'),
            validity=order.get('validity', 'DAY'),
            price=float(order.get('price', 0.0)),
            tag=order.get('tag', 'multi_order'),
            instrument_token=order.get('instrument_token'),
            order_type=order.get('order_type', 'MARKET'),
            transaction_type=order.get('transaction_type'),
            disclosed_quantity=int(order.get('disclosed_quantity', 0)),
            trigger_price=float(order.get('trigger_price', 0.0)),
            is_amo=order.get('is_amo', False)
        )
        multi_order_request_list.append(req)
        
    try:
        # The SDK expects a list of PlaceOrderRequest
        api_response = api_instance.place_multi_order(multi_order_request_list, api_version='2.0')
        return api_response.to_dict()
    except ApiException as e:
        print(f"Exception when calling OrderApi->place_multi_order: {e}")
        return None

def cancel_order(access_token, order_id):
    """
    Cancel an order.
    """
    if Config.is_verbose():
        print(f"Cancelling order: {order_id}")
    
    api_instance = upstox_client.OrderApi(_get_api_client(access_token))
    
    try:
        api_response = api_instance.cancel_order(order_id, api_version='2.0')
        
        if Config.is_verbose():
             print(f"Order cancelled successfully: {order_id}")
             
        return api_response.to_dict()
            
    except ApiException as e:
        print(f"Request error when cancelling order: {e}")
        return None
    except Exception as e:
        print(f"Exception when cancelling order: {e}")
        return None

def cancel_multiple_orders(access_token, order_ids):
    """
    Cancel multiple orders. SDK supports cancel_multi_order? 
    Checked: Yes, cancel_multi_order.
    Alternatively, iterate.
    """
    if Config.is_verbose():
        print(f"Cancelling {len(order_ids)} orders...")
        
    # If SDK supports batch cancel, we should use it. Note: 'cancel_multi_order' might exist but accept order_id list?
    # Let's check signature strictly? It usually takes 'order_id' as query param or body. 
    # To be safe and consistent with previous behavior, let's iterate for now unless we are sure.
    # Actually, previous implementation iterated.
    
    results = []
    for i, order_id in enumerate(order_ids, 1):
        print(f"\nCancelling order {i}/{len(order_ids)}: {order_id}")
        result = cancel_order(access_token, order_id)
        results.append(result)
        # Avoid rate limiting if necessary, though SDK handles some retry?
        if i < len(order_ids):
            time.sleep(0.1)
            
    return results

def cancel_all_orders(access_token, status_filter=None):
    """
    Cancel all orders or orders with specific status.
    """
    print("Fetching orders to cancel...")
    df_orders = get_order_book(access_token)
    
    if df_orders.empty:
        print("No orders found to cancel")
        return []
    
    # Filter by status
    if status_filter:
        orders_to_cancel = df_orders[df_orders['status'] == status_filter]
    else:
        # Cancel all open/pending
        orders_to_cancel = df_orders[df_orders['status'].isin(['open', 'trigger_pending', 'after market order req received'])]
        
    if orders_to_cancel.empty:
        print("No orders found to cancel")
        return []
        
    order_ids = orders_to_cancel['order_id'].tolist()
    return cancel_multiple_orders(access_token, order_ids)

def get_trades_for_day(access_token):
    """
    Get all trades executed for the current day.
    SDK: get_trade_history
    """
    print("Fetching trades for the day...")
    api_instance = upstox_client.OrderApi(_get_api_client(access_token))
    
    try:
        api_response = api_instance.get_trade_history(api_version='2.0')
        
        if not api_response.data:
            print("No trades found for today")
            return pd.DataFrame()
            
        trades_list = [trade.to_dict() for trade in api_response.data]
        df_trades = pd.DataFrame(trades_list)
        
        # Convert timestamps
        time_cols = ["order_timestamp", "exchange_timestamp", "trade_timestamp"]
        for col in time_cols:
            if col in df_trades.columns:
                df_trades[col] = pd.to_datetime(df_trades[col], errors='coerce')
                
        print(f"Successfully fetched {len(df_trades)} trades for today")
        return df_trades
        
    except ApiException as e:
        print(f"Request error when fetching trades: {e}")
        return pd.DataFrame()
    except Exception as e:
        print(f"Exception when fetching trades: {e}")
        return pd.DataFrame()

def get_trades_summary(access_token):
    """Get summary of trades"""
    print("Generating trades summary...")
    df_trades = get_trades_for_day(access_token)
    
    if df_trades.empty:
        return {
            "total_trades": 0,
            "total_quantity": 0,
            "total_value": 0,
            "buy_trades": 0,
            "sell_trades": 0,
            "symbols_traded": [],
            "exchanges": [],
            "summary_df": pd.DataFrame()
        }
        
    # Calculate summary
    total_trades = len(df_trades)
    total_quantity = df_trades['quantity'].sum() if 'quantity' in df_trades else 0
    # Average price might be 0 if not set, strict check
    df_trades['value'] = df_trades.apply(lambda x: x.get('quantity',0) * x.get('average_price',0), axis=1)
    total_value = df_trades['value'].sum()
    
    buy_trades = len(df_trades[df_trades['transaction_type'] == 'BUY']) if 'transaction_type' in df_trades else 0
    sell_trades = len(df_trades[df_trades['transaction_type'] == 'SELL']) if 'transaction_type' in df_trades else 0
    
    symbols_traded = df_trades['trading_symbol'].unique().tolist() if 'trading_symbol' in df_trades else []
    exchanges = df_trades['exchange'].unique().tolist() if 'exchange' in df_trades else []
    
    # GroupBy
    summary_df = pd.DataFrame()
    if 'trading_symbol' in df_trades and 'transaction_type' in df_trades:
        summary_df = df_trades.groupby(['trading_symbol', 'transaction_type']).agg({
            'quantity': 'sum',
            'average_price': 'mean',
            'order_id': 'count'
        }).round(2)
        summary_df.columns = ['Total_Quantity', 'Avg_Price', 'Trade_Count']
        summary_df = summary_df.reset_index()
        
    return {
        "total_trades": total_trades,
        "total_quantity": int(total_quantity),
        "total_value": round(total_value, 2),
        "buy_trades": buy_trades,
        "sell_trades": sell_trades,
        "symbols_traded": symbols_traded,
        "exchanges": exchanges,
        "summary_df": summary_df
    }

def get_trades_by_symbol(access_token, symbol):
    """Filter trades by symbol"""
    print(f"Fetching trades for symbol: {symbol}")
    df_trades = get_trades_for_day(access_token)
    if df_trades.empty: return pd.DataFrame()
    
    filtered = df_trades[df_trades['trading_symbol'] == symbol]
    if filtered.empty: print(f"No trades found for {symbol}")
    return filtered

def get_trades_by_exchange(access_token, exchange):
    """Filter trades by exchange"""
    print(f"Fetching trades for exchange: {exchange}")
    df_trades = get_trades_for_day(access_token)
    if df_trades.empty: return pd.DataFrame()
    
    filtered = df_trades[df_trades['exchange'] == exchange]
    if filtered.empty: print(f"No trades found for {exchange}")
    return filtered

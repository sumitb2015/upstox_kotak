"""
Order Placement Helper Utilities

Provides clean, abstracted order placement functions that handle:
- Automatic lot size lookup
- Quantity calculation
- Error handling
- Consistent logging
"""

from typing import Optional, Dict, Any
from lib.utils.instrument_utils import get_lot_size
from lib.api.order_management import place_order


def place_option_order(
    access_token: str,
    instrument_key: str,
    nse_data,
    num_lots: int,
    transaction_type: str,
    product_type: str = "INTRADAY",
    order_type: str = "MARKET",
    validity: str = "DAY",
    price: float = 0.0,
    trigger_price: float = 0.0
) -> Optional[Dict[str, Any]]:
    """
    Place an option order with automatic lot size handling.
    
    This function abstracts away the complexity of:
    - Looking up lot size from NSE data
    - Calculating correct quantity
    - Handling order placement
    
    Args:
        access_token: Upstox access token
        instrument_key: Option instrument key (e.g., "NSE_FO|12345")
        nse_data: NSE market data DataFrame
        num_lots: Number of lots to trade (strategy-level parameter)
        transaction_type: "BUY" or "SELL"
        product_type: "INTRADAY", "DELIVERY", etc.
        order_type: "MARKET", "LIMIT", "SL", "SL-M"
        validity: "DAY", "IOC"
        price: Limit price (for LIMIT orders)
        trigger_price: Trigger price (for SL orders)
    
    Returns:
        Order response dict if successful, None if failed
    
    Example:
        >>> order = place_option_order(
        ...     access_token=token,
        ...     instrument_key="NSE_FO|58689",
        ...     nse_data=nse_df,
        ...     num_lots=2,
        ...     transaction_type="SELL",
        ...     product_type="INTRADAY"
        ... )
    """
    try:
        # Get actual lot size from NSE data
        lot_size = get_lot_size(instrument_key, nse_data)
        
        # Calculate total quantity
        quantity = num_lots * lot_size
        
        # Place order
        order_response = place_order(
            access_token=access_token,
            instrument_token=instrument_key,
            quantity=quantity,
            transaction_type=transaction_type,
            order_type=order_type,
            product=product_type,
            validity=validity,
            price=price,
            trigger_price=trigger_price
        )
        
        return order_response
        
    except Exception as e:
        print(f"Error placing option order: {e}")
        return None


def place_futures_order(
    access_token: str,
    instrument_key: str,
    nse_data,
    num_lots: int,
    transaction_type: str,
    product_type: str = "INTRADAY",
    order_type: str = "MARKET",
    validity: str = "DAY",
    price: float = 0.0,
    trigger_price: float = 0.0
) -> Optional[Dict[str, Any]]:
    """
    Place a futures order with automatic lot size handling.
    
    Same as place_option_order but semantically named for futures.
    
    Args:
        Same as place_option_order
    
    Returns:
        Order response dict if successful, None if failed
    """
    return place_option_order(
        access_token=access_token,
        instrument_key=instrument_key,
        nse_data=nse_data,
        num_lots=num_lots,
        transaction_type=transaction_type,
        product_type=product_type,
        order_type=order_type,
        validity=validity,
        price=price,
        trigger_price=trigger_price
    )


def get_order_quantity(instrument_key: str, nse_data, num_lots: int) -> int:
    """
    Calculate order quantity for a given instrument and number of lots.
    
    This is a utility function for strategies that need to calculate
    quantity without placing an order immediately.
    
    Args:
        instrument_key: Instrument key
        nse_data: NSE market data DataFrame
        num_lots: Number of lots
    
    Returns:
        int: Total quantity (num_lots × lot_size)
    
    Example:
        >>> qty = get_order_quantity("NSE_FO|58689", nse_df, 2)
        >>> print(qty)  # 130 (for Nifty with lot size 65)
    """
    lot_size = get_lot_size(instrument_key, nse_data)
    return num_lots * lot_size

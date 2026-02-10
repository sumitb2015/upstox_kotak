"""
OrderManager: Handles order placement and status checking.

This module provides:
- Order placement with dry-run support
- Order status verification
- Retry logic and error handling
"""

import time
import logging
import sys

logger = logging.getLogger(__name__)


class OrderManager:
    """
    Manages order placement and tracking.
    
    Attributes:
        client (NeoAPI): Broker API client
        dry_run (bool): If True, simulates orders without actual placement
    """
    
    def __init__(self, client, dry_run=False):
        """
        Initialize order manager.
        """
        self.client = client
        self.dry_run = dry_run
        self.failed_orders = {} # {symbol: count}
        self.max_retries = 3
    
    def place_order(self, symbol, qty, transaction_type, tag="", order_type="MKT", exchange_segment="nse_fo", product="MIS"):
        """
        Place an order.
        """
        # Check Retry Limit
        fail_count = self.failed_orders.get(symbol, 0)
        if fail_count >= self.max_retries:
             error_msg = f"⛔ Max Retries ({self.max_retries}) reached for {symbol}. Exiting Strategy."
             logger.critical(error_msg)
             sys.exit(1)

        action = "BUY" if transaction_type == "B" else "SELL"
        prefix = "[DRY RUN] " if self.dry_run else ""
        logger.info(f"{prefix}[KOTAK] ORDER: {action} {qty} x {symbol} [{tag}]")

        if self.dry_run:
            logger.info(f"DRY RUN: Order simulated")
            # Simulate Success: Reset counter
            if symbol in self.failed_orders: del self.failed_orders[symbol]
            return "DRY_RUN_ORDER_ID"
        
        try:
            response = self.client.place_order(
                exchange_segment=exchange_segment,
                product=product,
                price="0",
                order_type=order_type,
                quantity=str(qty),
                validity="DAY",
                trading_symbol=symbol,
                transaction_type=transaction_type,
                amo="NO"
            )
            
            if response and isinstance(response, dict) and 'nOrdNo' in response:
                order_id = response['nOrdNo']
                logger.info(f"[KOTAK] Order Placed! ID: {order_id}")
                time.sleep(1)  # Wait for order processing
                status = self.check_order_status(order_id)
                
                if status.lower() in ['complete', 'filled', 'open', 'pending']:
                    # Success - Reset Retry Counter
                    if symbol in self.failed_orders:
                        del self.failed_orders[symbol]
                    return str(order_id)
                else:
                    # Order Rejected/Failed
                    self.failed_orders[symbol] = self.failed_orders.get(symbol, 0) + 1
                    logger.warning(f"⚠️ [KOTAK] Order {order_id} Status: {status} (Attempt {self.failed_orders[symbol]}/{self.max_retries})")
                    return None
            else:
                logger.error(f"Order API error: {response}")
                self.failed_orders[symbol] = self.failed_orders.get(symbol, 0) + 1
                return None
                
        except Exception as e:
            logger.error(f"Order Exception: {e}")
            self.failed_orders[symbol] = self.failed_orders.get(symbol, 0) + 1
            return None
    
    def check_order_status(self, order_id):
        """
        Check status of a specific order.
        """
        try:
            logger.info(f"[KOTAK] Checking status for Order ID: {order_id}")
            report = self.client.order_report()
            
            if not report or not isinstance(report, dict):
                return "Unknown"
            
            data = report.get('data', [])
            for order in data:
                if str(order.get('nOrdNo')) == str(order_id):
                    status = order.get('ordSt', 'Unknown')
                    logger.info(f"Order {order_id} Status: {status}")
                    return status
            
            return "NotFound"
        except Exception as e:
            logger.error(f"Error checking status: {e}")
            return "Error"

    def cancel_order(self, order_id, is_amo=False):
        """
        Cancel an open order.
        """
        if self.dry_run:
            logger.info(f"DRY RUN: Order {order_id} cancelled")
            return True
            
        try:
            logger.info(f"Cancelling Order {order_id}...")
            resp = self.client.cancel_order(order_id=str(order_id), amo="YES" if is_amo else "NO")
            if resp and isinstance(resp, dict) and resp.get('stat') == "Ok":
                logger.info(f"Cancellation sent for {order_id}")
                return True
            else:
                logger.error(f"Cancel failed: {resp}")
                return False
        except Exception as e:
            logger.error(f"Cancel Exception: {e}")
            return False

    def modify_order(self, order_id, price=None, quantity=None, trigger_price=None, validity="DAY", is_amo=False):
        """
        Modify an open order.
        """
        if self.dry_run:
            logger.info(f"DRY RUN: Order {order_id} modified (Qty: {quantity}, Price: {price})")
            return True
            
        try:
            logger.info(f"Modifying Order {order_id}...")
            resp = self.client.modify_order(
                order_id=str(order_id),
                price=str(price) if price else "0",
                quantity=str(quantity) if quantity else None,
                trigger_price=str(trigger_price) if trigger_price else None,
                validity=validity,
                amo="YES" if is_amo else "NO"
            )
            
            if resp and isinstance(resp, dict) and resp.get('stat') == "Ok":
                logger.info(f"Modification sent for {order_id}")
                return True
            else:
                logger.error(f"Modify failed: {resp}")
                return False
        except Exception as e:
            logger.error(f"Modify Exception: {e}")
            return False

    def get_trade_report(self):
        """
        Fetch trade report (filled orders).
        """
        try:
            logger.info(f"Fetching Trade Report...")
            report = self.client.trade_report()
            if report and isinstance(report, dict):
                return report.get('data', [])
            return None
        except Exception as e:
            logger.error(f"Error fetching trade report: {e}")
            return None

    def get_order_history(self, order_id):
        """
        Get history of a specific order.
        """
        try:
            logger.info(f"Fetching History for {order_id}...")
            hist = self.client.order_history(order_id=str(order_id))
            if hist and isinstance(hist, dict):
                return hist.get('data', [])
            return None
            return None
        except Exception as e:
            logger.error(f"Error fetching history: {e}")
            return None

    def is_blocked(self, symbol):
        """Check if a symbol is blocked due to max retries."""
        return self.failed_orders.get(symbol, 0) >= self.max_retries

    def get_execution_price(self, order_id):
        """
        Fetch the actual execution price (Avg Price) for a completed order.
        """
        if self.dry_run: return 0.0
        
        try:
            # 1. Try Order Report Logic first (usually faster/easier if contained there)
            report = self.client.order_report()
            if report and isinstance(report, dict):
                data = report.get('data', [])
                for order in data:
                    if str(order.get('nOrdNo')) == str(order_id):
                        # Kotak usually calls it 'avgPrc' or 'AvgPrice'
                        # Based on docs/common structures, check likely keys
                        # Note: This depends on the exact API response structure.
                        # Assuming 'avgPrc' based on standard Neo API patterns.
                        avg_prc = order.get('avgPrc', 0.0)
                        if avg_prc: return float(avg_prc)
                        
                        # Fallback: Maybe it's not in 'avgPrc', check if status filled and use price? No, incorrect.
                        pass
                        
            # 2. Try Trade Report (Confirmed trades)
            trades = self.client.trade_report()
            if trades and isinstance(trades, dict):
                data = trades.get('data', [])
                # Could be multiple fills for one order
                total_val = 0.0
                total_qty = 0
                found = False
                
                for trade in data:
                    if str(trade.get('nOrdNo')) == str(order_id):
                        qty = float(trade.get('qty', 0))
                        price = float(trade.get('prc', 0)) # 'prc' refers to trade price usually
                        total_val += (qty * price)
                        total_qty += qty
                        found = True
                        
                if found and total_qty > 0:
                    return total_val / total_qty

            return 0.0 # Not found or unfilled
            
        except Exception as e:
            logger.error(f"Error fetching execution price for {order_id}: {e}")
            return 0.0

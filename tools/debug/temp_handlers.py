    # --- WebSocket Order Update Handlers ---
    
    def _handle_order_update(self, order_info):
        """
        Callback for real-time order status updates via Portfolio WebSocket.
        
        Args:
            order_info (dict): Order update with status, filled_qty, average_price, etc.
        """
        try:
            order_id = order_info.get('order_id')
            status = order_info.get('status')
            filled_qty = order_info.get('filled_quantity', 0)
            avg_price = order_info.get('average_price', 0)
            
            if not order_id:
                return
            
            # Update cache
            self.order_status_cache[order_id] = {
                'status': status,
                'filled_quantity': filled_qty,
                'average_price': avg_price,
                'timestamp': datetime.now(),
                'raw_data': order_info
            }
            
            # Trigger any waiting threads
            if order_id in self.order_update_events:
                self.order_update_events[order_id].set()
            
            # Log in verbose mode
            if self.verbose:
                symbol = order_info.get('trading_symbol', 'N/A')
                print(f"📡 Order Update: {order_id[:8]}... | {symbol} | Status: {status} | Filled: {filled_qty} @ ₹{avg_price:.2f}")
                
        except Exception as e:
            if self.verbose:
                print(f"Error handling order update: {e}")
    
    def _handle_position_update(self, position_info):
        """
        Callback for real-time position updates via Portfolio WebSocket.
        
        Args:
            position_info (dict): Position update with instrument, quantity, P&L, etc.
        """
        try:
            instrument_key = position_info.get('instrument_key')
            symbol = position_info.get('trading_symbol', 'N/A')
            quantity = position_info.get('quantity', 0)
            pnl = position_info.get('pnl', 0)
            
            # Log in verbose mode
            if self.verbose:
                print(f"📈 Position Update: {symbol} | Qty: {quantity} | P&L: ₹{pnl:.2f}")
                
        except Exception as e:
            if self.verbose:
                print(f"Error handling position update: {e}")
    
    def wait_for_order_fill(self, order_id, timeout=30):
        """
        Wait for order to be filled using WebSocket updates.
        
        Args:
            order_id (str): Order ID to wait for
            timeout (int): Maximum seconds to wait
            
        Returns:
            dict: Order status info or None if timeout
        """
        import threading
        
        try:
            # Create event for this order if not exists
            if order_id not in self.order_update_events:
                self.order_update_events[order_id] = threading.Event()
            
            # Wait for update or timeout
            if self.order_update_events[order_id].wait(timeout):
                # Got update - return cached status
                return self.order_status_cache.get(order_id)
            else:
                # Timeout - return None (will fallback to REST in calling code)
                if self.verbose:
                    print(f"⚠️ WebSocket timeout for order {order_id[:8]}...")
                return None
                
        except Exception as e:
            if self.verbose:
                print(f"Error waiting for order fill: {e}")
            return None

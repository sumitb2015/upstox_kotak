"""
PositionTracker: Tracks positions and calculates MTM.

This module provides:
- Position tracking isolated to specific strategy
- MTM calculation (total and unrealized separately)
- Cumulative realized PnL tracking
"""

import time


class PositionTracker:
    """
    Tracks positions and calculates MTM for a specific strategy.
    
    Calculates:
    - Total MTM = Unrealized PnL (current positions) + Cumulative Realized PnL (past trades)
    - Unrealized PnL = Current active trade only (for TSL/targets)
    
    Attributes:
        client (NeoAPI): Broker API client
        data_store (DataStore): Data store for LTP prices
        positions (dict): Current positions {side: {token, qty, strike, ...}}
        cumulative_realized_pnl (float): Realized PnL from closed positions
    
    Example:
        >>> from lib.broker import BrokerClient  
        >>> from lib.data_store import DataStore
        >>> 
        >>> broker = BrokerClient()
        >>> broker.authenticate()
        >>> data_store = DataStore()
        >>> 
        >>> tracker = PositionTracker(broker.client, data_store)
        >>> tracker.positions = {'CE': {'token': '12345', 'qty': -50, 'strike': 24200}}
        >>> total_mtm, active_mtm = tracker.calculate_mtm()
    """
    
    def __init__(self, client, data_store):
        """
        Initialize position tracker.
        
        Args:
            client (NeoAPI): Authenticated broker client
            data_store (DataStore): Data store instance
        """
        self.client = client
        self.data_store = data_store
        self.positions = {}
        self.cumulative_realized_pnl = 0.0
        
        # MTM caching
        self.last_mtm_update = 0
        self.cached_mtm = 0.0
        self.cached_unrealized_pnl = 0.0
    
    def calculate_mtm(self, cache_duration=5):
        """
        Calculate strategy-isolated MTM.
        
        Returns:
            tuple: (total_mtm, unrealized_pnl) where:
                - total_mtm: Unrealized + Cumulative Realized (overall strategy performance)
                - unrealized_pnl: Current active trade only (for TSL/target decisions)
        
        Args:
            cache_duration (int, optional): Cache duration in seconds. Defaults to 5.
        """
        # Check cache
        if time.time() - self.last_mtm_update < cache_duration:
            return self.cached_mtm, self.cached_unrealized_pnl
        
        unrealized_pnl = 0.0
        
        # Get active tokens for this strategy
        active_tokens = set()
        for key, pos in self.positions.items():
            if 'token' in pos:
                active_tokens.add(str(pos['token']))
        
        if not active_tokens:
            # No positions, return only realized PnL
            return self.cumulative_realized_pnl, 0.0
        
        try:
            positions_data = self.client.positions()
            if not positions_data or 'data' not in positions_data:
                return self.cumulative_realized_pnl, 0.0
            
            # Calculate unrealized PnL for ONLY this strategy's active positions
            for pos in positions_data['data']:
                try:
                    tok = str(pos.get('tok', pos.get('tk', '')))
                    
                    # Filter: Only this strategy's active positions
                    if tok not in active_tokens:
                        continue
                    
                    # Parse amounts
                    buy_amt = float(pos.get('buyAmt', 0) or 0)
                    cf_buy_amt = float(pos.get('cfBuyAmt', 0) or 0)
                    sell_amt = float(pos.get('sellAmt', 0) or 0)
                    cf_sell_amt = float(pos.get('cfSellAmt', 0) or 0)
                    
                    total_buy_amt = buy_amt + cf_buy_amt
                    total_sell_amt = sell_amt + cf_sell_amt
                    
                    # Parse quantities
                    fl_buy_qty = int(pos.get('flBuyQty', 0) or 0)
                    cf_buy_qty = int(pos.get('cfBuyQty', 0) or 0)
                    fl_sell_qty = int(pos.get('flSellQty', 0) or 0)
                    cf_sell_qty = int(pos.get('cfSellQty', 0) or 0)
                    
                    net_qty = (fl_buy_qty + cf_buy_qty) - (fl_sell_qty + cf_sell_qty)
                    
                    # Get multiplier and LTP
                    multiplier = float(pos.get('multiplier', 1) or 1)
                    ltp = self.data_store.get_ltp(tok)
                    if ltp == 0:
                        ltp = float(pos.get('lp', 0) or 0)
                    
                    # Calculate PnL: (SellAmt - BuyAmt) + (NetQty * LTP * Multiplier)
                    pnl = (total_sell_amt - total_buy_amt) + (net_qty * ltp * multiplier)
                    unrealized_pnl += pnl
                    
                except Exception:
                    continue
        
        except Exception:
            pass
        
        # Total Strategy MTM = Unrealized + Realized
        total_mtm = unrealized_pnl + self.cumulative_realized_pnl
        
        # Update cache
        self.cached_mtm = total_mtm
        self.cached_unrealized_pnl = unrealized_pnl
        self.last_mtm_update = time.time()
        
        return total_mtm, unrealized_pnl
    
    def add_realized_pnl(self, pnl):
        """
        Add realized PnL from a closed position.
        
        Args:
            pnl (float): Realized PnL to add
        """
        self.cumulative_realized_pnl += pnl
        print(f"  💰 Realized PnL: ₹{pnl:.2f} | Cumulative: ₹{self.cumulative_realized_pnl:.2f}")

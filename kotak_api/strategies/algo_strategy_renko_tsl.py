"""
Algo Strategy: Renko-Based Nifty Option Selling
Status: EXPERIMENTAL

Logic:
1. Construct Renko Bricks (Size 15) from Nifty Spot (Live).
2. Signal:
   - SELL CE after 3 consecutive RED bricks (Bearish Trend)
   - SELL PE after 3 consecutive GREEN bricks (Bullish Trend)
3. Exit:
   - Reversal Brick Formation (e.g. holding CE and Green Brick forms).
"""

import os
import sys
import time
import threading
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# Force UTF-8 encoding for Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Add lib to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Library imports
from lib.broker import BrokerClient
from lib.data_store import DataStore
from lib.websocket_client import WebSocketClient
from lib.utils import setup_strategy_logger
from lib.trading_utils import (
    get_strike_token,
    get_lot_size,
    get_nearest_expiry
)

# Configure Logging
logger = setup_strategy_logger("RenkoTSLStrategy", "algo_strategy_renko_tsl.log")

# Configuration
BRICK_SIZE = 7
TREND_STREAK = 2 # Number of consecutive bricks for trend confirmation
NIFTY_SYMBOL = "NIFTY 50"
NIFTY_TOKEN = "26000"  # Check master_launcher or constants for exact token
DRY_RUN = True  # Safety First

# Premium-Based TSL Configuration
ENABLE_PREMIUM_TSL = True
PREMIUM_TSL_TRIGGER_PCT = 50  # Activate TSL after 50% profit
PREMIUM_TSL_TRAIL_PCT = 30    # Exit if premium rises 30% from best

# Time-Based Exit Configuration
AUTO_EXIT_TIME = "15:10"  # Square off before market close (HH:MM format)

# Global objects
broker = None
data_store = None

class RenkoBrick:
    def __init__(self, index, open, close, color, timestamp, low=None, high=None):
        self.index = index
        self.open = open
        self.close = close
        self.color = color # 'RED' or 'GREEN'
        self.timestamp = timestamp
        # For EMA calculation, we usually use Close
        self.high = high if high is not None else max(open, close)
        self.low = low if low is not None else min(open, close)

    def __repr__(self):
        return f"Brick({self.index}, {self.color}, {self.open}-{self.close})"

class RenkoCalculator:
    """
    Manages Renko logic state.
    Assumes standard Renko:
    - New Green: Price >= Previous Top + BrickSize
    - New Red: Price <= Previous Bottom - BrickSize
    - Reversal: Needs 2 bricks of movement from the extreme to flip direction.
    """
    def __init__(self, brick_size=15):
        self.brick_size = brick_size
        self.bricks = [] # List of RenkoBrick objects
        self.current_high = None # Top of the last brick
        self.current_low = None  # Bottom of the last brick
        self.direction = 0       # 1 (Green), -1 (Red), 0 (None)
        
    def initialize(self, start_price):
        """Align first brick to nearest box interval"""
        # Common practice: specific alignment or just start 
        # Here: align floors to brick size for clean charts
        base = round(start_price / self.brick_size) * self.brick_size
        self.current_high = base + self.brick_size
        self.current_low = base
        # We don't create a brick yet, we wait for movement out of this init zone
        # Actually simplest to just set current level to price and wait for deviation
        self.current_high = start_price
        self.current_low = start_price
        logger.info(f"  🧱 Renko Initialized @ {start_price}")

    def update(self, price, timestamp):
        if not self.bricks and self.current_high == self.current_low:
            # First initialization move
            if price >= self.current_high + self.brick_size:
                self._add_brick('GREEN', self.current_high, self.current_high + self.brick_size, timestamp)
                self.direction = 1
                return 1
            elif price <= self.current_low - self.brick_size:
                self._add_brick('RED', self.current_low, self.current_low - self.brick_size, timestamp)
                self.direction = -1
                return 1
            return 0

        new_bricks_count = 0
        
        # Loop until price is within the current range
        while True:
            added_this_loop = False
            
            # 1. Check for Extension in Same Direction
            if self.direction == 1: # Uptrend
                # Calculate potential bricks
                # Gap from High
                if price >= self.current_high + self.brick_size:
                    # Calculate how many full bricks fit in the gap
                    diff = price - self.current_high
                    num_bricks = int(diff // self.brick_size)
                    
                    for _ in range(num_bricks):
                        self._add_brick('GREEN', self.current_high, self.current_high + self.brick_size, timestamp)
                        new_bricks_count += 1
                        
                    added_this_loop = True
                    # Continue to check next interactions? No, logic is pure price level.
                    # Once extended, the new high is close to price.
            
            elif self.direction == -1: # Downtrend
                if price <= self.current_low - self.brick_size:
                    diff = self.current_low - price
                    num_bricks = int(diff // self.brick_size)
                    
                    for _ in range(num_bricks):
                        self._add_brick('RED', self.current_low, self.current_low - self.brick_size, timestamp)
                        new_bricks_count += 1
                        
                    added_this_loop = True

            # 2. Check for Reversal
            # Reversal criteria: Move 2 bricks from extreme (High for Uptrend, Low for Downtrend)
            # Actually, standard logic: Price falls below (Current Low - Brick Size) for Green->Red
            
            if not added_this_loop:
                if self.direction == 1: # Green
                     if price <= self.current_low - self.brick_size:
                        # Reversal Triggered: Handle Gap
                        diff = self.current_low - price
                        num_bricks = int(diff // self.brick_size)
                        
                        for _ in range(num_bricks):
                            self._add_brick('RED', self.current_low, self.current_low - self.brick_size, timestamp)
                            self.direction = -1 # Set immediately
                            new_bricks_count += 1
                        
                        added_this_loop = True
                        
                elif self.direction == -1: # Red
                    if price >= self.current_high + self.brick_size:
                        # Reversal Triggered: Handle Gap
                        diff = price - self.current_high
                        num_bricks = int(diff // self.brick_size)
                        
                        for _ in range(num_bricks):
                            self._add_brick('GREEN', self.current_high, self.current_high + self.brick_size, timestamp)
                            self.direction = 1
                            new_bricks_count += 1
                        
                        added_this_loop = True
            
            # If no bricks added in this iteration, we are done
            if not added_this_loop:
                break
                
        return new_bricks_count

    def _add_brick(self, color, start, end, timestamp):
        idx = len(self.bricks) + 1
        # For Green: Open=Start, Close=End
        # For Red: Open=Start, Close=End (where End < Start)
        open_p = start
        close_p = end
        
        brick = RenkoBrick(idx, open_p, close_p, color, timestamp, 
                           low=min(start, end), high=max(start, end))
        self.bricks.append(brick)
        
        # Update State
        self.current_high = brick.high
        self.current_low = brick.low
        
        arrow = "🟢" if color == 'GREEN' else "🔴"
        logger.info(f"    {arrow} New Brick: {brick}")

    def get_closes(self):
        return [b.close for b in self.bricks]




class RenkoStrategy:
    def __init__(self, broker_client, nifty_token):
        self.broker = broker_client
        self.client = broker_client.client
        self.nifty_token = nifty_token
        
        self.renko = RenkoCalculator(brick_size=BRICK_SIZE)
        self.running = False
        self.lock = threading.Lock()
        
        # Positions: {'CE': {'token':..., 'entry_price':...}, 'PE': ...}
        self.active_positions = {}
        
        self.options_map = {} # Loaded later
        self.expiry = None
        
        self.entry_state = "WAITING" # States: WAITING, IN_GREEN_TREND, IN_RED_TREND
        
        # Premium TSL State
        self.entry_premium = 0
        self.best_premium = 0
        self.tsl_active = False
        
        # Trailing Stop: Track best Nifty levels for profit locking (Renko-based)
        self.best_nifty_high = 0  # Highest Nifty reached (for Short PE)
        self.best_nifty_low = 999999  # Lowest Nifty reached (for Short CE)

    def start(self):
        self.running = True
        print(f"🚀 Renko Strategy Started. Brick Size: {BRICK_SIZE}")
        
        # 1. Initialize Options Map
        self.init_instruments()
        
        # 2. Sync Existing Positions (Restart Safety)
        self.sync_active_positions()
        
        # 3. Get Initial Price
        ticks = 0
        initial_price = 0
        print("Waiting for Nifty Tick...")
        while ticks < 5:
            lp = data_store.get_ltp(self.nifty_token)
            if lp > 0:
                initial_price = lp
                break
            time.sleep(1)
            ticks += 1
            
        if initial_price == 0:
            logger.warning("⚠️ Initial Price not found from WebSocket. Attempting to fetch Quote...")
            try:
                # Nifty 50 is usually NSE-CM, token 26000
                # Assuming nse_cm for index.
                quote_payload = [{"instrument_token": str(self.nifty_token), "exchange_segment": "nse_cm"}]
                quote_resp = self.client.quotes(instrument_tokens=quote_payload)
                logger.info(f"DEBUG Quote Response: {quote_resp}")
                
                if quote_resp and isinstance(quote_resp, list) and len(quote_resp) > 0:
                    item = quote_resp[0]
                    if 'ltp' in item and float(item['ltp']) > 0:
                        initial_price = float(item['ltp'])
                        logger.info(f"✅ Fetched Snapshot Price via API: {initial_price}")
                    elif 'ohlc' in item and 'close' in item['ohlc']:
                        initial_price = float(item['ohlc'].get('close', 0))
                        logger.info(f"✅ Fetched Previous Close via API: {initial_price}")
                
                if initial_price == 0:
                     if DRY_RUN:
                        initial_price = 23500.0
                        logger.warning("⚠️ Quote API failed/returned error. Using DUMMY PRICE (23500) for DRY RUN.")
                     else:
                        logger.error("❌ Failed to fetch valid initial price. Exiting.")
                        return

            except Exception as e:
                logger.error(f"❌ Error fetching quote: {e}")
                if DRY_RUN:
                    initial_price = 23500.0
                    logger.warning("⚠️ Exception fetching price. Using DUMMY PRICE (23500) for DRY RUN.")
                else:
                    return

        if not self.validate_nifty_range(initial_price):
            logger.error(f"❌ Initial Price {initial_price} is out of sanity range (10k-40k). Exiting.")
            return

        self.renko.initialize(initial_price)
        
        # 3. Main Loop
        threading.Thread(target=self._run_loop, daemon=True).start()




    def init_instruments(self):
        # Fetch Nifty Options Chain
        logger.info("Fetching Options Chain...")
        
        # Calculate Nifty Expiry
        # User specified Nifty Expiry is on Tuesday (e.g. 20th Jan), matching lib logic
        self.expiry = get_nearest_expiry()
        logger.info(f"Expiry: {self.expiry}")
        
        if self.broker.master_df is None:
             logger.error("❌ Master DF not loaded in Broker.")

    def _run_loop(self):
        logger.info("🔄 Strategy Loop Started")
        last_heartbeat = time.time()
        
        while self.running:
            try:
                # 1. Get Live Price
                ltp = data_store.get_ltp(self.nifty_token)
                
                # Heartbeat every 3 seconds
                if time.time() - last_heartbeat > 3:
                    # Update best Nifty levels for trailing stop
                    if self.entry_state == "IN_GREEN_TREND" and ltp > self.best_nifty_high:
                        self.best_nifty_high = ltp
                    elif self.entry_state == "IN_RED_TREND" and ltp < self.best_nifty_low:
                        self.best_nifty_low = ltp
                    
                    # Calculate ACTUAL reversal exit level (uses BEST levels for true trailing)
                    reversal_sl_info = ""
                    if self.entry_state == "IN_GREEN_TREND" and self.best_nifty_high > 0:
                        # In Green Trend (Short PE): Exit when 2 RED bricks form from BEST high
                        # Stop only tightens as market rises, NEVER loosens as market falls
                        reversal_level = self.best_nifty_high - (2 * BRICK_SIZE)
                        reversal_sl_info = f" | Exit @ 2 RED: {reversal_level:.2f} (locked @ {self.best_nifty_high:.2f})"
                    elif self.entry_state == "IN_RED_TREND" and self.best_nifty_low < 999999:
                        # In Red Trend (Short CE): Exit when 2 GREEN bricks form from BEST low
                        # Stop only tightens as market falls, NEVER loosens as market rises
                        reversal_level = self.best_nifty_low + (2 * BRICK_SIZE)
                        reversal_sl_info = f" | Exit @ 2 GREEN: {reversal_level:.2f} (locked @ {self.best_nifty_low:.2f})"
                    
                    logger.info(f"💓 Heartbeat: LTP {ltp} | Bricks: {len(self.renko.bricks)}{reversal_sl_info}")
                    last_heartbeat = time.time()

                if ltp <= 0:
                    time.sleep(1)
                    continue
                
                # Staleness detection: Check if LTP has been unchanged for too long
                if not hasattr(self, '_last_ltp'):
                    self._last_ltp = ltp
                    self._last_ltp_change_time = time.time()
                
                if ltp != self._last_ltp:
                    self._last_ltp = ltp
                    self._last_ltp_change_time = time.time()
                else:
                    staleness = time.time() - self._last_ltp_change_time
                    if staleness > 30:  # 30 seconds without change
                        if int(staleness) % 10 == 0:  # Log every 10 seconds
                            logger.warning(f"  ⚠️ STALE DATA: LTP unchanged for {int(staleness)}s. WebSocket may be disconnected!")

                # 2. Check Time-Based Exit
                current_time = datetime.now()
                if self.check_time_exit(current_time):
                    continue
                
                # 3. Check Premium-Based TSL (if in position)
                if ENABLE_PREMIUM_TSL and self.entry_state != "WAITING":
                    if self.check_premium_tsl():
                        continue
                
                # 4. Update Renko
                new_bricks = self.renko.update(ltp, current_time)
                
                if new_bricks > 0:
                    self.on_new_brick()
                
                time.sleep(1) # Check every 1s (Renko ignores time, but we sample price)
                
            except Exception as e:
                print(f"Error in Loop: {e}")
                time.sleep(5)

    def on_new_brick(self):
        """Handle Signal Logic"""
        if not self.renko.bricks:
            return

        last_brick = self.renko.bricks[-1]
        
        logger.info(f"  🏁 Brick #{last_brick.index} Closed: {last_brick.color} @ {last_brick.close}")
        
        # Determine Signal
        self.check_trend_signal()

    def check_trend_signal(self):
        """
        State Machine Logic for Trend Strategy.
        States: WAITING -> IN_GREEN_TREND / IN_RED_TREND -> WAITING
        """
        # Ensure enough data for Trend Streak
        if len(self.renko.bricks) < TREND_STREAK:
            return
        
        last_n = self.renko.bricks[-TREND_STREAK:]
        last_brick = self.renko.bricks[-1]
        
        all_green = all(b.color == 'GREEN' for b in last_n)
        all_red = all(b.color == 'RED' for b in last_n)
        
        # State: WAITING → Check for new trend
        if self.entry_state == "WAITING":
            if all_green:
                if 'PE' not in self.active_positions:
                    logger.info(f"  📈 TREND DETECTED: {TREND_STREAK} GREEN → SELL PE")
                    self.signal_sell_pe()
                    self.ensure_ce_exit()
                    self.entry_state = "IN_GREEN_TREND"
            
            elif all_red:
                if 'CE' not in self.active_positions:
                    logger.info(f"  📉 TREND DETECTED: {TREND_STREAK} RED → SELL CE")
                    self.signal_sell_ce()
                    self.ensure_pe_exit()
                    self.entry_state = "IN_RED_TREND"
        
        # State: IN_GREEN_TREND → Watch for reversal (2 consecutive RED bricks)
        elif self.entry_state == "IN_GREEN_TREND":
            if len(self.renko.bricks) >= 2:
                last_2 = self.renko.bricks[-2:]
                if all(b.color == 'RED' for b in last_2):
                    logger.info("  🛡️ REVERSAL: 2 Red bricks → Exiting PE")
                    self.ensure_pe_exit()
                    self.entry_state = "WAITING"
        
        # State: IN_RED_TREND → Watch for reversal (2 consecutive GREEN bricks)
        elif self.entry_state == "IN_RED_TREND":
            if len(self.renko.bricks) >= 2:
                last_2 = self.renko.bricks[-2:]
                if all(b.color == 'GREEN' for b in last_2):
                    logger.info("  🛡️ REVERSAL: 2 Green bricks → Exiting CE")
                    self.ensure_ce_exit()
                    self.entry_state = "WAITING"

    def signal_sell_ce(self):
        if 'CE' in self.active_positions:
            return # Already Short CE
            
        logger.info("  🔴 SIGNAL: SELL CE")
        # Strike Selection: ATM + Offset?
        # User didn't specify, assuming ATM
        atm = round(data_store.get_ltp(self.nifty_token) / 50) * 50
        strike = atm + 150 # 150 points OTM
        
        # Fix call: pass self.broker, strike, type, expiry
        token, symbol = get_strike_token(self.broker, strike, "CE", self.expiry)
        
        if token and symbol:
           qty = get_lot_size(self.broker.master_df, symbol)
           if self.place_order(token, qty, "SELL", "Renko Short CE", trading_symbol=symbol):
               # FIX: Retry logic to avoid race condition
               ce_ltp = 0
               max_retries = 3
               for attempt in range(max_retries):
                   ce_ltp = data_store.get_ltp(token)
                   if ce_ltp > 0:
                       break
                   logger.info(f"  ⏳ Waiting for CE LTP... (Attempt {attempt + 1}/{max_retries})")
                   time.sleep(1)
               
               if ce_ltp == 0:
                   logger.warning(f"  ⚠️ Could not fetch CE LTP after {max_retries} attempts. TSL may not work correctly.")
                   ce_ltp = 100  # Fallback to prevent division by zero
               
               self.active_positions['CE'] = {
                   'token': token, 'strike': strike, 'symbol': symbol, 'qty': qty,
                   'entry_premium': ce_ltp, 'entry_time': time.time()
               }
               # Reset TSL state for new position
               self.entry_premium = ce_ltp
               self.best_premium = ce_ltp
               self.tsl_active = False
               logger.info(f"  📊 Entry Premium: ₹{ce_ltp:.2f}")
               
               # Initialize Renko trailing stop: Track best LOW for Short CE
               current_nifty = data_store.get_ltp(self.nifty_token)
               self.best_nifty_low = current_nifty
               logger.info(f"  📊 Entry Nifty: {current_nifty:.2f} | Initial Renko SL: {current_nifty + (2 * BRICK_SIZE):.2f}")

    def signal_sell_pe(self):
        if 'PE' in self.active_positions:
            return # Already Short PE
            
        logger.info("  🟢 SIGNAL: SELL PE")
        atm = round(data_store.get_ltp(self.nifty_token) / 50) * 50
        strike = atm - 150 # 150 points OTM
        
        token, symbol = get_strike_token(self.broker, strike, "PE", self.expiry)
        
        if token and symbol:
           qty = get_lot_size(self.broker.master_df, symbol)
           if self.place_order(token, qty, "SELL", "Renko Short PE", trading_symbol=symbol):
               # FIX: Retry logic to avoid race condition
               pe_ltp = 0
               max_retries = 3
               for attempt in range(max_retries):
                   pe_ltp = data_store.get_ltp(token)
                   if pe_ltp > 0:
                       break
                   logger.info(f"  ⏳ Waiting for PE LTP... (Attempt {attempt + 1}/{max_retries})")
                   time.sleep(1)
               
               if pe_ltp == 0:
                   logger.warning(f"  ⚠️ Could not fetch PE LTP after {max_retries} attempts. TSL may not work correctly.")
                   pe_ltp = 100  # Fallback to prevent division by zero
               
               self.active_positions['PE'] = {
                   'token': token, 'strike': strike, 'symbol': symbol, 'qty': qty,
                   'entry_premium': pe_ltp, 'entry_time': time.time()
               }
               # Reset TSL state for new position
               self.entry_premium = pe_ltp
               self.best_premium = pe_ltp
               self.tsl_active = False
               logger.info(f"  📊 Entry Premium: ₹{pe_ltp:.2f}")
               
               # Initialize Renko trailing stop: Track best HIGH for Short PE
               current_nifty = data_store.get_ltp(self.nifty_token)
               self.best_nifty_high = current_nifty
               logger.info(f"  📊 Entry Nifty: {current_nifty:.2f} | Initial Renko SL: {current_nifty - (2 * BRICK_SIZE):.2f}")

    def ensure_ce_exit(self):
        if 'CE' in self.active_positions:
            pos = self.active_positions.pop('CE')
            qty = pos.get('qty', 50) # Fallback to 50 if missing (shouldn't happen with new logic)
            logger.info(f"  👋 Exiting CE Position (Qty: {qty})...")
            self.place_order(pos['token'], qty, "BUY", "Renko Exit CE", trading_symbol=pos.get('symbol'))
            
            # FIX: Reset TSL state after exit
            self.entry_premium = 0
            self.best_premium = 0
            self.tsl_active = False
            # Reset Renko trailing stop
            self.best_nifty_low = 999999

    def ensure_pe_exit(self):
        if 'PE' in self.active_positions:
            pos = self.active_positions.pop('PE')
            qty = pos.get('qty', 50)
            logger.info(f"  👋 Exiting PE Position (Qty: {qty})...")
            self.place_order(pos['token'], qty, "BUY", "Renko Exit PE", trading_symbol=pos.get('symbol'))
            
            # FIX: Reset TSL state after exit
            self.entry_premium = 0
            self.best_premium = 0
            self.tsl_active = False
            # Reset Renko trailing stop
            self.best_nifty_high = 0

    def place_order(self, token, qty, transaction_type, tag, trading_symbol=None):
        if DRY_RUN:
            logger.info(f"  🧪 DRY RUN: {transaction_type} {qty} of {token} ({trading_symbol}) [{tag}]")
            return True
        else:
            if not trading_symbol:
                 logger.error(f"❌ Cannot place order without trading symbol for token {token}")
                 return False

            try:
                logger.info(f"  📝 PLACING ORDER: {transaction_type} {qty} {trading_symbol}")
                order = self.client.place_order(
                    exchange_segment="nse_fo",
                    product="NRML",
                    price="0",
                    order_type="MKT",
                    quantity=str(qty),
                    validity="DAY",
                    trading_symbol=trading_symbol,
                    transaction_type="S" if transaction_type == "SELL" else "B"
                )
                logger.info(f"✅ Order placed: {order}")
                
                 # Check for API rejection
                if isinstance(order, dict) and order.get('stat') != 'Ok':
                     logger.error(f"❌ Order Rejected: {order.get('errMsg', 'Unknown Error')}")
                     return False
                     
                return True
            except Exception as e:
                logger.error(f"❌ Order failed: {e}")
                return False

    def sync_active_positions(self):
        """Restore active positions from broker to resume state on restart."""
        logger.info("🔄 Syncing active positions from Broker...")
        try:
            positions_resp = self.client.positions()
            if not positions_resp:
                return

            # Kotak Neo structure: {'data': [...], 'stat': 'Ok'}
            pos_data = positions_resp.get('data', []) if isinstance(positions_resp, dict) else positions_resp
            
            if not pos_data:
                return

            count = 0
            for pos in pos_data:
                # Filter for Open Positions (NetQty != 0)
                net_qty = int(pos.get('netQty', 0))
                if net_qty == 0:
                    continue
                
                # Check if it's NIFTY and Option
                sym = pos.get('trdSym', '')
                if 'NIFTY' in sym and ('CE' in sym or 'PE' in sym):
                    # Deduced logic:
                    # If NetQty < 0, it's a SELL (Short)
                    # If NetQty > 0, it's a BUY (Long) - Strategy typically Shorts, but maybe we treat as well
                    
                    p_type = 'CE' if 'CE' in sym else 'PE'
                    token = pos.get('tok') # Assuming token key
                     # If token key missing, might need lookup, but usually in pos report
                     
                    # Add to active_positions
                    if net_qty < 0: # We are Short
                        # Fetch current LTP for entry_premium (best effort)
                        current_ltp = data_store.get_ltp(token)
                        if current_ltp == 0:
                            # Fallback: Try to get from position data
                            current_ltp = float(pos.get('lp', 0) or 0)
                        
                        self.active_positions[p_type] = {
                            'token': token,
                            'symbol': sym,
                            'qty': abs(net_qty),
                            'strike': 0,
                            'entry_premium': current_ltp,  # FIX: Add entry_premium for TSL
                            'entry_time': time.time()
                        }
                        
                        # Initialize TSL state for restored position
                        if current_ltp > 0:
                            self.entry_premium = current_ltp
                            self.best_premium = current_ltp
                            self.tsl_active = False
                            logger.info(f"  📊 Restored Entry Premium: ₹{current_ltp:.2f}")
                        else:
                            logger.warning(f"  ⚠️ Could not fetch entry premium for {p_type}. TSL disabled for this position.")
                        
                        # Restore State (Only if this is the FIRST position found)
                        if self.entry_state == "WAITING":
                            if p_type == 'CE':
                                self.entry_state = "IN_RED_TREND"
                                logger.info(f"  ✅ Restored SHORT CE: {sym} (Qty: {abs(net_qty)}) | State: IN_RED_TREND")
                            elif p_type == 'PE':
                                self.entry_state = "IN_GREEN_TREND"
                                logger.info(f"  ✅ Restored SHORT PE: {sym} (Qty: {abs(net_qty)}) | State: IN_GREEN_TREND")
                            count += 1
                        else:
                            # Already restored a position - this is unexpected
                            logger.warning(f"  ⚠️ Found additional {p_type} position while already in state {self.entry_state}")
                            logger.warning(f"  ⚠️ Strategy should only hold ONE position type. Manual intervention may be needed.")
                            count += 1
            
            if count == 0:
                logger.info("  ℹ️ No relevant open Nifty positions found.")
                
        except Exception as e:
            logger.error(f"❌ Error syncing positions: {e}")

    def validate_nifty_range(self, price):
        """Sanity check for Nifty price."""
        if price < 10000 or price > 40000:
            return False
        return True
    
    def check_premium_tsl(self):
        """Check premium-based trailing stop loss."""
        if self.entry_state == "IN_GREEN_TREND" and 'PE' in self.active_positions:
            current_premium = data_store.get_ltp(self.active_positions['PE']['token'])
            entry_premium = self.active_positions['PE'].get('entry_premium', 0)
            
            if current_premium <= 0 or entry_premium <= 0:
                return False
            
            # Update best premium (lowest for short position)
            if current_premium < self.best_premium:
                self.best_premium = current_premium
            
            # Calculate profit percentage
            profit_pct = ((entry_premium - current_premium) / entry_premium) * 100
            
            # Activate TSL if profit threshold reached
            if profit_pct >= PREMIUM_TSL_TRIGGER_PCT:
                if not self.tsl_active:
                    logger.info(f"  🔒 Premium TSL ACTIVATED at {profit_pct:.1f}% profit (Best: ₹{self.best_premium:.2f})")
                    self.tsl_active = True
                
                # Check if premium has risen too much from best
                tsl_threshold = self.best_premium * (1 + PREMIUM_TSL_TRAIL_PCT / 100)
                if current_premium >= tsl_threshold:
                    profit_locked = ((entry_premium - current_premium) / entry_premium) * 100
                    pnl_amount = (entry_premium - current_premium) * self.active_positions['PE']['qty']
                    logger.info(f"  🛡️ PREMIUM TSL HIT: Current ₹{current_premium:.2f} >= ₹{tsl_threshold:.2f} (30% from best ₹{self.best_premium:.2f})")
                    logger.info(f"  💰 Locking profit: {profit_locked:.1f}% (₹{pnl_amount:.0f})")
                    self.ensure_pe_exit()
                    self.entry_state = "WAITING"
                    return True
        
        elif self.entry_state == "IN_RED_TREND" and 'CE' in self.active_positions:
            current_premium = data_store.get_ltp(self.active_positions['CE']['token'])
            entry_premium = self.active_positions['CE'].get('entry_premium', 0)
            
            if current_premium <= 0 or entry_premium <= 0:
                return False
            
            # Update best premium (lowest for short position)
            if current_premium < self.best_premium:
                self.best_premium = current_premium
            
            # Calculate profit percentage
            profit_pct = ((entry_premium - current_premium) / entry_premium) * 100
            
            # Activate TSL if profit threshold reached
            if profit_pct >= PREMIUM_TSL_TRIGGER_PCT:
                if not self.tsl_active:
                    logger.info(f"  🔒 Premium TSL ACTIVATED at {profit_pct:.1f}% profit (Best: ₹{self.best_premium:.2f})")
                    self.tsl_active = True
                
                # Check if premium has risen too much from best
                tsl_threshold = self.best_premium * (1 + PREMIUM_TSL_TRAIL_PCT / 100)
                if current_premium >= tsl_threshold:
                    profit_locked = ((entry_premium - current_premium) / entry_premium) * 100
                    pnl_amount = (entry_premium - current_premium) * self.active_positions['CE']['qty']
                    logger.info(f"  🛡️ PREMIUM TSL HIT: Current ₹{current_premium:.2f} >= ₹{tsl_threshold:.2f} (30% from best ₹{self.best_premium:.2f})")
                    logger.info(f"  💰 Locking profit: {profit_locked:.1f}% (₹{pnl_amount:.0f})")
                    self.ensure_ce_exit()
                    self.entry_state = "WAITING"
                    return True
        
        return False
    
    def check_time_exit(self, current_time):
        """Check if time-based exit should trigger."""
        current_time_str = current_time.strftime("%H:%M")
        
        if current_time_str >= AUTO_EXIT_TIME:
            if self.entry_state != "WAITING":
                logger.info(f"  ⏰ TIME EXIT: {current_time_str} >= {AUTO_EXIT_TIME}")
                
                # Exit all positions
                if 'CE' in self.active_positions:
                    entry_prem = self.active_positions['CE'].get('entry_premium', 0)
                    current_prem = data_store.get_ltp(self.active_positions['CE']['token'])
                    pnl = (entry_prem - current_prem) * self.active_positions['CE']['qty']
                    logger.info(f"  💰 CE P&L: ₹{pnl:.0f}")
                    self.ensure_ce_exit()
                
                if 'PE' in self.active_positions:
                    entry_prem = self.active_positions['PE'].get('entry_premium', 0)
                    current_prem = data_store.get_ltp(self.active_positions['PE']['token'])
                    pnl = (entry_prem - current_prem) * self.active_positions['PE']['qty']
                    logger.info(f"  💰 PE P&L: ₹{pnl:.0f}")
                    self.ensure_pe_exit()
                
                self.entry_state = "WAITING"
                logger.info(f"  🛑 All positions squared off. Strategy paused until next day.")
                return True
        
        return False

# Standalone execution
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    # Simple Test Harness
    broker = BrokerClient()
    try:
        if broker.authenticate():
            broker.load_master_data() # Required for token lookups
            
            # Initialize DataStore and WebSocket
            data_store = DataStore()
            ws_client = WebSocketClient(broker.client, data_store)
            
            # Attach Callbacks
            broker.client.on_message = ws_client.on_message
            broker.client.on_error = ws_client.on_error
            broker.client.on_open = ws_client.on_open
            broker.client.on_close = ws_client.on_close
            
            # Subscribe to Nifty
            ws_client.subscribe([NIFTY_TOKEN], is_index=False)
            
            strategy = RenkoStrategy(broker, NIFTY_TOKEN)
            strategy.start()
            
            try:
                while True: time.sleep(1)
            except KeyboardInterrupt:
                print("Exiting...")
    except Exception as e:
        print(f"Failed to start: {e}")

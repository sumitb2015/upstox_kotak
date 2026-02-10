"""
Algo Strategy: Renko-Based Nifty Option Selling
Status: EXPERIMENTAL

Logic:
1. Construct Renko Bricks (Size 5) from Nifty Spot (Live).
2. Signal:
   - SELL CE after 2 consecutive RED bricks (Bearish Trend)
   - SELL PE after 2 consecutive GREEN bricks (Bullish Trend)
3. Exit:
   - Option Premium Renko (Dynamic Size, e.g., 5% of entry)
   - 2 consecutive GREEN bricks on Option Premium -> EXIT
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
logger = setup_strategy_logger("RenkoOptionExitStrategy", "algo_strategy_renko_option_exit.log")

# Configuration
NIFTY_BRICK_SIZE = 5  # Brick size for NIFTY (entry signal)
OPTION_BRICK_PCT = 0.05  # 5% of premium (e.g. 100 -> 5)
MIN_OPTION_BRICK = 2.0   # Minimum brick size to avoid noise
TREND_STREAK = 2  # Number of consecutive bricks for trend confirmation
NIFTY_SYMBOL = "NIFTY 50"
NIFTY_TOKEN = "26000"  # Check master_launcher or constants for exact token
DRY_RUN = False  # Safety First
TRADING_LOTS = 3 # Number of lots to trade

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
    def __init__(self, broker_client, nifty_token, ws_client=None):
        self.broker = broker_client
        self.client = broker_client.client
        self.nifty_token = nifty_token
        self.ws_client = ws_client # For dynamic subscription
        
        # Two Renko calculators: one for entry (Nifty), one for exit (Option)
        self.nifty_renko = RenkoCalculator(brick_size=NIFTY_BRICK_SIZE)
        self.option_renko = None  # Created when position is entered
        self.running = False
        self.lock = threading.Lock()
        
        # Positions: {'CE': {'token':..., 'entry_price':...}, 'PE': ...}
        self.active_positions = {}
        
        self.options_map = {} # Loaded later
        self.expiry = None
        
        self.entry_state = "WAITING" # States: WAITING, IN_GREEN_TREND, IN_RED_TREND
        self.current_option_token = None  # Track which option we're monitoring

    def calculate_brick_size(self, price):
        """
        Calculate dynamic brick size with adaptive ranges:
        - Price < 50: Max of 2.0 or 5% (Floor behavior)
        - 50 <= Price < 200: Standard 5%
        - Price >= 200: Min of 50.0 or 5% (Cap behavior)
        """
        raw_size = price * OPTION_BRICK_PCT
        
        if price < 50:
            return max(MIN_OPTION_BRICK, round(raw_size, 1))
        elif price < 200:
            return round(raw_size, 1)
        else:
            return min(50.0, round(raw_size, 1))

    def start(self):
        self.running = True
        print(f"🚀 Renko Strategy Started. Nifty Brick Size: {NIFTY_BRICK_SIZE}")
        
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

        self.nifty_renko.initialize(initial_price)
        
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
                # 1. Get Live Nifty Price
                nifty_ltp = data_store.get_ltp(self.nifty_token)
                
                # 2. Update Nifty Renko (for entry signals)
                nifty_bricks_formed = self.nifty_renko.update(nifty_ltp, datetime.now())
                if nifty_bricks_formed > 0:
                    self.on_nifty_brick()
                
                # 3. If in position, track option premium
                if self.current_option_token and self.option_renko:
                    option_ltp = data_store.get_ltp(self.current_option_token)
                    if option_ltp > 0:
                        option_bricks_formed = self.option_renko.update(option_ltp, datetime.now())
                        if option_bricks_formed > 0:
                            self.on_option_brick()
                
                # Heartbeat every 3 seconds
                if time.time() - last_heartbeat > 3:
                    option_info = ""
                    if self.current_option_token and self.option_renko:
                        opt_ltp = data_store.get_ltp(self.current_option_token)
                        
                        # Find Symbol
                        sym = "Option"
                        for p_type in ['CE', 'PE']:
                            if p_type in self.active_positions and self.active_positions[p_type]['token'] == self.current_option_token:
                                sym = self.active_positions[p_type]['symbol']
                                break
                        
                        # Calculate TSL (Low + 3*Brick for 2-Brick Reversal)
                        tsl = self.option_renko.current_low + (3 * self.option_renko.brick_size)
                        
                        option_info = f" | {sym}: ₹{opt_ltp:.2f} (Bricks: {len(self.option_renko.bricks)}) | TSL Trigger: {tsl:.2f}"
                    
                    logger.info(f"💓 Heartbeat: Nifty {nifty_ltp:.2f} | Entry Bricks: {len(self.nifty_renko.bricks)}{option_info}")
                    last_heartbeat = time.time()

                if nifty_ltp <= 0:
                    time.sleep(1)
                    continue
                
                # Staleness detection: Check if Nifty LTP has been unchanged for too long
                if not hasattr(self, '_last_ltp'):
                    self._last_ltp = nifty_ltp
                    self._last_ltp_change_time = time.time()
                
                if nifty_ltp != self._last_ltp:
                    self._last_ltp = nifty_ltp
                    self._last_ltp_change_time = time.time()
                else:
                    staleness = time.time() - self._last_ltp_change_time
                    if staleness > 30:  # 30 seconds without change
                        if int(staleness) % 10 == 0:  # Log every 10 seconds
                            logger.warning(f"  ⚠️ STALE DATA: Nifty LTP unchanged for {int(staleness)}s. WebSocket may be disconnected!")
                
                time.sleep(1) # Check every 1s (Renko ignores time, but we sample price)
                
            except Exception as e:
                logger.error(f"❌ Error in Loop: {e}", exc_info=True)
                time.sleep(5)

    def on_nifty_brick(self):
        """Handle Nifty Signal Logic (Entry Only)"""
        if not self.nifty_renko.bricks:
            return

        last_brick = self.nifty_renko.bricks[-1]

        # Update Trailing Stop Levels based on CLOSED bricks only (Nifty TSL)
        if self.entry_state == "IN_GREEN_TREND":
            if last_brick.high > self.best_nifty_high:
                self.best_nifty_high = last_brick.high
                logger.info(f"  ⛓️  TSL Tightened: Best High updated to {self.best_nifty_high} (Brick #{last_brick.index})")
        elif self.entry_state == "IN_RED_TREND":
            if last_brick.low < self.best_nifty_low:
                self.best_nifty_low = last_brick.low
                logger.info(f"  ⛓️  TSL Tightened: Best Low updated to {self.best_nifty_low} (Brick #{last_brick.index})")
        
        logger.info(f"  🏁 Nifty Brick #{last_brick.index} Closed: {last_brick.color} @ {last_brick.close}")
        
        # Determine Signal
        self.check_trend_signal()

    def check_trend_signal(self):
        """
        State Machine Logic for Trend Strategy.
        States: WAITING -> IN_GREEN_TREND / IN_RED_TREND
        """
        # Ensure enough data for Trend Streak
        if len(self.nifty_renko.bricks) < TREND_STREAK:
            return
        
        last_n = self.nifty_renko.bricks[-TREND_STREAK:]
        
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

    def on_option_brick(self):
        """Handle Option Signal Logic (Exit Only)"""
        if not self.option_renko or not self.option_renko.bricks:
            return

        last_brick = self.option_renko.bricks[-1]
        
        # Visualize Option TSL (Moving on Box Size)
        # We are short, so we track the Low. 
        # Reversal needed: 2 Green Bricks.
        # - Brick 1 (Reversal): Triggers at High + Brick = (Low + Brick) + Brick = Low + 2*Brick
        # - Brick 2 (Confirmation): Triggers at NewHigh + Brick = Low + 3*Brick
        tsl_level = self.option_renko.current_low + (3 * self.option_renko.brick_size)
        
        if last_brick.color == 'RED':
             logger.info(f"  ⛓️  Option TSL Tightened: Exit Trigger @ {tsl_level:.2f} (Low: {self.option_renko.current_low:.2f})")
        elif last_brick.color == 'GREEN':
             logger.info(f"  ⚠️  Option TSL Threat: Price Rising. Exit Trigger @ {tsl_level:.2f}")

        logger.info(f"  🏁 Option Brick #{last_brick.index} Closed: {last_brick.color} @ {last_brick.close}")

        # Exit Logic: Reversal (2 consecutive GREEN bricks on Option Premium)
        # Green on Option Premium = Price Rising = Bad for Short
        if len(self.option_renko.bricks) >= 2:
            last_2 = self.option_renko.bricks[-2:]
            if all(b.color == 'GREEN' for b in last_2):
                logger.info("  🛡️ OPTION REVERSAL: 2 Green Bricks (Premium Rising) → EXIT")
                
                if self.entry_state == "IN_GREEN_TREND": # Short PE
                    self.ensure_pe_exit()
                    self.entry_state = "WAITING"
                elif self.entry_state == "IN_RED_TREND": # Short CE
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
           base_qty = get_lot_size(self.broker.master_df, symbol)
           qty = base_qty * TRADING_LOTS
           
           if self.place_order(token, qty, "SELL", "Renko Short CE", trading_symbol=symbol):
               self.active_positions['CE'] = {'token': token, 'strike': strike, 'symbol': symbol, 'qty': qty}
               # Subscribe to Option Token for Live Data
               if self.ws_client:
                   self.ws_client.subscribe([token], segment="nse_fo")
               
               # Initialize Option Renko
               # Need to wait briefly for first tick or fetch quote since WS might take a moment
               time.sleep(1) 
               opt_ltp = data_store.get_ltp(token)
               if opt_ltp == 0:
                   # Try fetching quote if WS data not yet available
                   try:
                       q = self.client.quotes(instrument_tokens=[{"instrument_token": str(token), "exchange_segment": "nse_fo"}])
                       if q and len(q) > 0 and 'ltp' in q[0]:
                           opt_ltp = float(q[0]['ltp'])
                   except:
                       pass
               
               if opt_ltp > 0:
                   self.current_option_token = token
                   
                   # Dynamic Brick Size Calculation
                   brick_size = self.calculate_brick_size(opt_ltp)
                   
                   self.option_renko = RenkoCalculator(brick_size=brick_size)
                   self.option_renko.initialize(opt_ltp)
                   logger.info(f"  📊 Option Tracker Initialized @ ₹{opt_ltp:.2f} (Dynamic Brick: {brick_size})")
               else:
                   logger.warning(f"  ⚠️ Could not get Option LTP for {symbol}. Exit logic delayed.")

               # Initialize trailing stop: Track best LOW for Short CE
               current_nifty = data_store.get_ltp(self.nifty_token)
               self.best_nifty_low = current_nifty
               logger.info(f"  📊 Entry Nifty: {current_nifty:.2f} | Initial SL: {current_nifty + (2 * NIFTY_BRICK_SIZE):.2f}")

    def signal_sell_pe(self):
        if 'PE' in self.active_positions:
            return # Already Short PE
            
        logger.info("  🟢 SIGNAL: SELL PE")
        atm = round(data_store.get_ltp(self.nifty_token) / 50) * 50
        strike = atm - 150 # 150 points OTM
        
        token, symbol = get_strike_token(self.broker, strike, "PE", self.expiry)
        
        if token and symbol:
           base_qty = get_lot_size(self.broker.master_df, symbol)
           qty = base_qty * TRADING_LOTS
           
           if self.place_order(token, qty, "SELL", "Renko Short PE", trading_symbol=symbol):
               self.active_positions['PE'] = {'token': token, 'strike': strike, 'symbol': symbol, 'qty': qty}
               # Subscribe to Option Token for Live Data
               if self.ws_client:
                   self.ws_client.subscribe([token], segment="nse_fo")
               
               # Initialize Option Renko
               time.sleep(1)
               opt_ltp = data_store.get_ltp(token)
               if opt_ltp == 0:
                   try:
                       q = self.client.quotes(instrument_tokens=[{"instrument_token": str(token), "exchange_segment": "nse_fo"}])
                       if q and len(q) > 0 and 'ltp' in q[0]:
                           opt_ltp = float(q[0]['ltp'])
                   except:
                       pass
               
               if opt_ltp > 0:
                   self.current_option_token = token
                   
                   # Dynamic Brick Size Calculation
                   brick_size = self.calculate_brick_size(opt_ltp)
                   
                   self.option_renko = RenkoCalculator(brick_size=brick_size)
                   self.option_renko.initialize(opt_ltp)
                   logger.info(f"  📊 Option Tracker Initialized @ ₹{opt_ltp:.2f} (Dynamic Brick: {brick_size})")
               else:
                   logger.warning(f"  ⚠️ Could not get Option LTP for {symbol}. Exit logic delayed.")

               # Initialize trailing stop: Track best HIGH for Short PE
               current_nifty = data_store.get_ltp(self.nifty_token)
               self.best_nifty_high = current_nifty
               logger.info(f"  📊 Entry Nifty: {current_nifty:.2f} | Initial SL: {current_nifty - (2 * NIFTY_BRICK_SIZE):.2f}")

    def ensure_ce_exit(self):
        if 'CE' in self.active_positions:
            pos = self.active_positions.pop('CE')
            qty = pos.get('qty', 50) # Fallback to 50 if missing (shouldn't happen with new logic)
            logger.info(f"  👋 Exiting CE Position (Qty: {qty})...")
            self.place_order(pos['token'], qty, "BUY", "Renko Exit CE", trading_symbol=pos.get('symbol'))
            
            # Unsubscribe and Clear State
            if self.ws_client and 'token' in pos:
                self.ws_client.unsubscribe([pos['token']])
            
            self.current_option_token = None
            self.option_renko = None
            
            # Reset trailing stop
            self.best_nifty_low = 999999

    def ensure_pe_exit(self):
        if 'PE' in self.active_positions:
            pos = self.active_positions.pop('PE')
            qty = pos.get('qty', 50)
            logger.info(f"  👋 Exiting PE Position (Qty: {qty})...")
            self.place_order(pos['token'], qty, "BUY", "Renko Exit PE", trading_symbol=pos.get('symbol'))
            
            # Unsubscribe and Clear State
            if self.ws_client and 'token' in pos:
                self.ws_client.unsubscribe([pos['token']])
            
            self.current_option_token = None
            self.option_renko = None
            
            # Reset trailing stop
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
                        self.active_positions[p_type] = {
                            'token': token,
                            'symbol': sym,
                            'qty': abs(net_qty),
                            'strike': 0
                        }
                        
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
                        
                        # Use first found option for active tracking
                        if self.current_option_token is None:
                            self.current_option_token = token
                            # Subscribe
                            if self.ws_client:
                                self.ws_client.subscribe([token], segment="nse_fo")
                                logger.info(f"  📡 Resubscribed to Option {sym}")
                            
                            # Initialize Renko (best effort with current price)
                            # Actual price history lost, so starting fresh Renko from current price
                            # This is a limitation of restart, but unavoidable without persistence
                            time.sleep(1)
                            opt_ltp = data_store.get_ltp(token)
                            if opt_ltp > 0:
                                # Dynamic Brick Size Calculation
                                brick_size = self.calculate_brick_size(opt_ltp)
                                
                                self.option_renko = RenkoCalculator(brick_size=brick_size)
                                self.option_renko.initialize(opt_ltp)
                                logger.info(f"  📊 Restored Option Tracker @ ₹{opt_ltp:.2f} (Dynamic Brick: {brick_size})")
                            else:
                                logger.warning(f"  ⚠️ Could not get Option LTP for restored position {sym}")
            
            if count == 0:
                logger.info("  ℹ️ No relevant open Nifty positions found.")
                
        except Exception as e:
            logger.error(f"❌ Error syncing positions: {e}")

    def validate_nifty_range(self, price):
        """Sanity check for Nifty price."""
        if price < 10000 or price > 40000:
            return False
        return True

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
            
            # Pass ws_client to strategy
            strategy = RenkoStrategy(broker, NIFTY_TOKEN, ws_client=ws_client)
            strategy.start()
            
            try:
                while True: time.sleep(1)
            except KeyboardInterrupt:
                print("Exiting...")
    except Exception as e:
        print(f"Failed to start: {e}")

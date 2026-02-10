"""
Algo Strategy: Dual-Renko (Mega Trend) Nifty Option Selling
Status: EXPERIMENTAL

Logic:
1. Construct Mega Renko Bricks (Size 15) for MACRO TREND direction.
2. Construct Signal Renko Bricks (Size 5) for ENTRY signals.
3. Entry Conditions:
   - SELL PE (Short Put): Signal Renko triggers GREEN Trend AND Mega Renko is GREEN.
   - SELL CE (Short Call): Signal Renko triggers RED Trend AND Mega Renko is RED.
4. Exit:
   - Option Premium Renko (Dynamic Size, e.g., 5% of entry)
   - 2 consecutive GREEN bricks on Option Premium (Price Rising) -> EXIT
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
logger = setup_strategy_logger("DualRenkoStrategy", "algo_strategy_dual_renko.log")

# Configuration
NIFTY_BRICK_SIZE = 5      # Signal Brick
MEGA_BRICK_SIZE = 15      # Trend Filter Brick
OPTION_BRICK_PCT = 0.05   # 5% of premium
MIN_OPTION_BRICK = 2.0    # Floor for option brick
TREND_STREAK = 2          # Signal confirmation streak
NIFTY_SYMBOL = "NIFTY 50"
NIFTY_TOKEN = "26000"
DRY_RUN = False
TRADING_LOTS = 1

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
        self.high = high if high is not None else max(open, close)
        self.low = low if low is not None else min(open, close)

    def __repr__(self):
        return f"Brick({self.index}, {self.color}, {self.open}-{self.close})"

class RenkoCalculator:
    def __init__(self, brick_size=15):
        self.brick_size = brick_size
        self.bricks = [] 
        self.current_high = None 
        self.current_low = None  
        self.direction = 0       

    def initialize(self, start_price):
        self.current_high = start_price
        self.current_low = start_price
        logger.info(f"  🧱 Renko Initialized @ {start_price} (Brick: {self.brick_size})")

    def update(self, price, timestamp):
        if not self.bricks and self.current_high == self.current_low:
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
        while True:
            added_this_loop = False
            if self.direction == 1: # Uptrend
                if price >= self.current_high + self.brick_size:
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

            # Reversal (Requires 2 box equivalent drop from extreme)
            if not added_this_loop:
                if self.direction == 1: 
                     if price <= self.current_low - self.brick_size:
                        diff = self.current_low - price
                        num_bricks = int(diff // self.brick_size)
                        for _ in range(num_bricks):
                            self._add_brick('RED', self.current_low, self.current_low - self.brick_size, timestamp)
                            self.direction = -1 
                            new_bricks_count += 1
                        added_this_loop = True
                        
                elif self.direction == -1: 
                    if price >= self.current_high + self.brick_size:
                        diff = price - self.current_high
                        num_bricks = int(diff // self.brick_size)
                        for _ in range(num_bricks):
                            self._add_brick('GREEN', self.current_high, self.current_high + self.brick_size, timestamp)
                            self.direction = 1
                            new_bricks_count += 1
                        added_this_loop = True
            
            if not added_this_loop:
                break
                
        return new_bricks_count

    def _add_brick(self, color, start, end, timestamp):
        idx = len(self.bricks) + 1
        brick = RenkoBrick(idx, start, end, color, timestamp, low=min(start, end), high=max(start, end))
        self.bricks.append(brick)
        self.current_high = brick.high
        self.current_low = brick.low
        # Logging handled by Strategy to differentiate Mega vs Signal

class RenkoStrategy:
    def __init__(self, broker_client, nifty_token, ws_client=None):
        self.broker = broker_client
        self.client = broker_client.client
        self.nifty_token = nifty_token
        self.ws_client = ws_client 
        
        # Dual Renko Setup
        self.nifty_renko = RenkoCalculator(brick_size=NIFTY_BRICK_SIZE)
        self.mega_renko = RenkoCalculator(brick_size=MEGA_BRICK_SIZE)
        
        self.option_renko = None 
        self.running = False
        self.active_positions = {}
        self.expiry = None
        self.entry_state = "WAITING" 
        self.current_option_token = None 
        self.best_option_low = 999999 # Anchored TSL for Option 

    def calculate_brick_size(self, price):
        raw_size = price * OPTION_BRICK_PCT
        if price < 50:
            return max(MIN_OPTION_BRICK, round(raw_size, 1))
        elif price < 200:
            return round(raw_size, 1)
        else:
            return min(50.0, round(raw_size, 1))

    def start(self):
        self.running = True
        print(f"🚀 Dual-Renko Strategy Started. Signal: {NIFTY_BRICK_SIZE}, Mega: {MEGA_BRICK_SIZE}")
        
        self.init_instruments()
        self.sync_active_positions()
        
        # Get Initial Price
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
            # Fallback Logic omitted for brevity, using same logic as previous file if needed
            # Assuming WS works or restarts
             if DRY_RUN: initial_price = 23500.0
             else: 
                 logger.error("❌ Failed to fetch initial price")
                 return

        if not self.validate_nifty_range(initial_price):
            return

        self.nifty_renko.initialize(initial_price)
        self.mega_renko.initialize(initial_price)
        
        threading.Thread(target=self._run_loop, daemon=True).start()

    def init_instruments(self):
        logger.info("Fetching Options Chain...")
        self.expiry = get_nearest_expiry()
        logger.info(f"Expiry: {self.expiry}")
        if self.broker.master_df is None:
             logger.error("❌ Master DF not loaded.")

    def _run_loop(self):
        logger.info("🔄 Strategy Loop Started")
        last_heartbeat = time.time()
        consecutive_failures = 0
        
        while self.running:
            try:
                nifty_ltp = data_store.get_ltp(self.nifty_token)
                
                # CRITICAL: Validate LTP BEFORE updating Renko calculators
                if nifty_ltp <= 0:
                    consecutive_failures += 1
                    if consecutive_failures % 5 == 0:  # Log every 5 failures
                        logger.warning(f"⚠️ No Nifty LTP data available (attempt {consecutive_failures})")
                    time.sleep(1)
                    continue
                
                # Reset failure counter on successful data fetch
                consecutive_failures = 0
                
                # 1. Update Mega Renko (First)
                mega_bricks = self.mega_renko.update(nifty_ltp, datetime.now())
                if mega_bricks > 0:
                    self.on_mega_brick()
                
                # 2. Update Signal Renko
                nifty_bricks = self.nifty_renko.update(nifty_ltp, datetime.now())
                if nifty_bricks > 0:
                    self.on_signal_brick()
                
                # 3. Update Option Renko
                if self.current_option_token and self.option_renko:
                    option_ltp = data_store.get_ltp(self.current_option_token)
                    if option_ltp > 0:
                        obricks = self.option_renko.update(option_ltp, datetime.now())
                        if obricks > 0:
                            self.on_option_brick()
                        
                        # 4. TSL Breach Check (Tick-by-Tick Safety Net)
                        # This ensures exit even if 2-brick pattern doesn't form
                        if self.entry_state in ["IN_GREEN_TREND", "IN_RED_TREND"]:
                            tsl_trigger = self.best_option_low + (3 * self.option_renko.brick_size)
                            if option_ltp >= tsl_trigger:
                                logger.warning(f"  🚨 SECONDARY EXIT: TSL Breach! Price: ₹{option_ltp:.2f} >= TSL: ₹{tsl_trigger:.2f}")
                                if self.entry_state == "IN_GREEN_TREND":
                                    self.ensure_pe_exit()
                                    self.entry_state = "WAITING"
                                elif self.entry_state == "IN_RED_TREND":
                                    self.ensure_ce_exit()
                                    self.entry_state = "WAITING"
                
                # Heartbeat
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
                        
                        # Calculate Exit Triggers
                        # Primary Exit: 2-Brick Reversal (current high + 2 bricks)
                        primary_exit = self.option_renko.current_high + (2 * self.option_renko.brick_size)
                        # Secondary Exit: TSL (best low + 3 bricks)
                        secondary_exit = self.best_option_low + (3 * self.option_renko.brick_size)
                        
                        option_info = f" | {sym}: ₹{opt_ltp:.2f} (Bricks: {len(self.option_renko.bricks)}) | 1° Exit: {primary_exit:.2f} | 2° TSL: {secondary_exit:.2f}"
                    
                    # Add Mega Trend Info
                    mega_Arrow = "🟢 GREEN" if self.mega_renko.direction == 1 else "🔴 RED" if self.mega_renko.direction == -1 else "⚪ NEUTRAL"
                    
                    # Signal Info
                    signal_bricks = len(self.nifty_renko.bricks)
                    if signal_bricks > 0:
                        last_sig = self.nifty_renko.bricks[-1]
                        sig_arrow = "🟢" if last_sig.color == 'GREEN' else "🔴"
                        signal_str = f"{sig_arrow} {last_sig.color} ({signal_bricks})"
                    else:
                        signal_str = "⚪ WAITING"

                    logger.info(f"💓 Heartbeat: Nifty {nifty_ltp:.2f} | Mega: {mega_Arrow} | Signal: {signal_str}{option_info}")
                    last_heartbeat = time.time()
                
                time.sleep(1) 
                
            except Exception as e:
                logger.error(f"❌ Error in Loop: {e}", exc_info=True)
                time.sleep(5)

    def on_mega_brick(self):
        last_brick = self.mega_renko.bricks[-1]
        logger.info(f"  🌌 MEGA TREND Brick #{last_brick.index}: {last_brick.color} @ {last_brick.close}")
        # Note: Mega Trend change doesn't auto-exit positions. We stick to Option Exit logic.

    def on_signal_brick(self):
        last_brick = self.nifty_renko.bricks[-1]
        logger.info(f"  ⚡ SIGNAL Brick #{last_brick.index}: {last_brick.color} @ {last_brick.close}")
        self.check_trend_signal()

    def check_trend_signal(self):
        if len(self.nifty_renko.bricks) < TREND_STREAK:
            return
        
        last_n = self.nifty_renko.bricks[-TREND_STREAK:]
        all_green = all(b.color == 'GREEN' for b in last_n)
        all_red = all(b.color == 'RED' for b in last_n)
        
        # State: WAITING → Check for new trend
        if self.entry_state == "WAITING":
            if all_green:
                # FILTER: Mega Trend must be GREEN (1) or Neutral (0)? Safer to require Green.
                if self.mega_renko.direction == 1:
                    if 'PE' not in self.active_positions:
                        logger.info(f"  📈 TREND CONFIRMED: Signal GREEN + Mega GREEN → SELL PE")
                        self.signal_sell_pe()
                        self.ensure_ce_exit()
                        self.entry_state = "IN_GREEN_TREND"
                else:
                    logger.info(f"  ✋ Signal GREEN but Mega is RED/Neutral. Trade Skipped.")
            
            elif all_red:
                # FILTER: Mega Trend must be RED (-1)
                if self.mega_renko.direction == -1:
                    if 'CE' not in self.active_positions:
                        logger.info(f"  📉 TREND CONFIRMED: Signal RED + Mega RED → SELL CE")
                        self.signal_sell_ce()
                        self.ensure_pe_exit()
                        self.entry_state = "IN_RED_TREND"
                else:
                    logger.info(f"  ✋ Signal RED but Mega is GREEN/Neutral. Trade Skipped.")

    def on_option_brick(self):
        # Same Logic as Hybrid: Exit on 2 Green Bricks
        if not self.option_renko or not self.option_renko.bricks:
            return

        last_brick = self.option_renko.bricks[-1]
        
        # Update Best Low for Anchored TSL
        if last_brick.color == 'RED':
             if last_brick.low < self.best_option_low:
                 self.best_option_low = last_brick.low

        # TSL is now anchored to BEST LOW, not current low
        tsl_level = self.best_option_low + (3 * self.option_renko.brick_size)
        
        if last_brick.color == 'RED':
             logger.info(f"  ⛓️  Option TSL Tightened: Exit Trigger @ {tsl_level:.2f} (Low: {self.best_option_low:.2f})")
        elif last_brick.color == 'GREEN':
             logger.info(f"  ⚠️  Option TSL Threat: Price Rising. Exit Trigger @ {tsl_level:.2f}")

        logger.info(f"  🏁 Option Brick #{last_brick.index} Closed: {last_brick.color} @ {last_brick.close}")

        if len(self.option_renko.bricks) >= 2:
            last_2 = self.option_renko.bricks[-2:]
            if all(b.color == 'GREEN' for b in last_2):
                logger.info("  🛡️ OPTION REVERSAL: 2 Green Bricks (Premium Rising) → EXIT")
                if self.entry_state == "IN_GREEN_TREND": 
                    self.ensure_pe_exit()
                    self.entry_state = "WAITING"
                elif self.entry_state == "IN_RED_TREND": 
                    self.ensure_ce_exit()
                    self.entry_state = "WAITING"

    def signal_sell_ce(self):
        if 'CE' in self.active_positions: return
        logger.info("  🔴 SIGNAL: SELL CE")
        atm = round(data_store.get_ltp(self.nifty_token) / 50) * 50
        strike = atm + 150 
        token, symbol = get_strike_token(self.broker, strike, "CE", self.expiry)
        
        if token and symbol:
           base_qty = get_lot_size(self.broker.master_df, symbol)
           qty = base_qty * TRADING_LOTS
           
           if self.place_order(token, qty, "SELL", "Renko Short CE", trading_symbol=symbol):
               self.active_positions['CE'] = {'token': token, 'strike': strike, 'symbol': symbol, 'qty': qty}
               if self.ws_client: self.ws_client.subscribe([token], segment="nse_fo")
               time.sleep(1) 
               opt_ltp = data_store.get_ltp(token)
               # Quote fallback omitted for brevity
               if opt_ltp > 0:
                   self.current_option_token = token
                   brick_size = self.calculate_brick_size(opt_ltp)
                   self.option_renko = RenkoCalculator(brick_size=brick_size)
                   self.option_renko.initialize(opt_ltp)
                   self.best_option_low = opt_ltp
                   logger.info(f"  📊 Option Tracker Initialized @ ₹{opt_ltp:.2f} (Dynamic Brick: {brick_size})")

    def signal_sell_pe(self):
        if 'PE' in self.active_positions: return
        logger.info("  🟢 SIGNAL: SELL PE")
        atm = round(data_store.get_ltp(self.nifty_token) / 50) * 50
        strike = atm - 150 
        token, symbol = get_strike_token(self.broker, strike, "PE", self.expiry)
        if token and symbol:
           base_qty = get_lot_size(self.broker.master_df, symbol)
           qty = base_qty * TRADING_LOTS
           if self.place_order(token, qty, "SELL", "Renko Short PE", trading_symbol=symbol):
               self.active_positions['PE'] = {'token': token, 'strike': strike, 'symbol': symbol, 'qty': qty}
               if self.ws_client: self.ws_client.subscribe([token], segment="nse_fo")
               time.sleep(1)
               opt_ltp = data_store.get_ltp(token)
               if opt_ltp > 0:
                   self.current_option_token = token
                   brick_size = self.calculate_brick_size(opt_ltp)
                   self.option_renko = RenkoCalculator(brick_size=brick_size)
                   self.option_renko.initialize(opt_ltp)
                   self.best_option_low = opt_ltp
                   logger.info(f"  📊 Option Tracker Initialized @ ₹{opt_ltp:.2f} (Dynamic Brick: {brick_size})")

    def ensure_ce_exit(self):
        if 'CE' in self.active_positions:
            pos = self.active_positions.pop('CE')
            qty = pos.get('qty', 50)
            logger.info(f"  👋 Exiting CE Position (Qty: {qty})...")
            self.place_order(pos['token'], qty, "BUY", "Renko Exit CE", trading_symbol=pos.get('symbol'))
            if self.ws_client and 'token' in pos: self.ws_client.unsubscribe([pos['token']])
            self.current_option_token = None
            self.option_renko = None
            self.best_option_low = 999999

    def ensure_pe_exit(self):
        if 'PE' in self.active_positions:
            pos = self.active_positions.pop('PE')
            qty = pos.get('qty', 50)
            logger.info(f"  👋 Exiting PE Position (Qty: {qty})...")
            self.place_order(pos['token'], qty, "BUY", "Renko Exit PE", trading_symbol=pos.get('symbol'))
            if self.ws_client and 'token' in pos: self.ws_client.unsubscribe([pos['token']])
            self.current_option_token = None
            self.option_renko = None
            self.best_option_low = 999999

    def place_order(self, token, qty, transaction_type, tag, trading_symbol=None):
        if DRY_RUN:
            logger.info(f"  🧪 DRY RUN: {transaction_type} {qty} of {token} ({trading_symbol}) [{tag}]")
            return True
        else:
            if not trading_symbol: return False
            try:
                logger.info(f"  📝 PLACING ORDER: {transaction_type} {qty} {trading_symbol}")
                order = self.client.place_order(exchange_segment="nse_fo", product="NRML", price="0", order_type="MKT", quantity=str(qty), validity="DAY", trading_symbol=trading_symbol, transaction_type="S" if transaction_type == "SELL" else "B")
                logger.info(f"✅ Order placed: {order}")
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

            pos_data = positions_resp.get('data', []) if isinstance(positions_resp, dict) else positions_resp
            
            if not pos_data:
                return

            count = 0
            for pos in pos_data:
                net_qty = int(pos.get('netQty', 0))
                if net_qty == 0:
                    continue
                
                sym = pos.get('trdSym', '')
                if 'NIFTY' in sym and ('CE' in sym or 'PE' in sym):
                    p_type = 'CE' if 'CE' in sym else 'PE'
                    token = pos.get('tok')
                    
                    if net_qty < 0: # We are Short
                        self.active_positions[p_type] = {
                            'token': token,
                            'symbol': sym,
                            'qty': abs(net_qty),
                            'strike': 0
                        }
                        
                        if self.entry_state == "WAITING":
                            if p_type == 'CE':
                                self.entry_state = "IN_RED_TREND"
                                logger.info(f"  ✅ Restored SHORT CE: {sym} (Qty: {abs(net_qty)}) | State: IN_RED_TREND")
                            elif p_type == 'PE':
                                self.entry_state = "IN_GREEN_TREND"
                                logger.info(f"  ✅ Restored SHORT PE: {sym} (Qty: {abs(net_qty)}) | State: IN_GREEN_TREND")
                            count += 1
                        
                        if self.current_option_token is None:
                            self.current_option_token = token
                            if self.ws_client:
                                self.ws_client.subscribe([token], segment="nse_fo")
                                logger.info(f"  📡 Resubscribed to Option {sym}")
                            
                            time.sleep(1)
                            opt_ltp = data_store.get_ltp(token)
                            if opt_ltp > 0:
                                brick_size = self.calculate_brick_size(opt_ltp)
                                self.option_renko = RenkoCalculator(brick_size=brick_size)
                                self.option_renko.initialize(opt_ltp)
                                self.best_option_low = opt_ltp
                                logger.info(f"  📊 Restored Option Tracker @ ₹{opt_ltp:.2f} (Dynamic Brick: {brick_size})")
            
            if count == 0:
                logger.info("  ℹ️ No relevant open Nifty positions found.")
                
        except Exception as e:
            logger.error(f"❌ Error syncing positions: {e}")

    def validate_nifty_range(self, price):
        if price < 10000 or price > 40000: return False
        return True

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    broker = BrokerClient()
    try:
        if broker.authenticate():
            broker.load_master_data()
            data_store = DataStore()
            ws_client = WebSocketClient(broker.client, data_store)
            broker.client.on_message = ws_client.on_message
            broker.client.on_error = ws_client.on_error
            broker.client.on_open = ws_client.on_open
            broker.client.on_close = ws_client.on_close
            ws_client.subscribe([NIFTY_TOKEN], is_index=False)
            strategy = RenkoStrategy(broker, NIFTY_TOKEN, ws_client=ws_client)
            strategy.start()
            try:
                while True: time.sleep(1)
            except KeyboardInterrupt:
                print("Exiting...")
    except Exception as e:
        print(f"Failed to start: {e}")

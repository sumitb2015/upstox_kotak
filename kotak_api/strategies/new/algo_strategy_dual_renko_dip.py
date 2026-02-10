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
import json
import threading
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import pandas_ta as ta
import yfinance as yf

# Force UTF-8 encoding for Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Add lib to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

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
logger = setup_strategy_logger("DualRenkoStrategy")

# Configuration
NIFTY_BRICK_SIZE = 5      # Signal Brick
MEGA_BRICK_SIZE = 30      # Trend Filter Brick (Increased for better intraday stability)
OPTION_BRICK_PCT = 0.075  # 7.5% of premium (Increased from 5% for better stability)
MIN_OPTION_BRICK = 2.0    # Floor for option brick
TREND_STREAK = 3          # Signal confirmation streak (Increased to 3 for noise reduction)
MEGA_MIN_BRICKS = 1       # Min bricks for Mega Trend confirmation
NIFTY_SYMBOL = "NIFTY 50"
NIFTY_TOKEN = "26000"
DRY_RUN = False
TRADING_LOTS = 1
MAX_PYRAMID_LOTS = 3      # Total lots allowed (1 original + 2 additions)

# RSI Momentum Filter
RSI_PERIOD = 14
RSI_PIVOT = 50            # Bullish: >50, Bearish: <50
RSI_OVERBOUGHT = 80       # Exit/Avoid Longs if RSI > 80
RSI_OVERSOLD = 20         # Exit/Avoid Shorts if RSI < 20

# Global objects
broker = None
data_store = None

class RenkoBrick:
    def __init__(self, index, open, close, color, timestamp, low=None, high=None):
        self.index = index
        self.open = open
        self.close = close
        self.color = color 
        self.timestamp = timestamp
        self.high = high if high is not None else max(open, close)
        self.low = low if low is not None else min(open, close)

    def to_dict(self):
        return {
            'index': self.index,
            'open': self.open,
            'close': self.close,
            'color': self.color,
            'timestamp': self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else self.timestamp,
            'high': self.high,
            'low': self.low
        }

    @classmethod
    def from_dict(cls, d):
        ts = d['timestamp']
        if isinstance(ts, str):
            try: ts = datetime.fromisoformat(ts)
            except: pass
        return cls(d['index'], d['open'], d['close'], d['color'], ts, low=d['low'], high=d['high'])

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

    def to_dict(self):
        return {
            'brick_size': self.brick_size,
            'bricks': [b.to_dict() for b in self.bricks],
            'current_high': self.current_high,
            'current_low': self.current_low,
            'direction': self.direction
        }

    def from_dict(self, d):
        self.brick_size = d.get('brick_size', self.brick_size)
        self.bricks = [RenkoBrick.from_dict(b) for b in d.get('bricks', [])]
        self.current_high = d.get('current_high')
        self.current_low = d.get('current_low')
        self.direction = d.get('direction', 0)
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
        self.rsi = 50                 # Neutral start
        self.last_indicator_update = 0
        self.pyramid_count = 0        # Track added lots
        self.pullback_active = False # Track if a pullback is detected for pyramiding
        self.state_file = "dual_renko_state.json"

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
        
        # 1. Load persisted state
        state_restored = self.load_state()
        
        # 2. Sync active positions
        self.sync_active_positions()
        
        if state_restored:
            logger.info("✅ Resuming from persisted state. Skipping initialization.")
        else:
            # 3. Initial Price Discovery
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
                # Snapshot fallback
                try:
                    quote_payload = [{"instrument_token": str(self.nifty_token), "exchange_segment": "nse_cm"}]
                    quote_resp = self.client.quotes(instrument_tokens=quote_payload)
                    if quote_resp and isinstance(quote_resp, list) and len(quote_resp) > 0:
                        item = quote_resp[0]
                        if 'ltp' in item and float(item['ltp']) > 0:
                            initial_price = float(item['ltp'])
                            logger.info(f"✅ Snapshot Price: {initial_price}")
                except: pass

                if initial_price == 0:
                    if DRY_RUN: initial_price = 23500.0
                    else: 
                        logger.error("❌ Failed to fetch initial price")
                        return

            if not self.validate_nifty_range(initial_price):
                return

            self.nifty_renko.initialize(initial_price)
            self.mega_renko.initialize(initial_price)
        
            self.nifty_renko.initialize(initial_price)
            self.mega_renko.initialize(initial_price)
        
        # 4. Validating: Check for Ghost States
        if self.entry_state in ["IN_GREEN_TREND", "IN_RED_TREND"]:
            has_local_pos = len(self.active_positions) > 0
            if not has_local_pos:
                logger.warning(f"⚠️ State Mismatch: State is {self.entry_state} but no positions found in Broker.")
                logger.warning("  ➡️ Resetting State to WAITING (Assuming manual exit).")
                self.entry_state = "WAITING"
                self.active_positions = {}
                self.current_option_token = None
                self.save_state()
        
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
                # 0. Update RSI periodically (Every 1 minute)
                if time.time() - self.last_indicator_update > 60:
                    self.update_indicators()
                    self.last_indicator_update = time.time()

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
                    self.save_state()
                
                # 2. Update Signal Renko
                nifty_bricks = self.nifty_renko.update(nifty_ltp, datetime.now())
                if nifty_bricks > 0:
                    self.on_signal_brick()
                    self.save_state()
                
                # 3. Update Option Renko
                if self.current_option_token and self.option_renko:
                    option_ltp = data_store.get_ltp(self.current_option_token)
                    if option_ltp > 0:
                        obricks = self.option_renko.update(option_ltp, datetime.now())
                        if obricks > 0:
                            self.on_option_brick()
                            self.save_state()
                        
                
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
                        
                        # Primary Exit: 3-Brick Reversal (current high + 3 bricks)
                        primary_exit = self.option_renko.current_high + (3 * self.option_renko.brick_size)
                        
                        option_info = f" | {sym}: ₹{opt_ltp:.2f} (Bricks: {len(self.option_renko.bricks)}) | Exit Trigger: {primary_exit:.2f}"
                    
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

                    logger.info(f"💓 Heartbeat: Nifty {nifty_ltp:.2f} | Mega: {mega_Arrow} | Signal: {signal_str} | RSI: {self.rsi:.1f}{option_info}")
                    last_heartbeat = time.time()
                
                time.sleep(1) 
                
            except Exception as e:
                logger.error(f"❌ Error in Loop: {e}", exc_info=True)
                time.sleep(5)

    def update_indicators(self):
        """Fetch latest RSI from yfinance."""
        try:
            df = yf.download("^NSEI", period="1d", interval="1m", progress=False)
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                rsi_series = ta.rsi(df['Close'], length=RSI_PERIOD)
                if rsi_series is not None and not rsi_series.empty:
                    self.rsi = float(rsi_series.iloc[-1])
        except Exception as e:
            logger.error(f"  ⚠️ RSI Update Failed: {e}")

    def on_mega_brick(self):
        last_brick = self.mega_renko.bricks[-1]
        logger.info(f"  🌌 MEGA TREND Brick #{last_brick.index}: {last_brick.color} @ {last_brick.close}")
        
        # Structural Reversal Exit: If Macro trend flips, kill the trade regardless of option bricks
        if self.entry_state == "IN_GREEN_TREND" and self.mega_renko.direction == -1:
            logger.warning("  🚨 MEGA REVERSAL: Macro Trend turned RED (Downtrend) → EMERGENCY EXIT")
            self.ensure_pe_exit()
            self.entry_state = "WAITING"
        elif self.entry_state == "IN_RED_TREND" and self.mega_renko.direction == 1:
            logger.warning("  🚨 MEGA REVERSAL: Macro Trend turned GREEN (Uptrend) → EMERGENCY EXIT")
            self.ensure_ce_exit()
            self.entry_state = "WAITING"

    def on_signal_brick(self):
        last_brick = self.nifty_renko.bricks[-1]
        logger.info(f"  ⚡ SIGNAL Brick #{last_brick.index}: {last_brick.color} @ {last_brick.close}")
        self.check_trend_signal()

    def check_trend_signal(self):
        # Guard: Stale Indicators
        if time.time() - self.last_indicator_update > 300: # 5 mins
             logger.warning("  ⚠️ RSI Data Stale (>5m). Skipping Entry.")
             return

        if len(self.nifty_renko.bricks) < TREND_STREAK:
            return
        
        last_n = self.nifty_renko.bricks[-TREND_STREAK:]
        all_green = all(b.color == 'GREEN' for b in last_n)
        all_red = all(b.color == 'RED' for b in last_n)
        
        # State: WAITING → Check for new trend
        if self.entry_state == "WAITING":
            self.pyramid_count = 0
            self.pullback_active = False

            # Check Mega Trend Persistence (Strength check)
            mega_count = 0
            # Walk back from the end of mega bricks list to count current direction streak
            if self.mega_renko.bricks:
                curr_dir = self.mega_renko.direction
                for b in reversed(self.mega_renko.bricks):
                    if (b.color == 'GREEN' and curr_dir == 1) or (b.color == 'RED' and curr_dir == -1):
                        mega_count += 1
                    else: break

            if all_green:
                # BULLISH ENTRY: Mega Green + Persistent (>=2) + RSI > 50 + RSI not overbought
                if self.mega_renko.direction == 1 and mega_count >= MEGA_MIN_BRICKS:
                    if RSI_PIVOT < self.rsi < RSI_OVERBOUGHT:
                        if 'PE' not in self.active_positions:
                            logger.info(f"  🚀 BULLISH ENTRY: Sig Streak {TREND_STREAK} + Mega Streak {mega_count} + RSI {self.rsi:.1f} → SELL PE")
                            self.signal_sell_pe()
                            self.ensure_ce_exit()
                            self.entry_state = "IN_GREEN_TREND"
                    else:
                        logger.info(f"  ✋ Bullish Signal but RSI {self.rsi:.1f} is not in {RSI_PIVOT}-{RSI_OVERBOUGHT} zone.")
                else:
                    logger.info(f"  ✋ Signal Green but Mega Trend ({mega_count} bricks) weak or opposing.")
            
            elif all_red:
                # BEARISH ENTRY: Mega Red + Persistent (>=2) + RSI < 50 + RSI not oversold
                if self.mega_renko.direction == -1 and mega_count >= MEGA_MIN_BRICKS:
                    if RSI_OVERSOLD < self.rsi < RSI_PIVOT:
                        if 'CE' not in self.active_positions:
                            logger.info(f"  🚀 BEARISH ENTRY: Sig Streak {TREND_STREAK} + Mega Streak {mega_count} + RSI {self.rsi:.1f} → SELL CE")
                            self.signal_sell_ce()
                            self.ensure_pe_exit()
                            self.entry_state = "IN_RED_TREND"
                    else:
                        logger.info(f"  ✋ Bearish Signal but RSI {self.rsi:.1f} is not in {RSI_OVERSOLD}-{RSI_PIVOT} zone.")
                else:
                    logger.info(f"  ✋ Signal Red but Mega Trend ({mega_count} bricks) weak or opposing.")

        # State: IN_GREEN_TREND (Bullish Position) -> Check for Pyramiding
        elif self.entry_state == "IN_GREEN_TREND":
            if self.nifty_renko.direction == -1: # Pullback color change
                if not self.pullback_active:
                    logger.info("  🔄 BULLISH PULLBACK Detected: Signal Renko flipped RED. Watching for 2-brick resumption.")
                    self.pullback_active = True
            
            elif self.pullback_active:
                # Check for 2 Green Bricks streak
                bricks_in_streak = 0
                for b in reversed(self.nifty_renko.bricks):
                    if b.color == 'GREEN': bricks_in_streak += 1
                    else: break
                
                if bricks_in_streak >= 2:
                    if self.pyramid_count < (MAX_PYRAMID_LOTS - 1):
                        logger.info(f"  🔥 PYRAMID: Bullish Resumption detected ({bricks_in_streak} bricks). Adding PE lot.")
                        self.signal_sell_pe()
                        self.pyramid_count += 1
                    self.pullback_active = False # Reset

        # State: IN_RED_TREND (Bearish Position) -> Check for Pyramiding
        elif self.entry_state == "IN_RED_TREND":
            if self.nifty_renko.direction == 1: # Pullback color change
                if not self.pullback_active:
                    logger.info("  🔄 BEARISH PULLBACK Detected: Signal Renko flipped GREEN. Watching for 2-brick resumption.")
                    self.pullback_active = True
            
            elif self.pullback_active:
                # Check for 2 Red Bricks streak
                bricks_in_streak = 0
                for b in reversed(self.nifty_renko.bricks):
                    if b.color == 'RED': bricks_in_streak += 1
                    else: break
                
                if bricks_in_streak >= 2:
                    if self.pyramid_count < (MAX_PYRAMID_LOTS - 1):
                        logger.info(f"  🔥 PYRAMID: Bearish Resumption detected ({bricks_in_streak} bricks). Adding CE lot.")
                        self.signal_sell_ce()
                        self.pyramid_count += 1
                    self.pullback_active = False # Reset

    def on_option_brick(self):
        # Custom Logic: Exit on 3 Green Bricks for more breathing room
        if not self.option_renko or not self.option_renko.bricks:
            return

        last_brick = self.option_renko.bricks[-1]
        
        if last_brick.color == 'GREEN':
             logger.info(f"  ⚠️  Option Reversal Warning: Price Rising...")

        logger.info(f"  🏁 Option Brick #{last_brick.index} Closed: {last_brick.color} @ {last_brick.close}")

        if len(self.option_renko.bricks) >= 3:
            last_3 = self.option_renko.bricks[-3:]
            if all(b.color == 'GREEN' for b in last_3):
                logger.info("  🛡️ OPTION REVERSAL: 3 Green Bricks (Premium Rising) → EXIT")
                if self.entry_state == "IN_GREEN_TREND": 
                    self.ensure_pe_exit()
                    self.entry_state = "WAITING"
                elif self.entry_state == "IN_RED_TREND": 
                    self.ensure_ce_exit()
                    self.entry_state = "WAITING"

    def signal_sell_ce(self):
        is_pyramid = 'CE' in self.active_positions
        logger.info(f"  {'🔴' if not is_pyramid else '🔥'} SIGNAL: {'SELL' if not is_pyramid else 'PYRAMID'} CE")
        
        atm = round(data_store.get_ltp(self.nifty_token) / 50) * 50
        
        if is_pyramid:
            pos = self.active_positions['CE']
            token = pos['token']
            symbol = pos['symbol']
            strike = pos['strike']
            # For pyramid, we add 1 standard lot (derived from master, not current position)
            base_qty = get_lot_size(self.broker.master_df, symbol)
            qty = base_qty * TRADING_LOTS
        else:
            strike = atm + 150 
            token, symbol = get_strike_token(self.broker, strike, "CE", self.expiry)
            if not token: return
            base_qty = get_lot_size(self.broker.master_df, symbol)
            qty = base_qty * TRADING_LOTS
        
        if token and symbol:
            if self.place_order(token, qty, "SELL", f"Renko {'Pyramid' if is_pyramid else 'Short'} CE", trading_symbol=symbol):
                if is_pyramid:
                    self.active_positions['CE']['qty'] += qty
                else:
                    self.active_positions['CE'] = {'token': token, 'strike': strike, 'symbol': symbol, 'qty': qty}
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

    def signal_sell_pe(self):
        is_pyramid = 'PE' in self.active_positions
        logger.info(f"  {'🟢' if not is_pyramid else '🔥'} SIGNAL: {'SELL' if not is_pyramid else 'PYRAMID'} PE")
        
        atm = round(data_store.get_ltp(self.nifty_token) / 50) * 50
        
        if is_pyramid:
            pos = self.active_positions['PE']
            token = pos['token']
            symbol = pos['symbol']
            strike = pos['strike']
            base_qty = get_lot_size(self.broker.master_df, symbol)
            qty = base_qty * TRADING_LOTS
        else:
            strike = atm - 150 
            token, symbol = get_strike_token(self.broker, strike, "PE", self.expiry)
            if not token: return
            base_qty = get_lot_size(self.broker.master_df, symbol)
            qty = base_qty * TRADING_LOTS

        if token and symbol:
            if self.place_order(token, qty, "SELL", f"Renko {'Pyramid' if is_pyramid else 'Short'} PE", trading_symbol=symbol):
                if is_pyramid:
                    self.active_positions['PE']['qty'] += qty
                else:
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
            self.save_state()

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
            self.save_state()

    def save_state(self):
        """Persist current strategy and Renko state to JSON."""
        try:
            state = {
                'entry_state': self.entry_state,
                'best_option_low': self.best_option_low,
                'current_option_token': self.current_option_token,
                'mega_renko': self.mega_renko.to_dict(),
                'nifty_renko': self.nifty_renko.to_dict(),
                'option_renko': self.option_renko.to_dict() if self.option_renko else None,
                'pyramid_count': self.pyramid_count,
                'pullback_active': self.pullback_active,
                'last_update': datetime.now().isoformat()
            }
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving state: {e}")

    def load_state(self):
        """Restore state from JSON if it belongs to the current trading day."""
        if not os.path.exists(self.state_file):
            return False
        
        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)
            
            # Check if stale (e.g. from previous day)
            last_upd = datetime.fromisoformat(state['last_update'])
            if last_upd.date() != datetime.now().date():
                logger.info("🗑️ Persisted state is from a previous day. Ignoring.")
                return False
                
            self.entry_state = state.get('entry_state', "WAITING")
            self.best_option_low = state.get('best_option_low', 999999)
            self.current_option_token = state.get('current_option_token')
            self.pyramid_count = state.get('pyramid_count', 0)
            self.pullback_active = state.get('pullback_active', False)
            
            self.mega_renko.from_dict(state['mega_renko'])
            self.nifty_renko.from_dict(state['nifty_renko'])
            
            if state.get('option_renko'):
                self.option_renko = RenkoCalculator()
                self.option_renko.from_dict(state['option_renko'])
                
            logger.info(f"✅ Strategy state RESTORED. Bricks: Mega({len(self.mega_renko.bricks)}), Nifty({len(self.nifty_renko.bricks)})")
            return True
        except Exception as e:
            logger.error(f"Error loading state: {e}")
            return False

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
                logger.warning("  ⚠️ No response from positions API.")
                return

            pos_data = positions_resp.get('data', []) if isinstance(positions_resp, dict) else positions_resp
            
            if not pos_data:
                logger.info("  ℹ️ API returned empty position list.")
                return

            count = 0
            for pos in pos_data:
                # Universal key lookup (Neo API is inconsistent)
                net_qty_val = pos.get('netQty', pos.get('netqty', pos.get('nqy', 0)))
                try:
                    net_qty = int(float(net_qty_val))
                except:
                    net_qty = 0
                    
                if net_qty == 0:
                    continue
                
                sym = str(pos.get('trdSym', pos.get('tsm', pos.get('symbol', '')))).upper()
                token = str(pos.get('tok', pos.get('tk', pos.get('instrument_token', ''))))
                
                if 'NIFTY' in sym and ('CE' in sym or 'PE' in sym):
                    p_type = 'CE' if 'CE' in sym else 'PE'
                    
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
                            
                            # Calculate Pyramid Count based on quantity
                            try:
                                base_lot = get_lot_size(self.broker.master_df, sym) * TRADING_LOTS
                                if base_lot > 0:
                                    self.pyramid_count = (abs(net_qty) // base_lot) - 1
                                    self.pyramid_count = max(0, self.pyramid_count)
                            except:
                                self.pyramid_count = 0
                            
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
                logger.info("  ℹ️ No relevant open Nifty SHORT positions found in API response.")
                # Diagnostic: Log symbols found even if they didn't match
                found_syms = [p.get('trdSym', p.get('tsm', 'Unknown')) for p in pos_data if int(float(p.get('netQty', p.get('nqy', 0)))) != 0]
                if found_syms:
                    logger.info(f"  🔍 Other active positions found: {found_syms}")
                
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

"""
Algo Strategy: ADX-Based Short ATM Straddle
Status: EXPERIMENTAL

Logic:
1. Entry: Sell ATM straddle when Nifty is consolidating (A+ Setup)
   - ADX < 25 (low trend strength)
   - Volatility < 0.04% of Nifty price
   - Data source: yfinance (refreshed every 60 seconds)
2. Exit: Track combined straddle premium (CE + PE total)
   - Primary: 2 consecutive GREEN Renko bricks (premium rising) → EXIT
   - Secondary: TSL breach → EXIT
"""

import os
import sys
import time
import threading
from datetime import datetime
import pandas as pd
import numpy as np
import yfinance as yf
import talib

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
logger = setup_strategy_logger("RangeStraddleStrategy", "algo_strategy_renko_straddle.log")

# ============================================================
# CONFIGURATION
# ============================================================

# Entry Conditions
CONSOLIDATION_RANGE_PTS = 25    # Max high-low range in last 30 mins to allow entry

ADX_THRESHOLD = 25            # Max ADX to allow entry (Filter for trending markets)

# Exit Conditions (Renko-based)
OPTION_BRICK_PCT = 0.03       # 3% brick size for straddle premium
                              # Rationale: Captures meaningful moves without noise
                              # For ₹200 straddle = ₹6 bricks
MIN_OPTION_BRICK = 1.5        # Minimum brick size (prevents micro-bricks on cheap options)

EXIT_REVERSAL_BRICKS = 2      # Number of consecutive GREEN bricks to trigger exit
                              # Rationale: 2 bricks = confirmation (not just noise)
                              
TSL_BRICK_MULTIPLIER = 3      # TSL trails by 3 bricks above best low
                              # Rationale: Gives room for natural premium fluctuation
                              # while protecting profits

# Risk Management
COOLDOWN_SECONDS = 600        # 10 minutes between exit and next entry
                              # Rationale: Prevents re-entry into same volatile spike

# System
NIFTY_TOKEN = "26000"
DRY_RUN = True                # Keep DRY_RUN=True for first live test
TRADING_LOTS = 1

# Intraday Time Filters
ENTRY_START_TIME = "09:20"    # Allow entries from 9:20 AM (no range check needed)
ENTRY_END_TIME = "14:20"      # Stop entries at 2:20 PM (avoid EOD volatility)
FORCE_EXIT_TIME = "15:15"     # Auto-exit all positions at 3:15 PM

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
        logger.info(f"  🧱 Renko Initialized @ ₹{start_price} (Brick: {self.brick_size})")

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
            if self.direction == 1:
                if price >= self.current_high + self.brick_size:
                    diff = price - self.current_high
                    num_bricks = int(diff // self.brick_size)
                    for _ in range(num_bricks):
                        self._add_brick('GREEN', self.current_high, self.current_high + self.brick_size, timestamp)
                        new_bricks_count += 1
                    added_this_loop = True
            elif self.direction == -1:
                if price <= self.current_low - self.brick_size:
                    diff = self.current_low - price
                    num_bricks = int(diff // self.brick_size)
                    for _ in range(num_bricks):
                        self._add_brick('RED', self.current_low, self.current_low - self.brick_size, timestamp)
                        new_bricks_count += 1
                    added_this_loop = True

            if not added_this_loop:
                if self.direction == 1: 
                     if price <= self.current_low - self.brick_size:
                        diff = self.current_low - price
                        num_bricks = int(diff // self.brick_size)
                        for _ in range(num_bricks):
                            self._add_brick('RED', self.current_low, self.current_low - self.brick_size, timestamp)
                            new_bricks_count += 1
                        self.direction = -1  # Set direction after all bricks created
                        added_this_loop = True
                elif self.direction == -1: 
                    if price >= self.current_high + self.brick_size:
                        diff = price - self.current_high
                        num_bricks = int(diff // self.brick_size)
                        for _ in range(num_bricks):
                            self._add_brick('GREEN', self.current_high, self.current_high + self.brick_size, timestamp)
                            new_bricks_count += 1
                        self.direction = 1  # Set direction after all bricks created
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

# Candle class removed - using yfinance data directly

class RangeTracker:
    """Tracks Nifty price history using Yfinance data"""
    def __init__(self, window_minutes=30):
        self.window_minutes = window_minutes
        self.history_df = pd.DataFrame(columns=['Open', 'High', 'Low', 'Close'])
        self.last_refresh_time = 0  # Track when we last fetched from yfinance
        
    def fetch_history(self):
        """Fetch latest 2 days of 1-minute data from Yfinance"""
        try:
            ticker = yf.Ticker("^NSEI")
            df = ticker.history(period="2d", interval="1m")
            
            if not df.empty:
                # Handle MultiIndex columns if present
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.droplevel(1)
                
                # Ensure we have required columns
                required = ['Open', 'High', 'Low', 'Close']
                if all(col in df.columns for col in required):
                    self.history_df = df[required].copy()
                    
                    # Remove timezone awareness for consistency
                    if self.history_df.index.tz is not None:
                        self.history_df.index = self.history_df.index.tz_localize(None)
                    
                    self.last_refresh_time = time.time()
                    logger.info(f"  ✅ Refreshed: {len(df)} candles | ADX: {self.get_adx():.1f}")
                else:
                    logger.error(f"  ❌ Yfinance missing columns. Got: {df.columns}")
            else:
                logger.warning("  ⚠️ Yfinance returned empty data")
                
        except Exception as e:
            logger.error(f"  ❌ Failed to fetch history: {e}")

    def needs_refresh(self):
        """Check if data needs refreshing (every 60 seconds)"""
        return (time.time() - self.last_refresh_time) >= 60



    def get_range(self, lookback_minutes=None):
        """Calculate high-low range from historical data"""
        if lookback_minutes is None:
            lookback_minutes = self.window_minutes
            
        if len(self.history_df) < 5:
            return 999
            
        recent_data = self.history_df.iloc[-lookback_minutes:]
        h_max = recent_data['High'].max()
        l_min = recent_data['Low'].min()
        return h_max - l_min

    def get_adx(self, period=14):
        """Calculate ADX(14) using TA-Lib on historical data"""
        if len(self.history_df) < period * 2:
            return 999
            
        # Get data arrays (TA-Lib needs float64)
        high = self.history_df['High'].values.astype(float)
        low = self.history_df['Low'].values.astype(float)
        close = self.history_df['Close'].values.astype(float)
        
        try:
            adx_series = talib.ADX(high, low, close, timeperiod=period)
            # Check for NaN (TA-Lib returns NaN for warmup period)
            last_adx = adx_series[-1]
            if np.isnan(last_adx):
                return 999
            return last_adx
        except Exception as e:
            logger.error(f"Error calc ADX: {e}")
            return 999
    
    def is_consolidating(self, current_nifty_price):
        """Check Max Range + ADX (A+ Setup)"""
        if len(self.history_df) < 15: # Min 15 candles
            return False
            
        # Check 1: Absolute Range
        current_range = self.get_range()
        if current_range > CONSOLIDATION_RANGE_PTS:
            return False

        # Check 2: ADX (Trend Strength)
        adx = self.get_adx(14)
        if adx > ADX_THRESHOLD:
            return False
            
        return True

class StraddleStrategy:
    def __init__(self, broker_client, nifty_token, ws_client=None):
        self.broker = broker_client
        self.client = broker_client.client
        self.nifty_token = nifty_token
        self.ws_client = ws_client 
        
        
        # Simple range tracker (30 minutes history)
        self.range_tracker = RangeTracker(window_minutes=30)
        
        # Straddle premium Renko
        self.straddle_renko = None 
        
        self.running = False
        self.active_positions = {}
        self.expiry = None
        self.entry_state = "WAITING" 
        self.best_straddle_low = 999999
        self.entry_premium = 0
        self.last_exit_time = None  # Cooldown tracker
        self.order_execution_gap = 0  # Track time between CE and PE orders
        
        # Parse time strings once (optimization)
        self.entry_start = datetime.strptime(ENTRY_START_TIME, "%H:%M").time()
        self.entry_end = datetime.strptime(ENTRY_END_TIME, "%H:%M").time()
        self.exit_time = datetime.strptime(FORCE_EXIT_TIME, "%H:%M").time()
    
        # Initialize history for ADX (Yfinance)
        self.range_tracker.fetch_history()

    def calculate_brick_size(self, price):
        raw_size = price * OPTION_BRICK_PCT
        if price < 100:
            return max(MIN_OPTION_BRICK, round(raw_size, 1))
        elif price < 300:
            return round(raw_size, 1)
        else:
            return min(50.0, round(raw_size, 1))
    
    def is_entry_allowed(self):
        """Check if current time is within entry window"""
        # Check cooldown period after last exit
        if self.last_exit_time and (time.time() - self.last_exit_time) < COOLDOWN_SECONDS:
            return False
        
        now = datetime.now().time()
        return self.entry_start <= now <= self.entry_end
    
    def is_exit_time(self):
        """Check if it's time to force exit"""
        return datetime.now().time() >= self.exit_time

    def start(self):
        self.running = True
        print(f"🚀 Range Straddle Strategy Started (A+ Setup: ADX < {ADX_THRESHOLD})")
        
        self.init_instruments()
        self.sync_active_positions()
        
        # Get initial price
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
             if DRY_RUN: initial_price = 25500.0
             else: 
                 logger.error("❌ Failed to fetch initial price")
                 return


        logger.info(f"✅ Initial Nifty: {initial_price}")
        threading.Thread(target=self._run_loop, daemon=True).start()

    def init_instruments(self):
        logger.info("Fetching Options Chain...")
        self.expiry = get_nearest_expiry()
        logger.info(f"Expiry: {self.expiry}")

    def _run_loop(self):
        logger.info("🔄 Strategy Loop Started")
        last_heartbeat = time.time()
        
        while self.running:
            try:
                nifty_ltp = data_store.get_ltp(self.nifty_token)
                
                if nifty_ltp <= 0:
                    time.sleep(1)
                    continue
                
                # 1. Refresh Nifty data from yfinance (every 60 seconds)
                if self.range_tracker.needs_refresh():
                    self.range_tracker.fetch_history()
                
                # 2. Check for entry (consolidation + time window)
                if self.entry_state == "WAITING":
                    if self.range_tracker.is_consolidating(nifty_ltp):
                        if self.is_entry_allowed():
                            range_val = self.range_tracker.get_range()
                            adx_val = self.range_tracker.get_adx()
                            
                            logger.info(f"  🚀 A+ Setup: ADX {adx_val:.1f} | Range {range_val:.2f} (Thresh: {CONSOLIDATION_RANGE_PTS})")
                            self.sell_atm_straddle()
                            self.entry_state = "IN_STRADDLE"
                        else:
                            # Outside entry window
                            pass
                
                # 3. Force exit at EOD
                if self.is_exit_time() and self.has_active_straddle():
                    logger.warning(f"  🕒 FORCE EXIT: End of day ({FORCE_EXIT_TIME})")
                    self.exit_straddle()
                    self.entry_state = "WAITING"
                
                # 4. Update straddle premium (if active)
                if self.has_active_straddle() and self.straddle_renko:
                    ce_ltp = data_store.get_ltp(self.active_positions['CE']['token'])
                    pe_ltp = data_store.get_ltp(self.active_positions['PE']['token'])
                    
                    if ce_ltp > 0 and pe_ltp > 0:
                        total_premium = ce_ltp + pe_ltp
                        
                        obricks = self.straddle_renko.update(total_premium, datetime.now())
                        if obricks > 0:
                            self.on_straddle_brick()
                        
                        # TSL breach check
                        if self.entry_state == "IN_STRADDLE":
                            tsl_trigger = self.best_straddle_low + (TSL_BRICK_MULTIPLIER * self.straddle_renko.brick_size)
                            if total_premium >= tsl_trigger:
                                logger.warning(f"  🚨 TSL Breach! Premium: ₹{total_premium:.2f} >= ₹{tsl_trigger:.2f}")
                                self.exit_straddle()
                                self.entry_state = "WAITING"
                
                # Heartbeat
                if time.time() - last_heartbeat > 3:
                    adx_val = self.range_tracker.get_adx()
                    range_val = self.range_tracker.get_range()
                    adx_str = f"{adx_val:.1f}" if adx_val < 900 else "Wait"
                    range_str = f"{range_val:.1f}" if range_val < 900 else "Wait"
                    
                    status_msg = f"📊 ADX: {adx_str} | Range: {range_str}" + (" ✅" if adx_val <= ADX_THRESHOLD and range_val <= CONSOLIDATION_RANGE_PTS else "")
                    
                    straddle_info = ""
                    if self.has_active_straddle() and self.straddle_renko:
                        ce_ltp = data_store.get_ltp(self.active_positions['CE']['token'])
                        pe_ltp = data_store.get_ltp(self.active_positions['PE']['token'])
                        
                        if ce_ltp > 0 and pe_ltp > 0:
                            total = ce_ltp + pe_ltp
                            
                            primary_exit = self.straddle_renko.current_high + (EXIT_REVERSAL_BRICKS * self.straddle_renko.brick_size)
                            secondary_exit = self.best_straddle_low + (TSL_BRICK_MULTIPLIER * self.straddle_renko.brick_size)
                            
                            straddle_info = f" | Straddle: ₹{total:.2f} (CE: ₹{ce_ltp:.2f} + PE: ₹{pe_ltp:.2f}) | 1° Exit: {primary_exit:.2f} | 2° TSL: {secondary_exit:.2f}"
                        else:
                            straddle_info = " | Straddle: Waiting for price data..."
                    
                    logger.info(f"💓 Heartbeat: Nifty {nifty_ltp:.2f} | {status_msg}{straddle_info}")
                    last_heartbeat = time.time()
                
                time.sleep(1) 
                
            except Exception as e:
                logger.error(f"❌ Error in Loop: {e}", exc_info=True)
                time.sleep(5)

    def on_straddle_brick(self):
        if not self.straddle_renko or not self.straddle_renko.bricks:
            return

        last_brick = self.straddle_renko.bricks[-1]
        
        # Update best low
        if last_brick.color == 'RED':
             if last_brick.low < self.best_straddle_low:
                 self.best_straddle_low = last_brick.low

        tsl_level = self.best_straddle_low + (TSL_BRICK_MULTIPLIER * self.straddle_renko.brick_size)
        
        if last_brick.color == 'RED':
             logger.info(f"  ⛓️  Straddle Decaying: TSL @ {tsl_level:.2f}")
        elif last_brick.color == 'GREEN':
             logger.info(f"  ⚠️  Straddle Rising: TSL Threat @ {tsl_level:.2f}")

        logger.info(f"  🏁 Straddle Brick #{last_brick.index}: {last_brick.color} @ ₹{last_brick.close}")

        # Primary exit: 2 GREEN bricks
        if len(self.straddle_renko.bricks) >= 2:
            last_2 = self.straddle_renko.bricks[-2:]
            if all(b.color == 'GREEN' for b in last_2):
                logger.info("  🛡️ REVERSAL: 2 Green Bricks → EXIT")
                self.exit_straddle()
                self.entry_state = "WAITING"

    def sell_atm_straddle(self):
        if self.has_active_straddle():
            return
        
        logger.info("  🎯 ENTRY: SELLING ATM STRADDLE")
        atm = round(data_store.get_ltp(self.nifty_token) / 50) * 50
        
        ce_token, ce_symbol = get_strike_token(self.broker, atm, "CE", self.expiry)
        pe_token, pe_symbol = get_strike_token(self.broker, atm, "PE", self.expiry)
        
        if ce_token and ce_symbol and pe_token and pe_symbol:
            base_qty = get_lot_size(self.broker.master_df, ce_symbol)
            qty = base_qty * TRADING_LOTS
            
            # ATOMIC ENTRY: Both legs must succeed
            # Track execution timing for monitoring
            ce_start = time.time()
            ce_success = self.place_order(ce_token, qty, "SELL", "Straddle CE", ce_symbol)
            ce_end = time.time()
            
            pe_start = time.time()
            pe_success = self.place_order(pe_token, qty, "SELL", "Straddle PE", pe_symbol)
            pe_end = time.time()
            
            # Log execution gap (for monitoring race condition risk)
            self.order_execution_gap = pe_end - ce_start
            logger.info(f"  ⏱️  Order Execution Gap: {self.order_execution_gap*1000:.0f}ms")
            
            if ce_success and pe_success:
                # Both succeeded - update positions
                self.active_positions['CE'] = {'token': ce_token, 'strike': atm, 'symbol': ce_symbol, 'qty': qty}
                self.active_positions['PE'] = {'token': pe_token, 'strike': atm, 'symbol': pe_symbol, 'qty': qty}
                
                if self.ws_client:
                    self.ws_client.subscribe([ce_token, pe_token], segment="nse_fo")
                
                # Premium fetch with retry logic
                # NOTE: Using LTP post-execution is a known limitation
                # Ideally, use fill prices from order response if available
                total_premium = 0
                for attempt in range(5):
                    time.sleep(0.5)  # Shorter wait, more retries
                    ce_ltp = data_store.get_ltp(ce_token)
                    pe_ltp = data_store.get_ltp(pe_token)
                    
                    if ce_ltp > 0 and pe_ltp > 0:
                        total_premium = ce_ltp + pe_ltp
                        self.entry_premium = total_premium
                        brick_size = self.calculate_brick_size(total_premium)
                        self.straddle_renko = RenkoCalculator(brick_size=brick_size)
                        self.straddle_renko.initialize(total_premium)
                        self.best_straddle_low = total_premium
                        logger.info(f"  📊 Straddle @ ₹{total_premium:.2f} (CE: ₹{ce_ltp:.2f} + PE: ₹{pe_ltp:.2f}) | Brick: ₹{brick_size}")
                        logger.info(f"  ℹ️  Note: Premium based on LTP (not fill price)")
                        break
                else:
                    # Failed to get premium after retries - exit immediately
                    logger.error("❌ Failed to get premium after entry - EXITING STRADDLE")
                    self.exit_straddle()
                    return
                    
            elif ce_success and not pe_success:
                # PE failed - rollback CE
                logger.error("❌ PE order failed - Rolling back CE")
                rollback_success = self.place_order(ce_token, qty, "BUY", "Rollback CE", ce_symbol)
                
                if not rollback_success:
                    logger.critical("🚨 CRITICAL: ROLLBACK FAILED - NAKED CE POSITION")
                    logger.critical(f"🚨 Manual intervention required: BUY {qty} {ce_symbol}")
                    logger.critical("🚨 HALTING STRATEGY - Manual cleanup required before restart")
                    
                    # Store partial position for manual cleanup
                    self.active_positions['CE'] = {
                        'token': ce_token, 
                        'symbol': ce_symbol, 
                        'qty': qty, 
                        'status': 'ORPHANED_ROLLBACK_FAILED'
                    }
                    
                    # HALT STRATEGY IMMEDIATELY
                    self.running = False
                    return
                else:
                    logger.info("✅ CE rollback successful")
                
            elif not ce_success and pe_success:
                # CE failed - rollback PE
                logger.error("❌ CE order failed - Rolling back PE")
                rollback_success = self.place_order(pe_token, qty, "BUY", "Rollback PE", pe_symbol)
                
                if not rollback_success:
                    logger.critical("🚨 CRITICAL: ROLLBACK FAILED - NAKED PE POSITION")
                    logger.critical(f"🚨 Manual intervention required: BUY {qty} {pe_symbol}")
                    logger.critical("🚨 HALTING STRATEGY - Manual cleanup required before restart")
                    
                    # Store partial position for manual cleanup
                    self.active_positions['PE'] = {
                        'token': pe_token, 
                        'symbol': pe_symbol, 
                        'qty': qty, 
                        'status': 'ORPHANED_ROLLBACK_FAILED'
                    }
                    
                    # HALT STRATEGY IMMEDIATELY
                    self.running = False
                    return
                else:
                    logger.info("✅ PE rollback successful")
                
            else:
                # Both failed
                logger.error("❌ Both orders failed - no entry")

    def exit_straddle(self):
        if not self.has_active_straddle():
            return
        
        logger.info("  👋 EXITING STRADDLE")
        
        if 'CE' in self.active_positions:
            pos = self.active_positions.pop('CE')
            self.place_order(pos['token'], pos['qty'], "BUY", "Exit CE", pos['symbol'])
            if self.ws_client: self.ws_client.unsubscribe([pos['token']])
        
        if 'PE' in self.active_positions:
            pos = self.active_positions.pop('PE')
            self.place_order(pos['token'], pos['qty'], "BUY", "Exit PE", pos['symbol'])
            if self.ws_client: self.ws_client.unsubscribe([pos['token']])
        
        self.straddle_renko = None
        self.best_straddle_low = 999999
        self.entry_premium = 0
        self.last_exit_time = time.time()  # Set cooldown

    def has_active_straddle(self):
        return 'CE' in self.active_positions and 'PE' in self.active_positions

    def place_order(self, token, qty, transaction_type, tag, trading_symbol=None):
        if DRY_RUN:
            logger.info(f"  🧪 DRY RUN: {transaction_type} {qty} {trading_symbol} [{tag}]")
            return True
        else:
            if not trading_symbol: return False
            try:
                logger.info(f"  📝 ORDER: {transaction_type} {qty} {trading_symbol}")
                order = self.client.place_order(exchange_segment="nse_fo", product="NRML", price="0", order_type="MKT", quantity=str(qty), validity="DAY", trading_symbol=trading_symbol, transaction_type="S" if transaction_type == "SELL" else "B")
                logger.info(f"✅ Order placed: {order}")
                return True
            except Exception as e:
                logger.error(f"❌ Order failed: {e}")
                return False

    def sync_active_positions(self):
        """Restore positions on restart WITH VALIDATION"""
        logger.info("🔄 Syncing positions...")
        try:
            positions_resp = self.client.positions()
            if not positions_resp:
                return

            pos_data = positions_resp.get('data', []) if isinstance(positions_resp, dict) else positions_resp
            if not pos_data:
                return

            # Collect potential straddle positions
            potential_positions = {}
            
            for pos in pos_data:
                net_qty = int(pos.get('netQty', 0))
                if net_qty >= 0:  # Only short positions (negative qty)
                    continue
                
                sym = pos.get('trdSym', '')
                if 'NIFTY' in sym and ('CE' in sym or 'PE' in sym):
                    p_type = 'CE' if 'CE' in sym else 'PE'
                    token = pos.get('tok')
                    
                    # Extract strike from symbol (e.g., NIFTY26JAN25670CE -> 25670)
                    try:
                        strike_str = sym.split('NIFTY')[1]  # Get part after NIFTY
                        strike_str = strike_str[5:]  # Remove date (DDMMM)
                        strike_str = strike_str.replace('CE', '').replace('PE', '')
                        strike = int(strike_str)
                    except:
                        logger.warning(f"⚠️ Could not parse strike from {sym}")
                        continue
                    
                    potential_positions[p_type] = {
                        'token': token,
                        'symbol': sym,
                        'qty': abs(net_qty),
                        'strike': strike
                    }
            
            # Validation: Ensure we have BOTH CE and PE
            if 'CE' not in potential_positions or 'PE' not in potential_positions:
                if potential_positions:
                    logger.warning(f"⚠️ Found incomplete straddle (only {list(potential_positions.keys())})")
                    logger.warning("⚠️ Not restoring - strategy only manages complete straddles")
                return
            
            # Validation: Check strikes are identical (ATM straddle)
            ce_strike = potential_positions['CE']['strike']
            pe_strike = potential_positions['PE']['strike']
            
            if ce_strike != pe_strike:
                logger.warning(f"⚠️ Strike mismatch: CE={ce_strike}, PE={pe_strike}")
                logger.warning("⚠️ Not restoring - not an ATM straddle")
                return
            
            # Validation: Check strike is near current ATM
            current_nifty = data_store.get_ltp(self.nifty_token)
            if current_nifty > 0:
                current_atm = round(current_nifty / 50) * 50
                strike_diff = abs(ce_strike - current_atm)
                
                if strike_diff > 200:  # More than 4 strikes away
                    logger.warning(f"⚠️ Restored strike {ce_strike} too far from current ATM {current_atm}")
                    logger.warning(f"⚠️ Difference: {strike_diff} points - likely an old/manual position")
                    logger.warning("⚠️ Not restoring - use manual exit for this position")
                    return
            
            # Validation: Check quantities match
            if potential_positions['CE']['qty'] != potential_positions['PE']['qty']:
                logger.warning(f"⚠️ Quantity mismatch: CE={potential_positions['CE']['qty']}, PE={potential_positions['PE']['qty']}")
                logger.warning("⚠️ Not restoring - imbalanced straddle")
                return
            
            # Validation: Check lot size is reasonable
            expected_lot_size = get_lot_size(self.client.master_df, potential_positions['CE']['symbol'])
            if expected_lot_size and potential_positions['CE']['qty'] % expected_lot_size != 0:
                logger.warning(f"⚠️ Quantity {potential_positions['CE']['qty']} not a multiple of lot size {expected_lot_size}")
                                
            # All validations passed - restore the position
            self.active_positions = potential_positions
            logger.info(f"  ✅ Validated & Restored Straddle: Strike {ce_strike}")
            logger.info(f"  ✅ CE: {potential_positions['CE']['symbol']} | Qty: {potential_positions['CE']['qty']}")
            logger.info(f"  ✅ PE: {potential_positions['PE']['symbol']} | Qty: {potential_positions['PE']['qty']}")
            
            # Subscribe to price feeds
            if self.ws_client:
                self.ws_client.subscribe([
                    potential_positions['CE']['token'],
                    potential_positions['PE']['token']
                ], segment="nse_fo")
            
            # Initialize Renko for exit tracking
            self.entry_state = "IN_STRADDLE"
            time.sleep(1)
            ce_ltp = data_store.get_ltp(potential_positions['CE']['token'])
            pe_ltp = data_store.get_ltp(potential_positions['PE']['token'])
            
            if ce_ltp > 0 and pe_ltp > 0:
                total = ce_ltp + pe_ltp
                brick_size = self.calculate_brick_size(total)
                self.straddle_renko = RenkoCalculator(brick_size=brick_size)
                self.straddle_renko.initialize(total)
                self.best_straddle_low = total
                self.entry_premium = total
                logger.info(f"  📊 Restored Straddle @ ₹{total:.2f} (Brick: ₹{brick_size})")
            else:
                logger.warning("⚠️ Could not fetch premium for restored position")
                
        except Exception as e:
            logger.error(f"❌ Sync error: {e}")



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
            strategy = StraddleStrategy(broker, NIFTY_TOKEN, ws_client=ws_client)
            strategy.start()
            try:
                while True: time.sleep(1)
            except KeyboardInterrupt:
                print("Exiting...")
    except Exception as e:
        print(f"Failed to start: {e}")

"""
Opening Range Breakout (ORB) Strategy with Break-and-Retest Confirmation

CORE EDGE: Avoid fake breakouts by waiting for price to retest the broken level
with strong confirmation before entry.

TRADING WINDOW: 09:15 - 10:45 (90 minutes)
TIMEFRAMES: 5-min for structure, 1-min for entries
INSTRUMENTS: Nifty Index (can trade futures or options)

RULES:
1. Opening Range = First 5-min candle (09:15-09:20)
2. Breakout = 5-min candle CLOSE outside OR
3. Retest = Price returns to broken level
4. Entry = Strong 1-min confirmation candle at retest
5. Stop Loss = Beyond opposite side of OR
6. Target = Minimum 2R

AVOIDANCE:
- No direct breakout entries
- No wick-only breakouts
- No weak confirmation candles
- Skip consolidation days (narrow OR)
"""

import sys
import os
import time
import pandas as pd
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List, Optional, Literal
from enum import Enum, auto

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'Kotak_Api'))) # Commented to fix lib conflict

# --- Upstox Imports ---
from lib.api.historical import get_historical_data_v3, get_intraday_data_v3
from lib.api.option_chain import get_option_chain_dataframe, get_atm_strike_from_chain
from lib.api.market_data import download_nse_market_data, get_market_quotes
from lib.utils.instrument_utils import get_option_instrument_key
from lib.utils.expiry_cache import get_expiry_for_strategy
from lib.utils.tick_aggregator import TickAggregator
from lib.api.streaming import UpstoxStreamer

# --- Kotak Imports ---
from Kotak_Api.lib.broker import BrokerClient
from Kotak_Api.lib.order_manager import OrderManager
from Kotak_Api.lib.trading_utils import get_strike_token, get_lot_size


class StrategyState(Enum):
    INITIALIZING = auto()
    WAITING_FOR_OR = auto()
    OR_FORMED = auto()
    MONITORING_BREAKOUT = auto()
    WAITING_FOR_RETEST = auto()
    POSITION_OPEN = auto()
    EXITED = auto()
    STOPPED = auto()


class ORBRetestStrategy:
    """
    Opening Range Breakout with Break-and-Retest Confirmation
    """
    
    def __init__(self, access_token: str, nse_data,
                 trading_lots: int = 1,
                 min_or_range_points: float = 20.0,
                 max_or_range_points: float = 150.0,
                 retest_tolerance: float = 5.0,
                 min_body_pct: float = 0.6,
                 stop_loss_buffer: float = 10.0,
                 risk_reward_ratio: float = 2.0,
                 retest_timeout_min: int = 30,
                 expiry_type: str = "current_week",
                 product_type: str = "MIS",
                 dry_run: bool = True):
        
        self.access_token = access_token
        self.nse_data = nse_data
        self.trading_lots = trading_lots
        self.product_type = product_type
        self.dry_run = dry_run
        
        # Strategy Parameters
        self.min_or_range_points = min_or_range_points
        self.max_or_range_points = max_or_range_points
        self.retest_tolerance = retest_tolerance
        self.min_body_pct = min_body_pct
        self.stop_loss_buffer = stop_loss_buffer
        self.risk_reward_ratio = risk_reward_ratio
        self.retest_timeout_min = retest_timeout_min
        self.expiry_type = expiry_type
        
        # Trading Times
        self.or_start_time = dt_time(9, 15)
        self.or_end_time = dt_time(9, 20)
        self.trading_end_time = dt_time(10, 45)
        
        # State
        self.state = StrategyState.INITIALIZING
        self.or_high = None
        self.or_low = None
        self.or_range = None
        self.breakout_direction = None  # 'LONG' or 'SHORT'
        self.breakout_level = None
        self.breakout_time = None
        self.retest_confirmed = False
        
        # Position
        self.position = None  # {'type': 'LONG/SHORT', 'entry': price, 'sl': price, 'target': price}
        self.entry_price = None
        self.stop_loss = None
        self.target = None
        
        # Instruments
        self.kotak_broker = None
        self.kotak_order_manager = None
        self.expiry_date = None
        self.atm_strike = None
        self.nifty_instrument_key = "NSE_INDEX|Nifty 50"
        
        # Aggregators & Streamer
        self.agg_5min = TickAggregator(5)
        self.agg_1min = TickAggregator(1)
        self.streamer = None
        
        # Logging
        self.log_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'logs')
        if not os.path.exists(self.log_dir):
            try: os.makedirs(self.log_dir)
            except: pass
        self.log_file = os.path.join(self.log_dir, f"orb_retest_{datetime.now().strftime('%Y%m%d')}.log")
    
    def log(self, message):
        """Log message to console and file"""
        ts = datetime.now().strftime('%H:%M:%S')
        print(f"[{ts}] {message}")
        try:
            with open(self.log_file, "a") as f:
                f.write(f"[{ts}] {message}\n")
        except: pass
    
    def initialize(self):
        """Initialize strategy components"""
        self.log("🚀 Initializing ORB Break-Retest Strategy...")
        
        # Initialize Kotak
        try:
            self.kotak_broker = BrokerClient()
            self.kotak_broker.authenticate()
            self.kotak_broker.load_master_data()
            self.kotak_order_manager = OrderManager(self.kotak_broker.client, dry_run=self.dry_run)
            self.log("✅ Kotak Neo Connected")
        except Exception as e:
            self.log(f"❌ Kotak Init Failed: {e}")
            return False
        
        # Get Expiry
        self.log(f"📅 Selecting {self.expiry_type} expiry...")
        try:
            expiry_str = get_expiry_for_strategy(
                access_token=self.access_token,
                expiry_type=self.expiry_type,
                instrument="NIFTY",
                force_refresh=False
            )
            self.expiry_date = expiry_str
            self.log(f"📅 Selected expiry: {self.expiry_date}")
        except Exception as e:
            self.log(f"❌ Expiry selection failed: {e}")
            return False
        
        return True
    
    def _init_streamer(self):
        """Initialize WebSocket for Ticks"""
        self.log("📡 Connecting to Upstox Streamer...")
        try:
             self.streamer = UpstoxStreamer(self.access_token)
             self.streamer.connect_market_data([self.nifty_instrument_key], mode="ltpc", on_message=self.on_market_data)
             
             # Wait for connection
             self.log("⏳ Waiting for WebSocket connection...")
             for _ in range(5):
                 time.sleep(1)
                 if self.streamer.market_data_connected:
                     self.log("✅ WebSocket connection confirmed")
                     break
             else:
                  self.log("⚠️ WebSocket not confirmed within 5s")

    def on_market_data(self, data):
        """Feed Ticks to Aggregators"""
        key = data.get('instrument_key')
        ltp = data.get('ltp')
        if key == self.nifty_instrument_key and ltp:
             ts = datetime.now()
             self.agg_5min.add_tick(key, ts, ltp)
             self.agg_1min.add_tick(key, ts, ltp)
    
    def get_5min_candles(self, start_date=None, end_date=None, completed_only=False):
        """
        Fetch 5-minute candles for Nifty
        completed_only: If True, ignores the last candle if it's currently forming
        """
        try:
            today_str = datetime.now().strftime('%Y-%m-%d')
            
            # Default to today
            if end_date is None:
                end_date = today_str
            if start_date is None:
                start_date = today_str
            
            # Check if requesting today's data
            if start_date == today_str and end_date == today_str:
                self.log(f"📊 Fetching INTRADAY 5-min candles for {today_str}")
                data = get_intraday_data_v3(
                    self.access_token,
                    self.nifty_instrument_key,
                    "minutes",
                    5
                )
                
                    self.log("⚠️ Intraday API returned no data")
                    return []
                
                # Seed Aggregators if empty
                if not self.agg_5min.candles:
                     self.agg_5min.update_historical(self.nifty_instrument_key, pd.DataFrame(data))
                
                # Use Aggregator Data if available and "fresh" enough
                agg_df = self.agg_5min.get_dataframe(self.nifty_instrument_key)
                if not agg_df.empty:
                    data = agg_df.to_dict('records') # Convert back to list of dicts for compatibility

                # Filter incomplete candles if requested
                
                # Filter incomplete candles if requested
                if completed_only and data:
                    last_ts = data[-1]['timestamp'] # Format: 2024-01-20T09:20:00+05:30
                    now = datetime.now()
                    # Calculate current interval start (e.g., 09:20:00)
                    curr_start = now.replace(second=0, microsecond=0, minute=(now.minute // 5) * 5)
                    curr_str = curr_start.strftime('%Y-%m-%dT%H:%M:%S+05:30')
                    
                    if last_ts == curr_str:
                        # self.log(f"ℹ️ Ignoring forming candle {last_ts}")
                        data.pop()
                        
                # self.log(f"📊 Received {len(data)} intraday candles")
                return data

            # Fallback to historical for other dates or ranges
            self.log(f"📊 Fetching Historical 5-min candles from {start_date} to {end_date}")
            
            data = get_historical_data_v3(
                self.access_token,
                self.nifty_instrument_key,
                "minutes",
                5,
                start_date,
                end_date
            )
            
            if not data:
                self.log("⚠️ API returned no data")
                return []
            
            self.log(f"📊 Received {len(data)} total candles from API")
            
            # Filter for today only if needed
            today_data = [c for c in data if c['timestamp'].startswith(today_str)]
            
            self.log(f"📊 Filtered to {len(today_data)} candles for today ({today_str})")
            return today_data
            
        except Exception as e:
            self.log(f"⚠️ Error fetching 5-min candles: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def get_1min_candles(self, lookback_minutes=120, completed_only=False):
        """Fetch recent 1-minute candles for Nifty"""
        try:
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
            
            data = get_historical_data_v3(
                self.access_token,
                self.nifty_instrument_key,
                "minutes",
                1,
                start_date,
                end_date
            )
            
            if not data:
                return []
            
            # Seed Aggregator
            if not self.agg_1min.candles:
                 self.agg_1min.update_historical(self.nifty_instrument_key, pd.DataFrame(data))
                 
            # Use Aggregator
            agg_df = self.agg_1min.get_dataframe(self.nifty_instrument_key)
            if not agg_df.empty:
                 # Convert DF to list of dicts
                 # Ensure headers match what logic expects ('close', 'timestamp', etc.)
                 data = agg_df.to_dict('records')
            
            # Filter for today only
            today_str = datetime.now().strftime('%Y-%m-%d')
            today_data = [c for c in data if c['timestamp'].startswith(today_str)]
            
            # Filter incomplete candles
            if completed_only and today_data:
                last_ts = today_data[-1]['timestamp']
                now = datetime.now()
                # For 1-min, current interval start is just now with seconds=0
                curr_start = now.replace(second=0, microsecond=0)
                curr_str = curr_start.strftime('%Y-%m-%dT%H:%M:%S+05:30')
                
                if last_ts == curr_str:
                    today_data.pop()
            
            return today_data[-lookback_minutes:] if len(today_data) > lookback_minutes else today_data
            
        except Exception as e:
            self.log(f"⚠️ Error fetching 1-min candles: {e}")
            return []
    
    def detect_opening_range(self):
        """Detect the 5-minute opening range (09:15-09:20)"""
        self.log("🔍 Detecting Opening Range...")
        
        # Fetch today's 5-min candles (Wait for complete OR)
        candles = self.get_5min_candles(completed_only=True)
        
        if not candles:
            self.log("❌ No 5-min candles found")
            return False
        
        # Find the first candle (09:15)
        or_candle = None
        for candle in candles:
            ts = candle['timestamp']
            # Strict check for 09:15 start
            if '09:15' in ts:
                or_candle = candle
                break
        
        if not or_candle:
            self.log("❌ Opening range candle (09:15) not found")
            return False
        
        self.or_high = or_candle['high']
        self.or_low = or_candle['low']
        self.or_range = self.or_high - self.or_low
        
        self.log(f"📊 Opening Range Detected (09:15):")
        self.log(f"   High: {self.or_high:.2f}")
        self.log(f"   Low: {self.or_low:.2f}")
        self.log(f"   Range: {self.or_range:.2f} points")
        
        # Validate range
        if self.or_range < self.min_or_range_points:
            self.log(f"⚠️ OR too narrow ({self.or_range:.2f} < {self.min_or_range_points}). Skipping trading.")
            return False
        
        if self.or_range > self.max_or_range_points:
            self.log(f"⚠️ OR too wide ({self.or_range:.2f} > {self.max_or_range_points}). Skipping trading.")
            return False
        
        self.log("✅ Opening Range Valid")
        return True
    
    def detect_breakout(self):
        """Detect 5-min candle close outside OR"""
        # Fetch recent 5-min candles (Completed Only!)
        candles = self.get_5min_candles(completed_only=True)
        
        if not candles:
            return False
        
        # Check latest candle
        latest = candles[-1]
        close = latest['close']
        ts = latest['timestamp']
        
        # Ignore the OR candle itself (09:15)
        if '09:15' in ts:
            return False

        # Bullish breakout
        if close > self.or_high:
            if self.breakout_direction is None:  # First breakout
                self.breakout_direction = 'LONG'
                self.breakout_level = self.or_high
                self.breakout_time = datetime.now()
                self.log(f"🔼 BULLISH BREAKOUT Detected at {ts}!")
                self.log(f"   Close: {close:.2f} > OR High: {self.or_high:.2f}")
                self.log(f"   Waiting for retest...")
                return True
        
        # Bearish breakout
        elif close < self.or_low:
            if self.breakout_direction is None:  # First breakout
                self.breakout_direction = 'SHORT'
                self.breakout_level = self.or_low
                self.breakout_time = datetime.now()
                self.log(f"🔽 BEARISH BREAKOUT Detected at {ts}!")
                self.log(f"   Close: {close:.2f} < OR Low: {self.or_low:.2f}")
                self.log(f"   Waiting for retest...")
                return True
        
        return False

    def detect_retest(self):
        """Detect retest with 1-min confirmation"""
        # Check timeout
        if self.breakout_time:
            elapsed = (datetime.now() - self.breakout_time).total_seconds() / 60
            if elapsed > self.retest_timeout_min:
                self.log(f"⏰ Retest timeout ({elapsed:.1f} min > {self.retest_timeout_min} min)")
                return 'TIMEOUT'
        
        # Fetch 1-min candles (Completed Only for Confirmation!)
        candles_1min = self.get_1min_candles(lookback_minutes=60, completed_only=True)
        
        if not candles_1min:
            return False
        
        # Check latest candle
        latest = candles_1min[-1]
        close = latest['close']
        high = latest['high']
        low = latest['low']
        
        # Bullish retest (price pulls back to or_high)
        if self.breakout_direction == 'LONG':
            # WICK TOUCH LOGIC: Check if Low touched the zone
            # Level: 22000. Low: 22003 (Near enough). Low: 21998 (Pierced, then closed up).
            dist = low - self.breakout_level
            
            # Check proximity (e.g. Low <= Level + tolerance) AND (Low >= Level - tolerance * 3 for deep pierce check?)
            # Actually, standard retest: Price comes back to level.
            if abs(dist) <= self.retest_tolerance or (low < self.breakout_level and close > self.breakout_level):
                 # Check for strong bullish confirmation
                if self.is_strong_bullish_candle(latest):
                    self.log(f"✅ BULLISH RETEST CONFIRMED!")
                    self.log(f"   Price {close:.2f} bounced off {self.breakout_level:.2f} (Low: {low:.2f})")
                    self.log(f"   Strong bullish candle detected")
                    return True
        
        # Bearish retest (price rallies back to or_low)
        elif self.breakout_direction == 'SHORT':
            # WICK TOUCH LOGIC: Check if High touched the zone
            dist = high - self.breakout_level
            
            if abs(dist) <= self.retest_tolerance or (high > self.breakout_level and close < self.breakout_level):
                # Check for strong bearish confirmation
                if self.is_strong_bearish_candle(latest):
                    self.log(f"✅ BEARISH RETEST CONFIRMED!")
                    self.log(f"   Price {close:.2f} rejected off {self.breakout_level:.2f} (High: {high:.2f})")
                    self.log(f"   Strong bearish candle detected")
                    return True
        
        return False
    def _resolve_option_params(self):
        """Resolve Token, Symbol and Calculate Qty based on Lot Size"""
        try:
            # 1. Determine Strike (ATM)
            spot_price = self.entry_price
            strike_price = round(spot_price / 50) * 50
            
            # 2. Determine Option Type
            option_type = "CE" if self.breakout_direction == 'LONG' else "PE" # Long Breakout -> Buy CE
            if self.breakout_direction == 'SHORT': option_type = "PE"
            
            self.log(f"🔍 Resolving NIFTY {self.expiry_date} {strike_price} {option_type}")
            
            # 3. Get Token & Symbol
            token, symbol = get_strike_token(self.kotak_order_manager.client, "NIFTY", self.expiry_date, strike_price, option_type)
            
            if not token:
                self.log("❌ Token not found!")
                return None, None, 0
                
            self.log(f"✅ Token Resolved: {token} | Symbol: {symbol}")
            
            # 4. Get Dynamic Lot Size
            lot_size = get_lot_size(self.kotak_broker.master_df, symbol)
            qty = lot_size * self.trading_lots
            
            self.log(f"📊 Lot Size: {lot_size} | Trading Lots: {self.trading_lots} | Total Qty: {qty}")
            
            return token, symbol, qty
            
        except Exception as e:
            self.log(f"❌ Resolution Error: {e}")
            return None, None, 0

    def _place_kotak_order(self, token, qty, transaction_type):
        """Raw Order Placement"""
        try:
            order_id = self.kotak_order_manager.place_order(
                instrument_token=int(token),
                transaction_type=transaction_type,
                quantity=qty,
                price=0, # Market
                tag="ORB_RETEST"
            )
            
            if order_id:
                self.log(f"🚀 {transaction_type} Order Placed! ID: {order_id}")
                return True
            else:
                self.log(f"❌ {transaction_type} Order Failed")
                return False
        except Exception as e:
            self.log(f"❌ Order Error: {e}")
            return False

    def execute_entry(self):
        """Execute trade entry"""
        # Get latest confirmation price
        candles_1min = self.get_1min_candles(lookback_minutes=5, completed_only=True)
        if not candles_1min:
            self.log("❌ Cannot get entry price")
            return False
        
        self.entry_price = candles_1min[-1]['close']
        
        # Calculate Spot SL/Target
        if self.breakout_direction == 'LONG':
            self.stop_loss = self.or_low - self.stop_loss_buffer
            risk = self.entry_price - self.stop_loss
            self.target = self.entry_price + (risk * self.risk_reward_ratio)
            self.log(f"📈 LONG ENTRY Triggered (Spot {self.entry_price})")
            
        elif self.breakout_direction == 'SHORT':
            self.stop_loss = self.or_high + self.stop_loss_buffer
            risk = self.stop_loss - self.entry_price
            self.target = self.entry_price - (risk * self.risk_reward_ratio)
            self.log(f"📉 SHORT ENTRY Triggered (Spot {self.entry_price})")
        
        # Resolve Option & Qty
        token, symbol, qty = self._resolve_option_params()
        if not token:
            return False

        # Execute Real Order
        if not self.dry_run:
            success = self._place_kotak_order(token, qty, "BUY")
            if not success: return False
        else:
            self.log(f"⚠️ Dry Run: would BUY {qty} of {symbol}")

        self.position = {
            'type': self.breakout_direction,
            'entry': self.entry_price,
            'sl': self.stop_loss,
            'target': self.target,
            'qty': qty,
            'token': token,
            'symbol': symbol
        }
        
        return True
    
    def monitor_position(self):
        """Monitor open position for SL/Target"""
        # Get current price
        candles_1min = self.get_1min_candles(lookback_minutes=5)
        if not candles_1min: return
        
        current_price = candles_1min[-1]['close']
        
        # Check stop loss
        if self.position['type'] == 'LONG':
            if current_price <= self.stop_loss:
                self.log(f"🛑 STOP LOSS HIT! Price: {current_price:.2f} <= SL: {self.stop_loss:.2f}")
                self.exit_position("Stop Loss")
                return
            
            if current_price >= self.target:
                self.log(f"🎯 TARGET HIT! Price: {current_price:.2f} >= Target: {self.target:.2f}")
                self.exit_position("Target")
                return
        
        elif self.position['type'] == 'SHORT':
            if current_price >= self.stop_loss:
                self.log(f"🛑 STOP LOSS HIT! Price: {current_price:.2f} >= SL: {self.stop_loss:.2f}")
                self.exit_position("Stop Loss")
                return
            
            if current_price <= self.target:
                self.log(f"🎯 TARGET HIT! Price: {current_price:.2f} <= Target: {self.target:.2f}")
                self.exit_position("Target")
                return
        
        # Calculate P&L estimate (Spot Points * Qty)
        qty = self.position.get('qty', 1)
        if self.position['type'] == 'LONG':
            pnl = (current_price - self.entry_price) * qty
        else:
            pnl = (self.entry_price - current_price) * qty
        
        self.log(f"📊 Position: {self.position['type']} | Price: {current_price:.2f} | Est P&L: {pnl:.2f}")
    
    def exit_position(self, reason):
        """Exit position"""
        self.log(f"🏁 Exiting Position: {reason}")
        
        if self.position and not self.dry_run:
            qty = self.position.get('qty', 0)
            token = self.position.get('token')
            
            if token and qty > 0:
                self._place_kotak_order(token, qty, "SELL")
                
        self.position = None
        self.state = StrategyState.EXITED
    
    def run(self):
        """Main strategy loop"""
        if not self.initialize():
            return
            
        # Start Streamer
        self._init_streamer()
        
        self.state = StrategyState.WAITING_FOR_OR
        
        while True:
            try:
                # 0. Global Kill Switch Check
                if os.path.exists("c:/algo/upstox/.STOP_TRADING"):
                    self.log("🛑 Global Kill Switch Detected (.STOP_TRADING). Stopping Strategy.")
                    if self.position: self.exit_position("Kill Switch")
                    break

                now = datetime.now()
                current_time = now.time()
                
                # Wait for market open
                if current_time < self.or_start_time:
                    self.log(f"⏳ Waiting for market open ({self.or_start_time})...")
                    time.sleep(30)
                    continue
                
                # Detect Opening Range
                if self.state == StrategyState.WAITING_FOR_OR:
                    if current_time >= self.or_end_time:
                        if self.detect_opening_range():
                            self.state = StrategyState.OR_FORMED
                        else:
                            self.log("❌ Invalid OR. Stopping strategy.")
                            break
                    else:
                        time.sleep(10)
                        continue
                
                # Monitor for breakout
                if self.state == StrategyState.OR_FORMED:
                    if self.detect_breakout():
                        self.state = StrategyState.WAITING_FOR_RETEST
                    time.sleep(30)  # Check every 30s
                
                # Wait for retest
                if self.state == StrategyState.WAITING_FOR_RETEST:
                    result = self.detect_retest()
                    if result == True:
                        if self.execute_entry():
                            self.state = StrategyState.POSITION_OPEN
                    elif result == 'TIMEOUT':
                        self.log("❌ No retest within timeout. Stopping.")
                        break
                    time.sleep(15)  # Check every 15s
                
                # Monitor position
                if self.state == StrategyState.POSITION_OPEN:
                    self.monitor_position()
                    time.sleep(15)  # Check every 15s
                
                # Exit at end of trading window
                if current_time >= self.trading_end_time:
                    if self.position:
                        self.exit_position("Time Exit")
                    self.log("⏰ Trading window closed. Stopping strategy.")
                    break
                
                # Exit if position closed
                if self.state == StrategyState.EXITED:
                    self.log("✅ Strategy completed.")
                    break
                
            except KeyboardInterrupt:
                self.log("⚠️ Strategy interrupted by user")
                break
            except Exception as e:
                self.log(f"❌ Error: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(30)


if __name__ == "__main__":
    from lib.core.authentication import check_existing_token, perform_authentication, save_access_token
    from lib.api.market_data import download_nse_market_data
    
    # Auth
    if not check_existing_token():
        try:
            token = perform_authentication()
            save_access_token(token)
        except: sys.exit(1)
    
    with open("lib/core/accessToken.txt", "r") as f:
        token = f.read().strip()
    
    nse_data = download_nse_market_data()
    
    # Run Strategy
    strategy = ORBRetestStrategy(
        token, nse_data,
        trading_lots=1,
        min_or_range_points=20.0,
        max_or_range_points=150.0,
        retest_tolerance=5.0,
        min_body_pct=0.6,
        stop_loss_buffer=10.0,
        risk_reward_ratio=2.0,
        retest_timeout_min=30,
        expiry_type="current_week",
        product_type="MIS",
        dry_run=False
    )
    
    strategy.run()

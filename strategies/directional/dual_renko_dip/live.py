"""
Live Implementation of Dual-Renko Strategy (Hybrid Model).
Data: Upstox API (1-min Candles for Trend, LTP for SL/Exit)
Execution: Kotak Neo (via Kotak_Api lib)
"""

import sys
import os
import time
import threading
import logging
from datetime import datetime, timedelta
import pandas as pd
from typing import Dict, Any, Optional

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
# Kotak_Api path
# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'Kotak_Api'))) # Commented to fix lib conflict

from strategies.directional.dual_renko_dip.core import DualRenkoCore, RenkoCalculator
from lib.api.historical import get_historical_data, get_intraday_data_v3
from lib.api.market_quotes import get_multiple_ltp_quotes
from kotak_api.lib.broker import BrokerClient
from kotak_api.lib.order_manager import OrderManager
from kotak_api.lib.trading_utils import get_strike_token, get_lot_size, get_nearest_expiry
from lib.utils.instrument_utils import get_option_instrument_key
from lib.api.streaming import UpstoxStreamer

# Logger
try:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', force=True)
except ValueError:
    # Fallback for older python versions
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logging.getLogger().setLevel(logging.INFO)

logger = logging.getLogger("DualRenkoLive")

class DualRenkoLive(DualRenkoCore):
    def __init__(self, upstox_access_token: str, config: Dict[str, Any]):
        super().__init__(config)
        self.upstox_token = upstox_access_token
        self.dry_run = config.get('dry_run', False)
        
        # Kotak Components
        self.kotak_broker = None
        self.kotak_client = None
        
        self.nifty_token = config.get('nifty_token', "NSE_INDEX|Nifty 50")
        self.state_file = "dual_renko_live_state.json"
        self.running = False
        self.last_sync_minute = None
        
        # Streaming Components
        self.streamer = None
        self.ltp_cache = {} # Map instrument_key -> float price

    def initialize(self):
        logger.info("🚀 Initializing Live Dual-Renko Strategy (Hybrid Model)...")
        
        # 1. Initialize Kotak
        try:
            logger.info("🔐 Authenticating Kotak Neo...")
            self.kotak_broker = BrokerClient()
            self.kotak_broker.authenticate()
            logger.info("📥 Loading Kotak Master Data...")
            self.kotak_broker.load_master_data()
            self.kotak_client = self.kotak_broker.client
            self.kotak_order_manager = OrderManager(self.kotak_client, dry_run=self.dry_run)
            logger.info("✅ Kotak Initialization Complete")
        except Exception as e:
            logger.error(f"❌ Kotak Initialization Failed: {e}")
            return False

        # 2. Restore Persistent State (Active Positions, Bricks)
        state_found = self.load_state(self.state_file)
        if state_found:
            logger.info("✅ State Restored from file.")

        # 3. State Sync / Self-Healing (Fill missing bricks)
        logger.info("📡 Syncing Renko State from Historical Data...")
        try:
            # Fetch last 100 1-minute candles for Nifty
            candles = get_historical_data(self.upstox_token, self.nifty_token, "1minute", 100)
            if not candles:
                logger.error("❌ Failed to fetch historical candles for sync")
                return False
            
            # Use the first candle's open to initialize if not already initialized
            if not self.nifty_renko.bricks and (self.nifty_renko.current_high is None):
                first_price = candles[0]['open']
                self.nifty_renko.initialize(first_price)
                self.mega_renko.initialize(first_price)
            
            # Replay candles that are newer than our last synced brick
            last_ts = None
            if self.nifty_renko.bricks:
                last_ts = pd.to_datetime(self.nifty_renko.bricks[-1].timestamp)
                if last_ts.tzinfo is not None:
                    last_ts = last_ts.tz_convert(None)

            new_count = 0
            for c in candles:
                ts = pd.to_datetime(c['timestamp'])
                if ts.tzinfo is not None:
                    ts = ts.tz_convert(None)
                    
                if last_ts is None or ts > last_ts:
                    self.nifty_renko.update_from_candle(c['high'], c['low'], ts)
                    self.mega_renko.update_from_candle(c['high'], c['low'], ts)
                    self.last_sync_minute = ts
                    new_count += 1
            
            logger.info(f"✅ State Synced. Processed {new_count} new candles. Current Bricks: Mega({len(self.mega_renko.bricks)}), Nifty({len(self.nifty_renko.bricks)})")
        except Exception as e:
            logger.error(f"❌ State Sync Failed: {e}")
            return False

        # 4. Initialize WebSocket Streamer
        logger.info("📡 Connecting to Upstox Market Data Feed...")
        try:
            self.streamer = UpstoxStreamer(self.upstox_token)
            logger.info("🔄 Calling connect_market_data...")
            self.streamer.connect_market_data(
                instrument_keys=[self.nifty_token],
                mode="ltpc",
                on_message=self.on_market_data
            )
            
            # Wait for WebSocket connection to be fully established
            logger.info("⏳ Waiting for WebSocket connection to stabilize...")
            for _ in range(5):
                time.sleep(1)
                if self.streamer.market_data_connected:
                    logger.info("✅ WebSocket connection confirmed")
                    break
            
            # Check if connection is active
            if not self.streamer.market_data_connected:
                logger.warning("⚠️ WebSocket connection not confirmed, but continuing...")
            else:
                # Explicitly subscribe to ensure we get data
                self.streamer.subscribe_market_data([self.nifty_token])
            
            # Pre-subscribe to any active positions (only if we have any)
            active_keys = []
            for side, pos in self.active_positions.items():
                u_key = f"NSE_FO|{pos['symbol']}"
                active_keys.append(u_key)
            
            if active_keys:
                logger.info(f"📡 Subscribing to {len(active_keys)} active positions...")
                try:
                    self.streamer.subscribe_market_data(active_keys)
                except Exception as sub_error:
                    logger.warning(f"⚠️ Failed to subscribe to active positions: {sub_error}")
                    # Continue anyway - we can subscribe later when positions are opened
                
        except Exception as e:
            logger.error(f"❌ WebSocket Connection Failed: {e}")
            import traceback
            traceback.print_exc()
            return False

        logger.info("✅ Initialization Complete")
        return True
    
    def on_market_data(self, data):
        """Handle incoming WebSocket messages (Handles both unrolled and rolled formats)"""
        try:
            # 1. Handle Unrolled Format (Preferred by UpstoxStreamer)
            if isinstance(data, dict) and 'instrument_key' in data:
                key = data['instrument_key']
                ltp = data.get('ltp') # UpstoxStreamer flattens ltpc.ltp into ltp
                if ltp is not None:
                    self.ltp_cache[key] = ltp
                return

            # 2. Handle Rolled Format (Backup)
            feeds = getattr(data, 'feeds', None)
            if feeds is None and isinstance(data, dict):
                feeds = data.get('feeds')
            
            if feeds:
                for key, feed in feeds.items():
                    ltp = None
                    if hasattr(feed, 'ltpc') and feed.ltpc:
                        ltp = feed.ltpc.ltp
                    elif isinstance(feed, dict):
                        ltp = feed.get('ltpc', {}).get('ltp', feed.get('ltp'))
                    
                    if ltp is not None:
                        self.ltp_cache[key] = ltp
                        # logger.debug(f"Tick: {key} -> {ltp}")
        except Exception as e:
            logger.error(f"Stream Parse Error: {e}")
            logger.debug(f"Data dump: {data}")

    def get_nifty_ltp(self) -> float:
        return self.ltp_cache.get(self.nifty_token, 0.0)

    def get_option_ltp(self, instrument_key: str) -> float:
        return self.ltp_cache.get(instrument_key, 0.0)

    def update_indicators(self):
        """Fetch RSI using historical + intraday data."""
        try:
            # 1. Fetch Historical (Last 5 days to be safe)
            # 1. Fetch Historical (Last 5 days to be safe)
            # Fetch 200 candles to allow Wilder's smoothing to stabilize
            hist_candles = get_historical_data(self.upstox_token, self.nifty_token, "1minute", 200) or []
            
            # 2. Fetch Intraday (Today's Live Data)
            intra_candles = get_intraday_data_v3(self.upstox_token, self.nifty_token, "minute", 1) or []
            
            # 3. Merge (Remove duplicates by timestamp)
            candle_dict = {c['timestamp']: c for c in hist_candles}
            for c in intra_candles:
                candle_dict[c['timestamp']] = c
            
            # Sort back to list
            candles = sorted(candle_dict.values(), key=lambda x: x['timestamp'])
            if candles and len(candles) > self.rsi_period:
                df = pd.DataFrame(candles)
                # RSI Calculation using TA-Lib
                import talib
                rsi_values = talib.RSI(df['close'].values, timeperiod=self.rsi_period)
                self.rsi = float(rsi_values[-1])
                
                last_closes = df['close'].tail(3).tolist()
                logger.info(f"📊 Updated RSI (TA-Lib): {self.rsi:.2f} | Rows: {len(df)} | Closes: {last_closes}")
        except Exception as e:
            logger.error(f"  ⚠️ RSI Update Failed: {e}")

    def execute_entry(self, option_type: str, timestamp: datetime, is_pyramid: bool = False):
        logger.info(f"🚀 SIGNAL: Executing {option_type} Entry (Pyramid: {is_pyramid})")
        
        nifty_ltp = self.get_nifty_ltp()
        
        # Fallback if WS hasn't updated yet
        if nifty_ltp == 0:
             logger.warning("⚠️ Nifty LTP is 0 (WS delay), fetching via API...")
             try:
                 res = get_multiple_ltp_quotes(self.upstox_token, [self.nifty_token])
                 if res and res.get('status') == 'success':
                     quotes_data = res.get('data', {})
                     if self.nifty_token in quotes_data:
                         nifty_ltp = quotes_data[self.nifty_token].get('last_price', 0)
                         logger.info(f"✅ Fetched API LTP: {nifty_ltp}")
             except Exception as e:
                 logger.error(f"❌ API Fetch Failed: {e}")
        
        if nifty_ltp == 0:
            logger.error("❌ Cannot execute entry: Nifty LTP is 0")
            return

        atm = round(nifty_ltp / 50) * 50
        offset = self.config.get('strike_offset', 150)
        strike = atm - offset if option_type == "PE" else atm + offset # OTM for selling
        
        expiry = get_nearest_expiry()
        
        # Kotak Resolution
        k_token, k_symbol = get_strike_token(self.kotak_broker, strike, option_type, expiry)
        if not k_token:
            logger.error(f"❌ Failed to resolve Kotak token for {strike} {option_type}")
            return

        base_lot = get_lot_size(self.kotak_broker.master_df, k_symbol)
        qty = base_lot * self.trading_lots
        
        order_id = self.kotak_order_manager.place_order(k_symbol, qty, "S", tag=f"DualRenko {'Pyramid' if is_pyramid else 'Entry'}", product="NRML")
        if order_id:
            # For data fetching in live, we need to resolve the Upstox key if it differs
            # Handle standard entry OR if we lost state (pyramid but key missing)
            if not is_pyramid or option_type not in self.active_positions:
                if is_pyramid:
                    logger.warning(f"⚠️ State synchronization issue: Pyramid signal for {option_type} but no active position found. Treating as new entry.")

                self.active_positions[option_type] = {
                    'symbol': k_symbol,
                    'qty': qty,
                    'token': k_token
                }
                # Initialize Option Renko for Exit Trend
                u_key = f"NSE_FO|{k_symbol}"
                self.streamer.subscribe_market_data([u_key]) # Subscribe to WS
                
                # Wait briefly for tick to arrive
                time.sleep(1)
                opt_price = self.get_option_ltp(u_key) or 100.0
                
                brick_size = self.calculate_option_brick_size(opt_price)
                self.option_renko = RenkoCalculator(brick_size=brick_size)
                self.option_renko.initialize(opt_price)
            else:
                self.active_positions[option_type]['qty'] += qty
            
            self.save_state(self.state_file)


    def execute_exit(self, option_type: str, reason: str, timestamp: Optional[datetime] = None):
        if option_type in self.active_positions:
            pos = self.active_positions.pop(option_type)
            logger.info(f"🛡️ EXIT: Executing {option_type} Exit | Reason: {reason}")
            order_id = self.kotak_order_manager.place_order(pos['symbol'], pos['qty'], "B", tag=f"Exit: {reason}", product="NRML")
            if order_id:
                logger.info(f"✅ Exit Order Placed for {option_type}. ID: {order_id}")
            
            u_key = f"NSE_FO|{pos['symbol']}"
            if self.streamer:
                self.streamer.unsubscribe_market_data([u_key]) # Unsubscribe
            
            self.option_renko = None
            self.save_state(self.state_file)

    def exit_all(self, reason: str = "Kill Switch"):
        """Exit all active positions."""
        if not self.active_positions:
            return
            
        logger.info(f"🏁 Exiting All Positions | Reason: {reason}")
        # Create a list of types to avoid mutation during iteration
        option_types = list(self.active_positions.keys())
        for option_type in option_types:
            self.execute_exit(option_type, reason)
        
        self.save_state(self.state_file)

    def run(self):
        self.running = True
        logger.info("🎬 Strategy Started - Continuous Monitoring (LTP) + Minute Sync (Candles)")
        
        last_indicator_update = 0
        
        while self.running:
            try:
                # 0. Global Kill Switch Check
                if os.path.exists("c:/algo/upstox/.STOP_TRADING"):
                    logger.info("🛑 Global Kill Switch Detected (.STOP_TRADING). Stopping Strategy.")
                    self.exit_all("Portfolio Manager Kill Switch")
                    self.running = False
                    break

                curr_now = datetime.now()
                # 1. CANDLE SYNC (Every Minute)
                # Check if we moved to a new minute
                if self.last_sync_minute is None or curr_now.minute != self.last_sync_minute.minute:
                    if curr_now.second >= 2: # Wait 2 seconds for candle to form reliably
                        sync_ts = curr_now.replace(second=0, microsecond=0)
                        logger.info(f"🔄 Minute Check: {sync_ts.strftime('%H:%M')} (Checking for new data...)")
                        self.last_sync_minute = curr_now # Mark as checked for this minute
                        
                        # Fetch the definitive 1-min candle
                        candles = get_intraday_data_v3(self.upstox_token, self.nifty_token, "minute", 1)
                        if candles:
                            latest_c = candles[-1]
                            c_ts = pd.to_datetime(latest_c['timestamp'])
                            if c_ts.tzinfo is not None:
                                c_ts = c_ts.tz_convert(None)
                            
                            # Only process if this is a NEW candle timestamp
                            last_brick_ts = None
                            if self.nifty_renko.bricks:
                                last_brick_ts = pd.to_datetime(self.nifty_renko.bricks[-1].timestamp)
                                if last_brick_ts.tzinfo is not None:
                                    last_brick_ts = last_brick_ts.tz_convert(None)

                            if not self.nifty_renko.bricks or c_ts > last_brick_ts:
                                logger.info(f"🔄 Minute Sync: Updating RSI for {c_ts.strftime('%H:%M')}")
                                self.update_indicators()
                                self.save_state(self.state_file)
                            else:
                                logger.debug(f"ℹ️ Candle for {c_ts.strftime('%H:%M')} already processed.")
                        else:
                            logger.warning(f"  ⚠️ No 1-min candle data available yet for {sync_ts.strftime('%H:%M')}")
                
                # 2. HIGH-FREQUENCY MONITORING (LTP)
                nifty_ltp = self.get_nifty_ltp()
                if nifty_ltp > 0:
                    # Update Nifty & Mega Renko Live
                    s_bricks = self.nifty_renko.update(nifty_ltp, curr_now)
                    for _ in range(s_bricks):
                        self.on_signal_brick(curr_now)
                        self.save_state(self.state_file)
                    
                    m_bricks = self.mega_renko.update(nifty_ltp, curr_now)
                    for _ in range(m_bricks):
                        self.on_mega_brick(curr_now)
                        self.save_state(self.state_file)

                    if int(time.time()) % 15 == 0:
                        logger.info(f"💓 Heartbeat | Nifty: {nifty_ltp:.2f} | RSI: {self.rsi:.2f} | Bricks: {len(self.nifty_renko.bricks)}")
                    
                    # Update Option Renko for Exit (using LTP for fast exit detection)
                    if self.option_renko and self.active_positions:
                        # Extract the key of the first active position
                        opt_type = next(iter(self.active_positions))
                        u_key = f"NSE_FO|{self.active_positions[opt_type]['symbol']}"
                        opt_ltp = self.get_option_ltp(u_key)
                        if opt_ltp > 0:
                            obricks = self.option_renko.update(opt_ltp, curr_now)
                            if obricks > 0: self.on_option_brick(curr_now)

                time.sleep(1) # Fast loop since we use cache
                
            except KeyboardInterrupt:
                self.running = False
            except Exception as e:
                logger.error(f"⚠️ Loop Error: {e}")
                time.sleep(5)

if __name__ == "__main__":
    token_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'lib', 'core', 'accessToken.txt')
    access_token = None
    if os.path.exists(token_path):
        with open(token_path, 'r') as f: access_token = f.read().strip()
    
    if not access_token:
        print("❌ No access token found.")
        sys.exit(1)

    config = {
        'dry_run': False,
        'nifty_token': "NSE_INDEX|Nifty 50",
        'nifty_brick_size': 5,
        'mega_brick_size': 30,
        'trading_lots': 1,
        'trend_streak': 3,
        'mega_min_bricks': 1,
        'max_pyramid_lots': 3,
        'strike_offset': 150,
    }

    strategy = DualRenkoLive(access_token, config)
    if strategy.initialize():
        strategy.run()
    else:
        print("❌ Initialization failed.")

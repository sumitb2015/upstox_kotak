"""
Futures Breakout Strategy
Logic: Sell OTM options when Nifty Futures breaks strike levels with volume confirmation.
"""

import sys
import os
import time
import logging
from datetime import datetime, timedelta
import pandas as pd
import talib
from typing import Dict, Any, Optional

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
# Kotak_Api path
# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'Kotak_Api'))) # Commented to fix lib conflict

from lib.api.historical import get_intraday_data_v3
from lib.api.market_quotes import get_multiple_ltp_quotes
from lib.api.streaming import UpstoxStreamer
from kotak_api.lib.broker import BrokerClient
from kotak_api.lib.order_manager import OrderManager
from kotak_api.lib.trading_utils import get_strike_token, get_lot_size, get_nearest_expiry
from lib.utils.instrument_utils import get_future_instrument_key, get_option_instrument_key

# Configure Logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("FuturesBreakout")

class FuturesBreakoutStrategy:
    def __init__(self, upstox_access_token: str, config: Dict[str, Any]):
        self.upstox_token = upstox_access_token
        self.config = config
        self.dry_run = config.get('dry_run', False)
        
        # Parameters
        self.vwap_period = config.get('vwap_period', 20) # Not used directly if calculating proper anchored VWAP, but maybe for SMA?
        self.volume_sma_period = config.get('volume_sma_period', 20)
        self.strike_step = config.get('strike_step', 50)
        self.strike_offset = config.get('strike_offset', 200)
        self.trading_lots = config.get('trading_lots', 1)
        
        # State
        self.running = False
        self.kotak_broker = None
        self.kotak_order_manager = None
        self.streamer = None
        
        self.future_key = None
        self.future_symbol = None # e.g. NIFTY 29 JAN FUt
        self.ltp_cache = {}
        self.last_candle_ts = None
        
        self.active_positions = {} # {'CE': {...}, 'PE': {...}}
        
        # Indicators
        self.current_vwap = 0.0
        self.volume_sma = 0.0
        self.trend = "NEUTRAL"
        
    def initialize(self):
        logger.info("🚀 Initializing Futures Breakout Strategy...")
        
        # 1. Kotak Setup
        try:
            logger.info("🔐 Authenticating Kotak Neo...")
            self.kotak_broker = BrokerClient()
            self.kotak_broker.authenticate()
            logger.info("📥 Loading Kotak Master Data...")
            self.kotak_broker.load_master_data()
            self.kotak_order_manager = OrderManager(self.kotak_broker.client, dry_run=self.dry_run)
            logger.info("✅ Kotak Initialization Complete")
        except Exception as e:
            logger.error(f"❌ Kotak Init Failed: {e}")
            return False

        # 2. Resolve Futures Instrument (Upstox)
        try:
            logger.info("📥 Downloading Upstox NSE Master Data...")
            from lib.api.market_data import download_nse_market_data
            self.nse_data = download_nse_market_data()
            
            if self.nse_data is None or self.nse_data.empty:
               logger.error("❌ Failed to download Upstox Master Data")
               return False

            logger.info("🔍 Resolving Nifty Futures Instrument...")
            self.future_key = get_future_instrument_key("NIFTY", self.nse_data)
            
            if not self.future_key:
                logger.error("❌ Failed to find active Nifty Futures contract")
                return False
                
            logger.info(f"✅ Locked Nifty Future: {self.future_key}")
            
        except Exception as e:
            logger.error(f"❌ Instrument Resolution Failed: {e}")
            return False

        # 3. Streamer Setup
        try:
            logger.info("📡 Connecting to Upstox Market Data Feed...")
            self.streamer = UpstoxStreamer(self.upstox_token)
            self.streamer.connect_market_data(
                instrument_keys=[self.future_key],
                mode="ltpc",
                on_message=self.on_market_data
            )
            # Wait for connection
            logger.info("⏳ Waiting for WebSocket connection...")
            for _ in range(5):
                time.sleep(1)
                if self.streamer.market_data_connected:
                    logger.info("✅ WebSocket Connected")
                    self.streamer.subscribe_market_data([self.future_key])
                    break
            else:
                 logger.warning("⚠️ WebSocket not confirmed within 5s")

        except Exception as e:
            logger.error(f"❌ Streamer Setup Failed: {e}")
            return False
            
        return True

    def on_market_data(self, data):
        """Handle incoming WebSocket data"""
        try:
            # Robust parsing (dict vs object)
            feeds = None
            if hasattr(data, 'feeds'): feeds = data.feeds
            elif isinstance(data, dict) and 'feeds' in data: feeds = data['feeds']
            
            if feeds:
                for key, feed in feeds.items():
                    ltp = None
                    if hasattr(feed, 'ltpc') and feed.ltpc: ltp = feed.ltpc.ltp
                    elif hasattr(feed, 'ff') and feed.ff:
                         if hasattr(feed.ff, 'marketFF') and feed.ff.marketFF: ltp = feed.ff.marketFF.ltp
                    
                    if ltp is None and isinstance(feed, dict):
                         # dict parsing fallback
                         pass # Assume object primarily based on recent debug

                    if ltp:
                        self.ltp_cache[key] = ltp
                        
        except Exception as e:
            pass # Silent fail to avoid spam, or log debug

    def run(self):
        if not self.initialize():
            logger.error("❌ Initialization Failed. Exiting.")
            return
            
        self.running = True
        logger.info("🎬 Strategy Started - Monitoring Futures Breakout...")
        
        while self.running:
            try:
                # 0. Global Kill Switch Check
                if os.path.exists("c:/algo/upstox/.STOP_TRADING"):
                    logger.info("🛑 Global Kill Switch Detected (.STOP_TRADING). Stopping Strategy.")
                    self.running = False
                    break

                self.process_logic()
                time.sleep(1)
            except KeyboardInterrupt:
                self.running = False
                logger.info("🛑 Strategy Stopped by User")
            except Exception as e:
                logger.error(f"⚠️ Loop Error: {e}")
                time.sleep(5)

    def process_logic(self):
        # 1. Candle Sync (Every Minute)
        curr_now = datetime.now()
        # Only check once per minute for candles
        if self.last_candle_ts is None or curr_now.minute != self.last_candle_ts.minute:
             if curr_now.second >= 2: # Wait for candle close
                 self.sync_candles()
                 self.last_candle_ts = curr_now

        # 2. Monitor LTP for Crossing (Every Tick)
        current_ltp = self.ltp_cache.get(self.future_key, 0)
        if current_ltp > 0:
            self.check_trigger(current_ltp)

    def sync_candles(self):
        """Fetch intraday candles and update indicators"""
        try:
            # Fetch data from today 09:15 to now?
            # get_intraday_data_v3(token, key, unit, interval_value)
            # unit="minute", interval_value=1 (for 1-minute candles)
            # The API returns all intraday candles; we don't pass a limit.
            
            candles = get_intraday_data_v3(self.upstox_token, self.future_key, "minute", 1)
            if not candles: return

            df = pd.DataFrame(candles)
            df['datetime'] = pd.to_datetime(df['timestamp'])
            
            # Sort by time
            df = df.sort_values('datetime')
            
            # Ensure numeric
            cols = ['open', 'high', 'low', 'close', 'volume']
            for c in cols: df[c] = pd.to_numeric(df[c])

            # Calculate Indicators
            # VWAP: Retrieve directly from API Quote (ATP)
            # Volume SMA: Use TA-Lib on candles
            from lib.api.market_data import get_vwap
            self.current_vwap = get_vwap(self.upstox_token, self.future_key)


            # Volume SMA 20 using TA-Lib
            df['vol_sma'] = talib.SMA(df['volume'], timeperiod=self.volume_sma_period)
            
            # Fill NaN
            df.fillna(0, inplace=True)
            
            self.df = df
            self.current_vol_sma = df['vol_sma'].iloc[-1]
            
            # Logger check for latest candle
            last = df.iloc[-1]
            logger.info(f"🕯️ Candle {last['datetime'].strftime('%H:%M')} | Close: {last['close']} | VWAP: {self.current_vwap:.2f} | Vol: {last['volume']} (Avg: {self.current_vol_sma:.1f})")

        except Exception as e:
            logger.error(f"⚠️ Candle Sync Failed: {e}")

    def check_trigger(self, ltp):
        """Check if LTP crosses Strike Levels"""
        if not hasattr(self, 'last_ltp') or self.last_ltp == 0:
            self.last_ltp = ltp
            return

        # Define Strike Levels (Step 50)
        # We look for CROSSING events
        
        # Current Level (Grid)
        curr_grid = (ltp // self.strike_step) * self.strike_step
        last_grid = (self.last_ltp // self.strike_step) * self.strike_step
        
        # Detect Crossing
        # Case 1: Bullish Breakout (Crossed Above a level)
        # e.g. Last 25790 (Grid 25750) -> Curr 25810 (Grid 25800)
        # Crossing happened if we moved from below Level to >= Level.
        
        # If we just use grid change:
        if curr_grid > last_grid:
            # Crossed UP into new zone?
            # Example: 25799 -> 25801.
            # Last Grid = 25750. Curr Grid = 25800.
            # Trigger Level = Curr Grid (25800).
            self.evaluate_signal(curr_grid, "BULLISH")
            
        elif curr_grid < last_grid:
            # Crossed DOWN
            # Example: 25801 -> 25799.
            # Last Grid = 25800. Curr Grid = 25750.
            # Trigger Level = Last Grid (25800) ? 
            # Or usually we say crossed BELOW 25800.
            # Grid logic: 25799 // 50 = 515 -> 25750.
            # Trigger was 25800.
            self.evaluate_signal(last_grid, "BEARISH")

        self.last_ltp = ltp

    def evaluate_signal(self, level, direction):
        """Verify Confirmation Logic"""
        if not hasattr(self, 'df') or self.df.empty:
            logger.warning("⚠️ Signal Ignored: No Candle Data")
            return

        # Check last 2 CLOSED candles (iloc[-3] and iloc[-2]?) 
        # API returns live candle as last?
        # get_intraday_data usually includes forming candle?
        # If so, ignore -1. Use -2 and -3.
        
        if len(self.df) < 5: return
        
        # Assume last row is forming/latest.
        c1 = self.df.iloc[-2] # Previous completed
        c2 = self.df.iloc[-3] # Pre-previous completed
        
        # Logic: 2 Consecutive Candles with Trend + Volume
        
        avg_vol = (c1['volume'] + c2['volume']) / 2
        vol_threshold = (c1['vol_sma'] + c2['vol_sma']) / 2 # Or use current SMA
        
        is_high_volume = avg_vol > vol_threshold
        
        valid_pattern = False
        
        if direction == "BULLISH":
            # Futures > VWAP (Trend) - Check current LTP against VWAP?
            # Or candles > VWAP?
            # Plan says: "Futures > VWAP"
            if self.ltp_cache[self.future_key] > self.current_vwap:
                # 2 Green Candles > VWAP
                # Condition: Close > Open AND Close > VWAP
                if (c1['close'] > c1['open'] and c1['close'] > c1['vwap']) and \
                   (c2['close'] > c2['open'] and c2['close'] > c2['vwap']):
                    valid_pattern = True
                    
        elif direction == "BEARISH":
            if self.ltp_cache[self.future_key] < self.current_vwap:
                # 2 Red Candles < VWAP
                if (c1['close'] < c1['open'] and c1['close'] < c1['vwap']) and \
                   (c2['close'] > c2['open'] and c2['close'] < c2['vwap']): # Wait check Bearish 2nd candle
                   # c2 usually Red too for confirmation?
                   if c2['close'] < c2['open'] and c2['close'] < c2['vwap']:
                       valid_pattern = True

        if valid_pattern and is_high_volume:
            logger.info(f"🚀 TRIGGER CONFIRMED: {direction} Breakout of {level} | Vol: {avg_vol:.0f} > {vol_threshold:.0f}")
            self.execute_trade(level, direction)
        else:
            logger.info(f"⚠️ Trigger {level} {direction} REJECTED | Vol: {is_high_volume} | Pat: {valid_pattern} | VWAP: {self.current_vwap:.2f}")

    def execute_trade(self, level, direction):
        # Calculate Strike
        offset = self.strike_offset
        if direction == "BULLISH":
            # Market UP -> Sell PUT (OTM)
            # Strike = Level - Offset
            strike = level - offset
            otype = "PE"
        else:
            # Market DOWN -> Sell CALL (OTM)
            # Strike = Level + Offset
            strike = level + offset
            otype = "CE"
            
        expiry = get_nearest_expiry()
        
        # Get Token
        k_token, k_symbol = get_strike_token(self.kotak_broker, strike, otype, expiry)
        if not k_token:
            logger.error(f"❌ Token not found for {strike} {otype}")
            return
            
        qty = get_lot_size(self.kotak_broker.master_df, k_symbol) * self.trading_lots
        
        # Place Order
        tag = "FuturesBreakout"
        logger.info(f"⚡ EXECUTING: SELL {qty} x {k_symbol} ({tag})")
        tag = "FuturesBreakout"
        logger.info(f"⚡ EXECUTING: SELL {qty} x {k_symbol} ({tag})")
        order_id = self.kotak_order_manager.place_order(k_symbol, qty, "S", tag=tag, product="NRML")
        
        if order_id:
            logger.info(f"✅ Order Successfully Placed for {k_symbol}. ID: {order_id}")
            # TODO: Track position in self.active_positions if needed
        else:
             logger.error(f"❌ Order Failed for {k_symbol}")


if __name__ == "__main__":
    # Load Token
    token_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'lib', 'core', 'accessToken.txt')
    if os.path.exists(token_path):
        with open(token_path, 'r') as f: access_token = f.read().strip()
    else:
        print("❌ No access token found.")
        sys.exit(1)

    config = {
        'dry_run': True,
        'strike_offset': 200,
        'trading_lots': 1
    }
    
    strategy = FuturesBreakoutStrategy(access_token, config)
    strategy.run()

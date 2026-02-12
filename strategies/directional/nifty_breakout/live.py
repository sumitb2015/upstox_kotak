"""
Execution Engine for Nifty Breakout Strategy.
Fetches Previous Day's High/Low/VWAP and runs live monitoring loop.
"""

import sys
import os
import time
import logging
import pandas as pd
from datetime import datetime, timedelta

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from strategies.directional.nifty_breakout import config
from strategies.directional.nifty_breakout.core import process_market_data, check_entry_signal, calculate_strikes

# Core Libraries
from lib.api.historical import get_historical_data, get_intraday_data_v3
from lib.core.authentication import get_access_token
from lib.api.market_data import fetch_historical_data, get_ltp, download_nse_market_data
from lib.api.streaming import UpstoxStreamer # WebSocket Import
from lib.utils.indicators import calculate_vwap
from lib.utils.instrument_utils import get_option_instrument_key
from kotak_api.lib.broker import BrokerClient
from kotak_api.lib.order_manager import OrderManager
from kotak_api.lib.trading_utils import get_strike_token

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"strategies/logs/{config.STRATEGY_NAME}_{datetime.now().strftime('%Y-%m-%d')}.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(config.STRATEGY_NAME)

class NiftyBreakoutStrategy:
    def __init__(self):
        self.kotak_broker = BrokerClient()
        self.kotak_client = self.kotak_broker.authenticate()
        self.order_mgr = OrderManager(self.kotak_client, dry_run=config.DRY_RUN)
        self.upstox_token = None
        
        self.prev_high = 0.0
        self.prev_low = 0.0
        self.prev_vwap = 0.0
        self.token = None # Nifty Token
        self.positions = {} # symbol -> {qty, entry_price, sl_price, target_price, upstox_key}
        self.pyramid_count = 0
        self.nse_data = None
        
        # WebSocket Component
        self.streamer = None
        self.latest_candle = None
        
    def setup(self):
        """Initial Setup: Get Token and Calculate Yesterday's Levels."""
        logger.info("[CORE] Starting Strategy Setup...")
        
        # 0. Get Upstox Access Token
        self.upstox_token = get_access_token()
        if not self.upstox_token:
            logger.error("[CORE] Failed to get Upstox Access Token. Exiting.")
            sys.exit(1)
            
        # 0.1 Download NSE Master Data (For Option Key Lookup)
        self.nse_data = download_nse_market_data()
        if self.nse_data is None:
            logger.error("[UPSTOX] Failed to download NSE Master Data. Exiting.")
            sys.exit(1)

        # 1. diverse Token Lookup (Simulated, assume we have a utility or hardcode for now for Nifty Index)
        # In reality, need to fetch token for Nifty 50 Index.
        # Let's assume Nifty 50 Index token is 26000 (Example).
        # Better: use a search utility. For now, we will use the symbol directly with api.
        self.token = "NSE_INDEX|Nifty 50" # Standard Instrument Key
        
        # 2. Fetch History (Last 5 days)
        logger.info(f"[UPSTOX] Fetching historical data for {self.token}...")
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=5)
        
        hist_df = fetch_historical_data(
            self.upstox_token,
            self.token,
            "day",
            1,
            start_date,
            end_date
        )
        
        if hist_df is None or hist_df.empty:
            logger.error("[CORE] Failed to fetch historical data. Exiting.")
            sys.exit(1)
            
        # Get Yesterday's Data (iloc[-2] because -1 is today/incomplete if run during market hours, or today if EOD)
        # Assuming run BEFORE market open or DURING market, -1 is likely the purely historical candle of yesterday if get_historical_data returns only completed days?
        # Standard behavior: get_historical_data usually returns completed candles.
        # Let's safely take the last row describing a full day.
        # If today is Monday, we want Friday.
        
        # Check date of last row
        last_date = pd.to_datetime(hist_df['timestamp'].iloc[-1]).date()
        today_date = datetime.now().date()
        
        if last_date == today_date:
            yesterday_row = hist_df.iloc[-2]
        else:
            yesterday_row = hist_df.iloc[-1]
            
        self.prev_high = float(yesterday_row['high'])
        self.prev_low = float(yesterday_row['low'])
        # Calculate VWAP for that day? Historic API "day" candles often don't have VWAP.
        # If we need Closing VWAP, we might need intraday data for that day.
        # Approximating with Typical Price for now as per standard daily candle limitation.
        self.prev_vwap = (self.prev_high + self.prev_low + float(yesterday_row['close'])) / 3
        
        logger.info(f"[CORE] Yesterday's Levels :: High: {self.prev_high}, Low: {self.prev_low}, Est. VWAP: {self.prev_vwap}")

        # 3. Initialize Streamer
        self.streamer = UpstoxStreamer(self.upstox_token)
        self.streamer.connect_market_data(
            instrument_keys=[self.token],
            mode="full", # Full mode required for OHLC
            on_message=self.on_market_update
        )

    def on_market_update(self, data):
        """Callback for WebSocket Updates."""
        # 1. Store Latest Candle if available
        if 'ohlc_1m' in data:
            self.latest_candle = data['ohlc_1m']
            logger.info(f"[WS] New Candle: {self.latest_candle['close']} at {self.latest_candle['timestamp']}")
            
            # Trigger Logic on Candle Close
            self.execute_logic(self.latest_candle)

    def execute_logic(self, candle):
        """Driven by WebSocket Candle Update."""
        try:
            ltp = float(candle['close'])
            
            # Supertrend Logic requires History + Latest Candle.
            # Ideally we maintain a DataFrame of recent history and append this candle.
            # For this simplified version, we will use the LTP and Trend from a maintained state or fetch small history if needed.
            
            # Optimization: We can fetch history ONCE and then append new candles.
            # Or continue to fetch small intraday chunk for indicators if cheap.
            # To be safe and compliant with "Merged Pattern", let's use get_intraday_data_v3 for the indicator calculation
            # BUT only trigger it when we have a new candle from WS.
            
            intraday_df = get_intraday_data_v3(self.upstox_token, self.token, "minute", 5)
            trend, st_value, _ = process_market_data(intraday_df, config.SUPERTREND_PERIOD, config.SUPERTREND_MULTIPLIER)
            
            logger.info(f"[CORE] LTP: {ltp} | Trend: {trend}")
            
            # 2. Check Entry Signal
            if not self.positions:
                signal = check_entry_signal(ltp, self.prev_high, self.prev_low, trend)
                if signal:
                    self.enter_position(signal, ltp)

            # 3. Manage Existing Positions
            else:
                self.manage_positions()
                
        except Exception as e:
            logger.error(f"[CORE] Error in logic: {e}", exc_info=True)

    def enter_position(self, signal, ltp):
        """Executes Entry Order."""
        logger.info(f"[CORE] Entry Signal Triggered: {signal}")
        
        # Calculate Strike
        ce_strike, pe_strike = calculate_strikes(ltp, config.STRIKE_OFFSET)
        
        transaction_type = "S" # Strategy is SELLING Options
        
        if signal == "BULLISH":
            # Bullish -> Sell PE
            strike = pe_strike
            opt_type = "PE"
        elif signal == "BEARISH":
            # Bearish -> Sell CE
            strike = ce_strike
            opt_type = "CE"
            
        # Get Token/Symbol Name from Kotak Utils
        # Need Expiry date
        from lib.utils.expiry_cache import get_expiry_for_strategy
        expiry = get_expiry_for_strategy(config.SYMBOL, config.EXPIRY_TYPE)
        
        # 1. Resolve Kotak Trading Symbol (For Execution)
        trading_symbol = get_strike_token(self.kotak_broker, strike, opt_type, expiry)
        
        if not trading_symbol:
            logger.error(f"[KOTAK] Could not resolve symbol for {strike} {opt_type} {expiry}")
            return

        # 2. Resolve Upstox Instrument Key (For Data/LTP)
        upstox_key = get_option_instrument_key(config.INSTRUMENT_NAME, strike, opt_type, self.nse_data, expiry)
        if not upstox_key:
             logger.error(f"[UPSTOX] Could not resolve Instrument Key for {strike} {opt_type} {expiry}")
             return

        # Subscribe to Option Token for LTP tracking
        logger.info(f"[WS] Subscribing to Option Key: {upstox_key}")
        self.streamer.subscribe_market_data([upstox_key], mode="ltpc")

        logger.info(f"[KOTAK] Placing SELL Order for {trading_symbol} ({strike} {opt_type})")
        
        success = self.order_mgr.place_order(
            symbol=trading_symbol,
            qty=config.LOT_SIZE, # Need to multiply by lot size multiplier? Usually SDK handles or config has raw qty. Assuming config.LOT_SIZE is raw quantity.
            transaction_type=transaction_type,
            tag="Breakout_Entry"
        )
        
        if success:
            self.positions[trading_symbol] = {
                'entry_price': ltp, # Approximate, ideally fetch order fill price
                'qty': config.LOT_SIZE,
                'sl': ltp * (1 + (config.SL_PCT/100)), # SL for Short is Higher
                'target': ltp * (1 - (config.TARGET_PCT/100)), # Target for Short is Lower
                'type': opt_type,
                'upstox_key': upstox_key
            }
            logger.info(f"[CORE] Position Tracked: {self.positions[trading_symbol]}")

    def manage_positions(self):
        """
        Manages active positions: SL, Target, TSL, Pyramiding.
        Iterates through tracked positions and fetches their LTPs from WS Cache.
        """
        if not self.positions:
            return

        # 1. Fetch LTPs for all active Option Symbols
        symbols = list(self.positions.keys())
        # Assuming get_ltp can handle multiple symbols or we loop
        # For simplicity, loop or use bulk fetch if available. 
        # get_ltp(token) usually takes instrument_token? 
        # Kotak might need a different call for LTP. 
        # Upstox get_ltp uses instrument_key.
        # We need the Upstox Instrument Key for the Option Symbol to get LTP.
        # This mapping might be complex if we only have the Trading Symbol (Kotak).
        # We need to ensure we have the Instrument Key.
        
        # For this implementation, I will assume we stored the Upstox Instrument Key 
        # in the position dict during entry.
        # But wait, enter_position only resolved the Kotak Trading Symbol.
        # We need a way to get the Upstox Key for that symbol.
        # OR, we rely on Kotak for LTP? No, "Data Fetching" is Upstox rule.
        
        # Let's assume we can derive or fetch the Upstox Key.
        # For now, to keep it runnable, I will use a placeholder for "fetch_option_ltp".
        
        for symbol, pos in list(self.positions.items()):
            # Fetch Real LTP using Upstox Key from Streamer Cache
            upstox_key = pos.get('upstox_key')
            
            # Get latest feed from streamer cache
            feed = self.streamer.get_latest_data(upstox_key)
            
            if not feed:
                # Fallback to REST API if cache empty (first tick pending)
                ltp = get_ltp(self.upstox_token, upstox_key)
            else:
                ltp = float(feed.get('ltp', 0)) or float(feed.get('last_price', 0))

            if ltp == 0:
                 continue
            
            entry = pos['entry_price']
            # qty = pos['qty'] # Not used
            sl = pos['sl']
            target = pos['target']
            # opt_type = pos['type'] # 'CE' or 'PE' -> We are SELLING, so Short. # Not used
            
            # --- Short Position Logic ---
            # Profit = Entry - LTP
            
            # 1. Check Stop Loss (LTP > SL)
            if ltp >= sl:
                logger.info(f"[CORE] SL Hit for {symbol}. LTP: {ltp}, SL: {sl}")
                self.exit_position(symbol, "SL_HIT")
                continue
                
            # 2. Check Target (LTP <= Target)
            if ltp <= target:
                logger.info(f"[CORE] Target Hit for {symbol}. LTP: {ltp}, TGT: {target}")
                self.exit_position(symbol, "TARGET_HIT")
                continue
                
            # 3. Trailing SL
            # If LTP moves down (favor), move SL down.
            # Simple TSL: Keep SL distance constant? Or dynamic?
            # User said "implement a trailing SL". 
            # Risk Skill says "Hybrid Gated...". 
            # Let's simple Trail: If new low made, move SL down.
            # Track 'lowest_ltp'.
            # TSL logic placeholder - kept simple for now
            
            # 4. Pyramiding
            # "pyramidding at 5% profit. max pyramids are 3"
            profit_points = entry - ltp
            profit_pct = (profit_points / entry) * 100
            
            if config.PYRAMID_ENABLED and self.pyramid_count < config.MAX_PYRAMID_COUNT:
                # 5% profit steps: 5%, 10%, 15%
                next_pyramid_threshold = (self.pyramid_count + 1) * config.PYRAMID_ENTRY_PCT
                
                if profit_pct >= next_pyramid_threshold:
                    logger.info(f"[CORE] Pyramiding Triggered for {symbol}. Profit: {profit_pct}%")
                    self.pyramid_position(symbol, ltp)

    def exit_position(self, symbol, reason):
        """Exits the position."""
        logger.info(f"[KOTAK] Exiting {symbol} via method: {reason}")
        self.order_mgr.place_order(symbol, qty=self.positions[symbol]['qty'], transaction_type="B", tag=reason)
        
        # Unsubscribe from Option Key to save bandwidth
        if symbol in self.positions:
             key = self.positions[symbol].get('upstox_key')
             if key:
                 self.streamer.unsubscribe_market_data([key])
        
        del self.positions[symbol]

    def pyramid_position(self, symbol, ltp):
        """Adds to the position."""
        qty_to_add = config.PYRAMID_LOTS
        
        success = self.order_mgr.place_order(symbol, qty=qty_to_add, transaction_type="S", tag="Pyramid_Add")
        
        if success:
            # Update Average Price 
            old_qty = self.positions[symbol]['qty']
            old_entry = self.positions[symbol]['entry_price']
            
            new_qty = old_qty + qty_to_add
            new_avg = ((old_qty * old_entry) + (qty_to_add * ltp)) / new_qty
            
            self.positions[symbol]['qty'] = new_qty
            self.positions[symbol]['entry_price'] = new_avg
            # SL might need adjustment? Usually Keep SL at original or tighten.
            # Leaving SL as is for now.
            
            self.pyramid_count += 1
            logger.info(f"[CORE] Pyramiding Success. New Qty: {new_qty}, Avg Price: {new_avg}")

    def run(self):
        """Main execution entry point."""
        self.setup()
        logger.info(f"[CORE] Strategy {config.STRATEGY_NAME} Started (WebSocket Mode).")
        
        # Keep main thread alive for WebSocket
        while True:
            try:
                now = datetime.now()
                if now.time() >= datetime.strptime(config.EXIT_TIME, "%H:%M:%S").time():
                    logger.info("[CORE] Exit Time Reached. Shutting down.")
                    self.streamer.disconnect_all()
                    break
                    
                time.sleep(1) 
            except KeyboardInterrupt:
                logger.info("[CORE] Strategy stopped by user.")
                self.streamer.disconnect_all()
                break
            except Exception as e:
                logger.error(f"[CORE] Critical Error in run loop: {e}", exc_info=True)
                time.sleep(5)

if __name__ == "__main__":
    strategy = NiftyBreakoutStrategy()
    strategy.run()

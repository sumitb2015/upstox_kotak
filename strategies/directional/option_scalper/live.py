"""
Option Scalper Strategy - Live Implementation
------------------------------------------
High-frequency scalping based on Order Book Imbalance and Price Momentum.

Strategy Logic Summary:
1. Signal Detection (CORE):
   - Market Depth: Monitors Bid/Ask quantity imbalance in the top 5 levels.
   - Momentum: Uses 10-tick ROC (Rate of Change).
   - Trigger: Depth imbalance > 2.5x + ROC alignment.

2. Strategy Execution (KOTAK):
   - Fast Market orders on OTM options.

3. Risk Management (CORE):
   - Fixed SL: 15% or 5 points.
   - Target: 10% profit.
   - Staleness: Exit if momentum stalls for > 30s.
"""

import os
import sys
import time
import threading
import logging
from datetime import datetime

# Add project root to path (4 levels up)
root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # live.py -> scalper -> directional -> strategies -> upstox
if root not in sys.path:
    sys.path.append(root)

from strategies.directional.option_scalper.config import SCALPER_CONFIG
from strategies.directional.option_scalper.strategy_core import OptionScalperCore

from lib.core import authentication
from lib.api import market_quotes, option_chain
from lib.api.streaming import UpstoxStreamer

# Setup Logging
logger = logging.getLogger("OptionScalperLive")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

class OptionScalperLive(OptionScalperCore):
    def __init__(self):
        super().__init__(SCALPER_CONFIG)
        self.access_token = None
        self.streamer = None
        self.target_ce = {'key': None, 'symbol': None}
        self.target_pe = {'key': None, 'symbol': None}
        self.is_running = False
        
        # Threading
        self.depth_thread = None
        
    def initialize(self):
        print("🔐 [INIT] Authenticating...")
        self.access_token = authentication.get_access_token()
        if not self.access_token:
            logger.error("Failed to get access token")
            sys.exit(1)
            
        print("📊 [INIT] Selecting Strike...")
        self.select_strike()
        
        if not self.target_ce['key'] or not self.target_pe['key']:
            logger.error("Failed to select target strikes (CE or PE missing)")
            sys.exit(1)
            
        print(f"🎯 [INIT] Targets: CE={self.target_ce['symbol']} | PE={self.target_pe['symbol']}")
        
        # Initialize Streamer
        self.streamer = UpstoxStreamer(self.access_token)
        self.streamer.connect_market_data([self.target_ce['key'], self.target_pe['key']], mode="ltpc")
        
        # Wait for connection
        print("⏳ [INIT] Waiting for WebSocket connection...")
        for _ in range(5):
            time.sleep(1)
            if self.streamer.market_data_connected:
                print("✅ [INIT] WebSocket connection confirmed")
                break
        else:
             print("⚠️ [INIT] WebSocket not confirmed within 5s")
        
        # NOTE: WE DO NOT START STREAMER THREAD HERE AS IT RUNS IN BACKGROUND AUTOMATICALLY UPON CONNECT? 
        # UpstoxStreamer usually needs a blocking call or we run our own loop.
        # We will run our loop.
        
    def select_strike(self):
        """
        Dynamically select strike based on Config (e.g. ATM + Offset)
        """
        index_symbol = self.config['index_symbol']
        expiry = option_chain.get_nearest_expiry(self.access_token, index_symbol)
        
        if not expiry:
            logger.error("Could not find expiry")
            return

        df_chain = option_chain.get_option_chain_dataframe(self.access_token, index_symbol, expiry)
        if df_chain is None or df_chain.empty:
            logger.error("Could not fetch option chain")
            return
            
        atm_strike = option_chain.get_atm_strike_from_chain(df_chain)
        if not atm_strike:
            return
            
        ce_target_strike = atm_strike + self.config['option_strike_offset']
        pe_target_strike = atm_strike - self.config['option_strike_offset']
        
        # Setup CE
        ce_row = df_chain[df_chain['strike_price'] == ce_target_strike]
        if not ce_row.empty:
            self.target_ce['key'] = ce_row.iloc[0]['ce_key']
            self.target_ce['symbol'] = f"NIFTY {expiry} {ce_target_strike} CE"
            
        # Setup PE
        pe_row = df_chain[df_chain['strike_price'] == pe_target_strike]
        if not pe_row.empty:
            self.target_pe['key'] = pe_row.iloc[0]['pe_key']
            self.target_pe['symbol'] = f"NIFTY {expiry} {pe_target_strike} PE"

    def run(self):
        self.initialize()
        self.is_running = True
        
        # Start Depth Polling Thread
        self.depth_thread = threading.Thread(target=self._depth_polling_loop)
        self.depth_thread.daemon = True
        self.depth_thread.start()
        
        print("🚀 [RUN] Strategy Started. Press Ctrl+C to stop.")
        logger.info("Waiting for signals...")
        
        heartbeat_counter = 0
        try:
            while self.is_running:
                # 0. Global Kill Switch Check
                if os.path.exists("c:/algo/upstox/.STOP_TRADING"):
                    logger.info("🛑 Global Kill Switch Detected (.STOP_TRADING). Stopping Strategy.")
                    self.stop("Portfolio Manager Kill Switch")
                    break

                # Main Loop handles Signal Check & Trade Management based on latest state
                
                # Get latest LTP from Streamer (for currently selected trade, or both if monitoring)
                # For scalping, once we enter, we only care about that contract's LTP
                current_active_key = self.active_position['key'] if self.active_position else None
                
                # HEARTBEAT & MONITORING
                heartbeat_counter += 1
                if heartbeat_counter >= 100:
                    with self.lock:
                        logger.info(f"💓 [HB] {self.target_ce['symbol']} Imb: {self.ce_stats['imbalance']:.2f} | {self.target_pe['symbol']} Imb: {self.pe_stats['imbalance']:.2f}")
                    heartbeat_counter = 0

                if current_active_key:
                    # WE ARE IN A TRADE
                    ltp_data = self.streamer.get_latest_data(current_active_key)
                    if ltp_data:
                        current_ltp = ltp_data.get('ltp', 0)
                        timestamp = datetime.now()
                        
                        # Update Momentum (Internal state tracking)
                        side = "CE" if current_active_key == self.target_ce['key'] else "PE"
                        self.check_momentum(current_ltp, timestamp, side)
                        
                        # Check Exits
                        should_exit, reason = self.check_exit_conditions(current_ltp, timestamp)
                        if should_exit:
                            self.execute_exit(current_ltp, reason)
                else:
                    # WAITING FOR SIGNAL (Monitor both)
                    timestamp = datetime.now()
                    
                    # Update CE Momentum
                    ce_ltp_data = self.streamer.get_latest_data(self.target_ce['key'])
                    ce_mom = 0.0
                    if ce_ltp_data:
                        ce_mom = self.check_momentum(ce_ltp_data.get('ltp', 0), timestamp, "CE")
                        
                    # Update PE Momentum
                    pe_ltp_data = self.streamer.get_latest_data(self.target_pe['key'])
                    pe_mom = 0.0
                    if pe_ltp_data:
                        pe_mom = self.check_momentum(pe_ltp_data.get('ltp', 0), timestamp, "PE")
                        
                    with self.lock:
                        # Check CE Signal (Depth + Momentum)
                        # CE Signal in SHORT mode = SELL CE (Bearish)
                        if self.check_entry_signal(self.ce_stats['imbalance'], ce_mom, self.ce_stats['has_buy_wall'], "CE"):
                            if ce_ltp_data:
                                self.execute_entry(ce_ltp_data.get('ltp', 0), "CE")
                                
                        # Check PE Signal (Depth + Momentum)
                        # PE Signal in SHORT mode = SELL PE (Bullish)
                        elif self.check_entry_signal(self.pe_stats['imbalance'], pe_mom, self.pe_stats['has_buy_wall'], "PE"):
                            if pe_ltp_data:
                                self.execute_entry(pe_ltp_data.get('ltp', 0), "PE")
                        
                time.sleep(0.05) # Fast loop for scalping
                
        except KeyboardInterrupt:
            print("\n🛑 Stopping Strategy...")
            self.stop()
            
    def _depth_polling_loop(self):
        """
        Polls market depth periodically and updates shared state for both CE and PE.
        """
        while self.is_running:
            try:
                # Fetch Quotes for both in one call
                keys = [self.target_ce['key'], self.target_pe['key']]
                quote_data = market_quotes.get_multiple_market_quotes(self.access_token, keys)
                
                if quote_data:
                    for key in keys:
                        data = quote_data.get(key, {})
                        depth = data.get('depth', {})
                        side = "CE" if key == self.target_ce['key'] else "PE"
                        
                        imbalance, has_buy_wall, has_sell_wall = self.analyze_market_depth(depth)
                        self.update_market_stats(key, imbalance, has_buy_wall, has_sell_wall, side)
                                 
            except Exception as e:
                logger.error(f"Depth Polling Error: {e}")
                
            time.sleep(self.config['polling_interval'])

    def execute_entry(self, price, side):
        target = self.target_ce if side == "CE" else self.target_pe
        mode = self.config.get('execution_mode', 'LONG')
        # Place real order if not dry run
        if self.config['dry_run']:
            logger.info(f"⚡ [EXEC] MOCK {mode} {target['symbol']} @ {price}")
        
        with self.lock:
            self.register_entry(price, datetime.now(), self.config['quantity_lots'] * self.config['lot_size'])
            self.active_position['key'] = target['key']
            self.active_position['symbol'] = target['symbol']

    def execute_exit(self, price, reason):
        target_symbol = self.active_position.get('symbol', 'Unknown')
        mode = "COVER" if self.config.get('execution_mode', 'LONG') == 'SHORT' else "SELL"
        # In real live trading, place Kotak Order here
        if self.config['dry_run']:
            logger.info(f"⚡ [EXEC] MOCK {mode} {target_symbol} @ {price} ({reason})")
        
        self.register_exit(price, datetime.now(), reason)

    def stop(self, reason="Kill Switch"):
        self.is_running = False
        
        # Immediate Exit if Position Active
        if self.active_position and self.active_position.get('key'):
            logger.info(f"🚨 Killing Active Position on Stop: {self.active_position['symbol']}")
            ltp_data = self.streamer.get_latest_data(self.active_position['key']) if self.streamer else None
            price = ltp_data.get('ltp', 0) if ltp_data else 0
            self.execute_exit(price, reason)

        if self.streamer:
            self.streamer.disconnect_all()

if __name__ == "__main__":
    strategy = OptionScalperLive()
    strategy.run()

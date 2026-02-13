"""
Supertrend Multi-Timeframe Strategy - Live Execution

[STRATEGY LOGIC]
1. CONCEPT:
   - Aligns the Index Trend (Nifty) with the Option Premium Trend.
   - We sell options only when the underlying is favorable AND the option premium itself is technically weak (Downtrend).

2. TIMEFRAMES:
   - Nifty Index: 3-minute (Determines Bias).
   - Option Chart: 3-minute (Determines Entry/Exit).

3. ENTRY (Directional Short Option Selling):
   - Step A: Check Nifty Index Supertrend (10, 2).
     - If Nifty Bullish (Green) -> Bias: Sell PE.
     - If Nifty Bearish (Red)   -> Bias: Sell CE.
   - Step B: Select Strike.
     - Find Strike with premium closest to `target_premium` (default 60).
   - Step C: Confirm Option Trend.
     - Verify Supertrend on the OPTION CHART itself.
     - Condition: Option Supertrend must be Bearish (-1) i.e., Price < Supertrend.
     - *Logic*: We only short the option if its premium is already in a downtrend.

4. EXIT Conditions:
   - Option Trend Reversal: Exit if Option Price > Option Supertrend (Trend turns Bullish).
   - Price Breach: Immediate exit if LTP crosses above Option Supertrend level.
   - Nifty Reversal: Exit if Nifty Trend flips against the trade (e.g., Short CE but Nifty turns Bullish).
"""

import os
import sys
import time
import logging
import threading
from datetime import datetime

# Adjust Paths
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from lib.api.streaming import UpstoxStreamer
from lib.core.authentication import get_access_token
from lib.api.market_data import download_nse_market_data, get_market_quotes
from lib.api.historical import get_intraday_data_v3, get_historical_data_v3
from lib.utils.instrument_utils import get_lot_size
from datetime import datetime, timedelta
import pandas as pd
from lib.utils.tick_aggregator import TickAggregator  # New
from kotak_api.lib.broker import BrokerClient
from kotak_api.lib.order_manager import OrderManager

from strategies.directional.supertrend_multitimeframe.core import SupertrendStrategyCore
from strategies.directional.supertrend_multitimeframe.config import CONFIG

# Logger settings
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', force=True)
logger = logging.getLogger("STMultiTF_Live")

class SupertrendMultiTimeframeLive:
    def __init__(self, upstox_token: str, config: dict):
        self.config = config
        self.upstox_token = upstox_token
        self.core = SupertrendStrategyCore(config)
        
        # Brokers
        self.kotak_broker = BrokerClient()
        self.kotak_client = None
        self.order_mgr = None
        self.streamer = None
        
        # State
        self.running = False
        self.ltp_cache = {}
        self.nse_data = None
        self.hard_stop_breach_time = None  # Track sustained hard stop breaches
        
        # Aggregators
        nifty_unit, nifty_val = self.core._parse_interval(self.config['nifty_interval'])
        self.nifty_aggregator = TickAggregator(nifty_val)
        
        opt_unit, opt_val = self.core._parse_interval(self.config['option_interval'])
        self.option_aggregator = TickAggregator(opt_val)
        
    def initialize(self):
        logger.info("🚀 Initializing Supertrend Multi-Timeframe Strategy...")
        
        # 1. Kotak Auth
        self.kotak_client = self.kotak_broker.authenticate()
        if not self.kotak_client:
            logger.error("❌ Kotak Auth Failed")
            return False
        self.kotak_broker.load_master_data()
        self.order_mgr = OrderManager(self.kotak_client, dry_run=self.config['dry_run'])
        
        # 3. Upstox NSE Master (for Lot Size)
        logger.info("📡 Downloading Upstox NSE master data...")
        self.nse_data = download_nse_market_data()
        
        # 4. Initial Nifty Warmup (History + Intraday)
        logger.info("🔥 Warming up Nifty 3m Aggregator with 5 days history...")
        nifty_unit, nifty_val = self.core._parse_interval(self.config['nifty_interval'])
        
        # Fetch History (Last 5 days)
        to_date = datetime.now()
        from_date = to_date - timedelta(days=5)
        hist_data = get_historical_data_v3(
            self.upstox_token, 
            self.core.nifty_token, 
            nifty_unit, 
            nifty_val, 
            from_date.strftime('%Y-%m-%d'), 
            to_date.strftime('%Y-%m-%d')
        )
        
        # Fetch Intraday
        intra_data = get_intraday_data_v3(self.upstox_token, self.core.nifty_token, nifty_unit, nifty_val)
        
        # Combine
        full_df = pd.DataFrame()
        if hist_data:
            full_df = pd.DataFrame(hist_data)
            
        if intra_data:
            intra_df = pd.DataFrame(intra_data)
            if not full_df.empty:
                full_df = pd.concat([full_df, intra_df]).drop_duplicates(subset=['timestamp']).sort_values('timestamp')
            else:
                full_df = intra_df
                
        if not full_df.empty:
             self.nifty_aggregator.update_historical(self.core.nifty_token, full_df)
             logger.info(f"✅ Seeded {len(full_df)} candles for Nifty")
        
        # 5. Upstox WebSocket (Optional)
        if self.config.get('use_websocket', True):
            self.streamer = UpstoxStreamer(self.upstox_token)
            self.streamer.connect_market_data([self.core.nifty_token], mode="ltpc", on_message=self.on_market_data)
            
            # Wait for connection to stabilize
            logger.info("⏳ Waiting for WebSocket connection...")
            for _ in range(5):
                time.sleep(1)
                if self.streamer.market_data_connected:
                    logger.info("✅ WebSocket connection confirmed")
                    break
            else:
                 logger.warning("⚠️ WebSocket not confirmed within 5s, proceeding with REST fallback enabled...")
        else:
            logger.info("ℹ️ WebSocket disabled via config. Using REST-only mode.")
        
        return True

    def on_market_data(self, data):
        """Handle real-time ticks."""
        inst_key = data.get('instrument_key')
        ltp = data.get('ltp')
        if not inst_key or not ltp: return
        
        self.ltp_cache[inst_key] = ltp
        
        # 1. Update Aggregators
        if inst_key == self.core.nifty_token:
            self.nifty_aggregator.add_tick(inst_key, datetime.now(), ltp)
        elif self.core.active_position and inst_key == self.core.active_position['token']:
            self.option_aggregator.add_tick(inst_key, datetime.now(), ltp)

    def resolve_kotak_symbol(self, expiry_data, strike, option_type):
        """
        Robust Symbol Resolution via Kotak Master Data Search.
        We search for underlying name, strike, and option type.
        """
        try:
            if self.kotak_broker.master_df is None:
                logger.error("❌ Kotak Master Data not loaded.")
                return None

            underlying = self.config.get('underlying', 'NIFTY')
            df = self.kotak_broker.master_df
            
            # Simple pattern match for pScripRefKey containing DDMMMYY format if possible
            # But more robust is filtering by name and strike
            # Upstox Expiry can vary in format, let's use the Date if it's there
            
            # 1. Broad filter
            matches = df[
                (df['pSymbolName'] == underlying) & 
                (df['pOptionType'] == option_type)
            ]
            
            if matches.empty:
                logger.error(f"❌ No {underlying} {option_type} found in master data.")
                return None
                
            # 2. Strike Filter (Handle float comparison or partial string)
            # Kotak pScripRefKey usually contains the strike as int or .00
            # Example: NIFTY30JAN2625000.00CE
            strike_str = str(int(strike))
            matches = matches[matches['pScripRefKey'].str.contains(strike_str)]
            
            if matches.empty:
                logger.error(f"❌ No {underlying} {option_type} strike {strike} found.")
                return None

            # 3. Expiry Filter
            # Convert Upstox expiry to DDMMMYY pattern for ScripRefKey matching
            dt = None
            if isinstance(expiry_data, str):
                dt = datetime.strptime(expiry_data, "%Y-%m-%d")
            elif hasattr(expiry_data, 'strftime'):
                dt = expiry_data
            
            if dt:
                pattern = dt.strftime("%d%b%y").upper() # 30JAN26
                final_matches = matches[matches['pScripRefKey'].str.contains(pattern)]
                if not final_matches.empty:
                    # Prefer pTrdSymbol which is used for placement
                    symbol = final_matches.iloc[0]['pTrdSymbol']
                    logger.info(f"✅ Resolved Kotak Symbol: {symbol} (via pScripRefKey: {final_matches.iloc[0]['pScripRefKey']})")
                    return symbol

            # Fallback: Just return the first match if only 1 exists
            if len(matches) == 1:
                symbol = matches.iloc[0]['pTrdSymbol']
                logger.warning(f"⚠️ Partial match (Expiry fuzzy) resolved: {symbol}")
                return symbol
                
            logger.error(f"❌ No unique symbol found for {underlying} {option_type} {strike} {expiry_data}")
            return None
                
        except Exception as e:
            logger.error(f"Symbol Resolution Error: {e}")
            return None

    def get_lot_size(self, symbol):
        """Fetch lot size from Master Data or fallback."""
        try:
            # Try to fetch from broker master
            # This requires a helper in BrokerClient or direct df access
            if self.kotak_broker.master_df is not None:
                row = self.kotak_broker.master_df[self.kotak_broker.master_df['pSymbol'] == symbol]
                if not row.empty:
                    return int(row.iloc[0]['lLotSize'])
        except Exception:
            pass
        return 25 # Fallback for Nifty

    def execute_entry(self, signal_type, token, strike, expiry, entry_price):
        """Execute Entry Order."""
        # Resolve Symbol
        symbol = self.resolve_kotak_symbol(expiry, strike, signal_type)
        if not symbol:
            logger.error("❌ Could not resolve Kotak Symbol. Entry Aborted.")
            return

        logger.info(f"⚡ EXECUTING ENTRY: {signal_type} on {symbol}")
        
        lots = self.config['trading_lots']
        lot_size = get_lot_size(token, self.nse_data)
        
        order_id = self.order_mgr.place_order(
            symbol=symbol,
            qty=lots * lot_size,
            transaction_type="S", # Short Selling
            product=self.config['product_type'],
            tag="ST_MultiTF_Entry"
        )
        
        if order_id:
            logger.info(f"✅ Entry Order Placed. ID: {order_id}")
            
            # Fetch Actual Execution Price
            time.sleep(1) # Wait for fill
            exec_price = self.order_mgr.get_execution_price(order_id)
            
            if exec_price > 0:
                slippage = exec_price - entry_price
                logger.info(f"📊 Entry Executed: {exec_price:.2f} (Signal: {entry_price:.2f}, Slippage: {slippage:+.2f})")
                final_price = exec_price
            else:
                logger.error(f"❌ CRITICAL: Could not retrieve execution price for order {order_id}. Aborting entry.")
                # Attempt to exit the position immediately as we can't track P&L accurately
                logger.error("⚠️ Attempting emergency exit of untracked position...")
                self.order_mgr.place_order(
                    symbol=symbol,
                    qty=lots * lot_size,
                    transaction_type="B",
                    product=self.config['product_type'],
                    tag="Emergency_Exit_No_ExecPrice"
                )
                return
            
            self.core.active_position = {
                'type': signal_type,
                'token': token,
                'symbol': symbol,
                'qty': lots * lot_size,
                'entry_price': final_price
            }
            
            # 1. Seed Option Aggregator with history (REST Warmup)
            logger.info(f"🔥 Warming up Option {symbol} Aggregator with history...")
            opt_unit, opt_val = self.core._parse_interval(self.config['option_interval'])
            
            # Fetch History + Intraday for Option
            opt_to_date = datetime.now()
            opt_from_date = opt_to_date - timedelta(days=5)
            
            opt_hist = get_historical_data_v3(self.upstox_token, token, opt_unit, opt_val, opt_from_date.strftime('%Y-%m-%d'), opt_to_date.strftime('%Y-%m-%d'))
            opt_intra = get_intraday_data_v3(self.upstox_token, token, opt_unit, opt_val)
            
            opt_df = pd.DataFrame()
            if opt_hist: opt_df = pd.DataFrame(opt_hist)
            if opt_intra: 
                idf = pd.DataFrame(opt_intra)
                opt_df = pd.concat([opt_df, idf]).drop_duplicates(subset=['timestamp']).sort_values('timestamp') if not opt_df.empty else idf
            
            if not opt_df.empty:
                 self.option_aggregator.update_historical(token, opt_df)

            # 2. Subscribe to new Option Token
            try:
                if self.streamer and self.streamer.market_data_connected:
                    self.streamer.subscribe_market_data([token], mode="ltpc")
                else:
                    logger.warning(f"⚠️ Market Data Stream not connected. Skipping subscription for {token}. Will rely on REST fallback.")
            except Exception as e:
                logger.error(f"⚠️ WebSocket Subscription Error: {e}. Continuing strategy via REST.")
            
        else:
            logger.error("❌ Order Rejected or Failed.")

    def execute_exit(self, reason):
        """Execute Exit Order with verification."""
        if not self.core.active_position: return
        
        symbol = self.core.active_position['symbol']
        qty = self.core.active_position['qty']
        
        logger.info(f"🚪 EXECUTING EXIT: {reason} for {symbol}")
        
        order_id = self.order_mgr.place_order(
            symbol=symbol,
            qty=qty,
            transaction_type="B", # Buy to Cover
            product=self.config['product_type'],
            tag=f"ST_MultiTF_Exit_{reason}"
        )
        
        if order_id:
            logger.info(f"✅ Exit Order Placed: {order_id}")
            
            # Verify execution price and calculate realized P&L
            time.sleep(1)
            exec_price = self.order_mgr.get_execution_price(order_id)
            
            if exec_price > 0:
                # Calculate realized P&L using ACTUAL prices (Short position: Entry - Exit)
                entry_price = self.core.active_position['entry_price']
                qty = self.core.active_position['qty']
                realized_pnl = (entry_price - exec_price) * qty
                
                logger.info(f"📊 Exit Executed: {exec_price:.2f} (Entry: {entry_price:.2f}) | Realized P&L: ₹{realized_pnl:+.2f}")
            else:
                logger.error(f"❌ WARNING: Could not retrieve exit price for order {order_id}")
            
            # Record Exit for Cooldown
            self.core.record_exit(self.core.active_position['type'])
            
            # Clear aggregator for this token
            self.option_aggregator.clear(self.core.active_position['token'])
            
            # Reset hard stop timer to prevent carryover to next trade
            self.hard_stop_breach_time = None
            
            self.core.active_position = None
        else:
            logger.error(f"❌ Exit Order Failed for {symbol}")

    def exit_all(self):
        """Mandatory Graceful Shutdown: Close all positions and clear state."""
        logger.info("🛑 [CORE] Initiating Graceful Shutdown...")
        if self.core.active_position:
            self.execute_exit("GracefulShutdown")
        
        # Reset core state
        self.core.active_position = None
        logger.info("✅ Shutdown complete")

    def run(self):
        if not self.initialize(): return
        self.running = True
        logger.info("📡 Strategy Running... Press Ctrl+C to stop.")
        
        last_check = 0
        try:
            while self.running:
                # 0. Global Kill Switch Check
                if os.path.exists("c:/algo/upstox/.STOP_TRADING"):
                    logger.info("🛑 Global Kill Switch Detected (.STOP_TRADING). Stopping Strategy.")
                    self.exit_all()
                    self.running = False
                    break

                now = time.time()
                
                # Check Logic Every 5 Seconds
                if now - last_check >= 5:
                    last_check = now
                    
                    # 1. Update Nifty ST via Aggregated Data
                    nifty_df = self.nifty_aggregator.get_dataframe(self.core.nifty_token)
                    
                    # Check for Stale Nifty Data
                    is_nifty_stale = False
                    if nifty_df.empty:
                        is_nifty_stale = True
                    else:
                        # Check last candle timestamp
                        last_ts = pd.to_datetime(nifty_df.iloc[-1]['timestamp'])
                        if now - last_ts.timestamp() > 300: # 5 minutes (for 3 min interval)
                             # logger.warning(f"⚠️ Nifty Data appears stale ({last_ts}). Fetching via REST...")
                             is_nifty_stale = True

                    if is_nifty_stale or not self.streamer or not self.streamer.market_data_connected:
                         # logger.debug("⚠️ Fetching Nifty Data via REST...")
                         unit, val = self.core._parse_interval(self.config['nifty_interval'])
                         fresh_nifty = get_intraday_data_v3(self.upstox_token, self.core.nifty_token, unit, val)
                         if fresh_nifty:
                             ndf = pd.DataFrame(fresh_nifty)
                             self.nifty_aggregator.update_historical(self.core.nifty_token, ndf)
                             nifty_df = self.nifty_aggregator.get_dataframe(self.core.nifty_token)

                    self.core.update_nifty_supertrend(self.upstox_token, df=nifty_df)
                    
                    # 2. Check Active Position
                    if self.core.active_position:
                        token = self.core.active_position['token']
                        
                        # Use aggregated data for option ST
                        opt_df = self.option_aggregator.get_dataframe(token)
                        
                        # 2.1 Check for Stale Data / WebSocket Disconnect
                        is_stale = False
                        if opt_df.empty:
                            is_stale = True
                        else:
                            last_ts = pd.to_datetime(opt_df.iloc[-1]['timestamp'])
                            # If last candle is older than 2x interval, consider stale
                            # But if market is closed/inactive, this might trigger often. 
                            # Better: Check if streamer is connected for this token
                            if not self.streamer or not self.streamer.market_data_connected or token not in self.ltp_cache:
                                is_stale = True
                                
                        if is_stale:
                            # logger.debug(f"⚠️ Option Data Stale for {token}. Fetching via REST...")
                            unit, val = self.core._parse_interval(self.config['option_interval'])
                            
                            # Only fetch latest if enough time passed since last REST fetch to avoid rate limit?
                            # For now, just fetch.
                            fresh_data = get_intraday_data_v3(self.upstox_token, token, unit, val)
                            if fresh_data:
                                fdf = pd.DataFrame(fresh_data)
                                self.option_aggregator.update_historical(token, fdf)
                                opt_df = self.option_aggregator.get_dataframe(token)
                            
                            # Fetch LTP explicitly for real-time check
                            try:
                                quotes = get_market_quotes(self.upstox_token, [token])
                                if quotes and token in quotes:
                                     self.ltp_cache[token] = quotes[token].get('last_price', 0.0)
                            except Exception as e:
                                logger.error(f"Error fetching quote: {e}")
                        
                        trend, st_val, candle_close, trend_completed = self.core.calculate_option_supertrend(self.upstox_token, token, df=opt_df)
                        
                        # Use cached LTP if available (from WS or REST), else Candle Close
                        current_price = self.ltp_cache.get(token, candle_close)
                        if current_price == 0: current_price = candle_close

                        # --- NEW: PnL and Trade Logging ---
                        entry_price = self.core.active_position.get('entry_price', 0.0)
                        qty = self.core.active_position.get('qty', 0)
                        
                        # Unrealized PnL (Short Position: Entry - Current) * Qty
                        pnl = (entry_price - current_price) * qty
                        
                        # Total Premium Collected (for % based calculations)
                        entry_premium_total = entry_price * qty
                        
                        # Apply Hardened Profit Locking (Percentage-based)
                        stop_strat, reason = self.core.check_profit_goals(pnl, entry_premium_total)
                        if stop_strat:
                            logger.info(f"🛑 [CORE] HARDENED EXIT TRIGGERED: {reason}")
                            self.execute_exit(f"ProfitLock_{reason}")
                            continue

                        logger.info(f"📊 {self.core.active_position['symbol']} | Entry: {entry_price:.2f} | CMP: {current_price:.2f} | SL: {st_val:.2f} | PnL: {pnl:.2f} | Lock: {self.core.locked_profit:.0f}")
                        # ----------------------------------

                        # LOGIC: Exit if Option Price > ST (Trend turns Bullish/Up)
                        exit_triggered = False
                        exit_reason = ""
                        
                        # 1. Trend Reversal (Primary Exit)
                        if self.config.get('exit_on_candle_close', False):
                            # Simplified "Closing Basis" Logic:
                            # 1. Hard Stop: If Price breaches ST + Buffer for 30+ seconds -> EXIT (Filters wicks)
                            # 2. Tech Stop: If ST flips to 1 (Bullish) -> This normally happens on close.
                            #    If we want to be super strict about "Close", we need to check if the Flip happened on a COMPLETED candle.
                            
                            st_buffer_pct = 0.01 # 1% safety buffer
                            hard_stop_price = st_val * (1 + st_buffer_pct)
                            
                            # Time-based hard stop confirmation (filters wicks)
                            if current_price > hard_stop_price:
                                if self.hard_stop_breach_time is None:
                                    # First breach - start timer
                                    self.hard_stop_breach_time = time.time()
                                    logger.warning(f"⚠️ Hard Stop Breach Detected: {current_price:.2f} > {hard_stop_price:.2f}. Monitoring...")
                                else:
                                    # Check if breach has been sustained
                                    breach_duration = time.time() - self.hard_stop_breach_time
                                    required_duration = self.config.get('hard_stop_breach_duration_sec', 30)
                                    if breach_duration >= required_duration:
                                        logger.info(f"🛑 CATASTROPHIC STOP: Sustained breach for {breach_duration:.0f}s ({current_price} > {hard_stop_price:.2f})")
                                        exit_triggered = True
                                        exit_reason = "HardStop"
                                        self.hard_stop_breach_time = None  # Reset
                                    else:
                                        logger.debug(f"⏳ Hard Stop breach ongoing: {breach_duration:.0f}s / {required_duration}s")
                            else:
                                # Price dropped back below hard stop - reset timer
                                if self.hard_stop_breach_time is not None:
                                    logger.info(f"✅ Hard Stop breach cleared. Price back to {current_price:.2f}")
                                    self.hard_stop_breach_time = None
                            
                            # Candle close confirmation for trend flip
                            if not exit_triggered and trend_completed == 1:
                                # Logic: Trust Trend Flip ONLY if it happened on a COMPLETED candle.
                                # IMPORTANT: If current 'trend' is -1 (Bearish), it means the price HAS droppped back below ST.
                                # So even if the 'previous' candle ended Bullish, the 'current' candle is Bearish (Breakout).
                                # We should NOT exit if we just entered on this breakout.
                                
                                if trend == -1:
                                     # We are largely safe, current candle is Bearish. The 'trend_completed' is lagging.
                                     pass
                                else:
                                    logger.info(f"🛑 TREND FLIP SIGNAL: Option Trend turned Bullish on COMPLETED Candle (Price > ST)")
                                    exit_triggered = True
                                    exit_reason = "TrendReversal"
                                    self.hard_stop_breach_time = None  # Reset
                        
                        else:
                            # Standard Instant Exit
                            if trend == 1:
                                logger.info(f"🛑 EXIT SIGNAL: Option Trend turned Bullish (Price {current_price} > ST {st_val})")
                                exit_triggered = True
                                exit_reason = "TrendReversal"
                            elif current_price > st_val:
                                logger.info(f"🛑 EXIT SIGNAL: Price Breached ST (Price {current_price} > ST {st_val})")
                                exit_triggered = True
                                exit_reason = "PriceBreach"
                        

                            
                        if exit_triggered:
                            self.execute_exit(exit_reason)
                            if not self.core.active_position: continue
                            
                        # Nifty Reversal Check (Optional but recommended)
                        if self.core.active_position['type'] == 'CE' and self.core.nifty_trend == 1:
                             logger.info("🛑 EXIT SIGNAL: Nifty Trend Reversed to BULLISH")
                             self.execute_exit("NiftyReversal")
                        elif self.core.active_position['type'] == 'PE' and self.core.nifty_trend == -1:
                             logger.info("🛑 EXIT SIGNAL: Nifty Trend Reversed to BEARISH")
                             self.execute_exit("NiftyReversal")
                             
                    # 3. Check for New Entry
                    else:
                        # Safety: Don't enter if we already hit a major drawdown this session
                        # (Note: In future versions, this should check cumulative closed P&L)
                        if self.core.locked_profit > 0 and self.core.max_profit_reached >= self.config.get('profit_locking', {}).get('lock_threshold_abs', 2000):
                             # This is a bit complex without cumulative PnL, 
                             # but let's at least avoid entries after a stop out.
                             pass

                        # Pass nifty_df for immediate update check
                        sig_type, token, strike, expiry_date, entry_price = self.core.check_signals(self.upstox_token, nifty_df=nifty_df)
                        if sig_type:
                            self.execute_entry(sig_type, token, strike, expiry_date, entry_price)
                            
                time.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("⚠️ Interrupted. Exiting...")
            self.exit_all()
            sys.exit(0)

if __name__ == "__main__":
    token = get_access_token()
    if not token: sys.exit(1)
    
    strat = SupertrendMultiTimeframeLive(token, CONFIG)
    strat.run()

"""
Futures VWAP Supertrend Strategy - Live implementation

[STRATEGY LOGIC]
1. ENTRY (Directional Short Option Selling - Configurable):
   - Check Timing: Tick-by-Tick (Default) OR Candle Close (Configurable via `enter_on_candle_close`).
   - Trend Follow: Trade matches Supertrend direction AND VWAP relation.
     - Call Sell (Bearish): Futures Price < VWAP AND Supertrend == -1 (Red).
     - Put Sell (Bullish): Futures Price > VWAP AND Supertrend == 1 (Green).
   - Filter 1: Price must be within `max_vwap_distance_pct` (0.2%) of VWAP to avoid chasing.
   - Filter 2: OTM Option Selection requires Short Buildup signal (Price Decrease >= 20% + OI Increase >= 20%).
   - Filter 3: Minimum 100 points OTM from ATM.

2. EXIT (Trend Reversal & TSL):
   - Reversal Check (Candle Close):
     - Exit CALLS if Futures Price > VWAP OR Supertrend turns Bullish.
     - Exit PUTS if Futures Price < VWAP OR Supertrend turns Bearish.
   - Trailing Stop Loss (Tick-by-Tick):
     - Logic: Logs lowest premium seen (L) since entry.
     - Trigger: Current Price > L * (1 + TSL_Pct).
     - Dynamic TSL: Base 10% TSL tightens to 5% after the first pyramid level.
   - Time Exit: Hard stop at 15:15.

3. PYRAMIDING:
   - Condition: Add 1 lot if current position profit >= 10%.
   - Limit: Max 2 levels.
"""

import sys
import os
import logging
import pandas as pd
import time
import numpy as np
import threading
from datetime import datetime, timedelta, time as dt_time
from typing import Optional

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from strategies.directional.futures_vwap_supertrend.strategy_core import FuturesVWAPSupertrendCore, Position
from strategies.directional.futures_vwap_supertrend.config import CONFIG

from lib.api.historical import get_historical_data
from lib.api.streaming import UpstoxStreamer
from lib.utils.instrument_utils import get_future_instrument_key, get_option_instrument_key, get_lot_size
from lib.api.market_data import download_nse_market_data, get_market_quote_for_instrument, get_option_chain_atm
from lib.utils.expiry_cache import get_expiry_for_strategy
from lib.oi_analysis.cumulative_oi_analysis import CumulativeOIAnalyzer
from lib.utils.indicators import calculate_vwap, calculate_supertrend
from lib.utils.vwap_calculator import VWAPCalculator  # NEW: Tick-level VWAP

from kotak_api.lib.broker import BrokerClient
from kotak_api.lib.order_manager import OrderManager
from kotak_api.lib.trading_utils import get_strike_token

# Force UTF-8 for Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

logger = logging.getLogger("VWAPSupertrendLive")

class FuturesVWAPSupertrendLive(FuturesVWAPSupertrendCore):
    def __init__(self, upstox_token: str, config: dict):
        super().__init__(config)
        self.upstox_token = upstox_token
        self.nse_data = None
        self.futures_key = None
        self.streamer = None
        self.last_candle_check = None
        self.last_pcr = 0.0
        self.ltp_cache = {}
        
        self.kotak_broker = BrokerClient()
        self.kotak_client = None
        self.order_mgr = None
        self.oi_analyzer = CumulativeOIAnalyzer(upstox_token)
        self.fixed_oi_strikes = []
        self.strike_step = 50
        self.last_entry_log_time = 0
        
        # Performance Caching
        self.cached_expiry = None
        self.cached_chain = pd.DataFrame()
        self.last_chain_fetch = 0
        
        # Tick-level VWAP Calculator (WebSocket-based, zero API calls)
        self.vwap_calculator = VWAPCalculator()

    def log(self, msg, tag="CORE"):
        timestamp = datetime.now().strftime('%H:%M:%S')
        emoji = "🎯" if "ENTRY" in msg else "🚪" if "EXIT" in msg else "📊" if "Fut:" in msg else "✅" if "Ready" in msg else "💓"
        print(f"[{timestamp}] {emoji} [{tag}] {msg}")

    def initialize(self):
        self.log("📊 [UPSTOX] Initializing Strategy and downloading NSE data...", "UPSTOX")
        self.nse_data = download_nse_market_data()
        if self.nse_data is None:
            self.log("❌ [UPSTOX] Failed to download NSE data", "UPSTOX")
            return False
            
        self.futures_key = get_future_instrument_key(self.config['underlying'], self.nse_data)
        if not self.futures_key:
            self.log(f"❌ [UPSTOX] Failed to find futures key for {self.config['underlying']}", "UPSTOX")
            return False
            
        # Update underlying key for analyzer
        if self.config['underlying'] == 'NIFTY':
            self.oi_analyzer.underlying_key = "NSE_INDEX|Nifty 50"
        elif self.config['underlying'] == 'BANKNIFTY':
            self.oi_analyzer.underlying_key = "NSE_INDEX|Nifty Bank"
        elif self.config['underlying'] == 'FINNIFTY':
            self.oi_analyzer.underlying_key = "NSE_INDEX|Nifty Fin Service"
            
        self.log("🔐 [KOTAK] Authenticating with Kotak Neo...", "KOTAK")
        self.kotak_client = self.kotak_broker.authenticate()
        if not self.kotak_client:
            self.log("❌ [KOTAK] Authentication failed", "KOTAK")
            return False
            
        self.kotak_broker.load_master_data()
        self.order_mgr = OrderManager(self.kotak_client, dry_run=self.config.get('dry_run', False))
        
        self.log(f"📡 [UPSTOX] Starting background initialization for {self.futures_key}", "UPSTOX")
        threading.Thread(target=self._initial_setup_task, daemon=True).start()
        
        self.log(f"✅ [CORE] Strategy ready (Data feed connecting in background)", "CORE")
        return True

    def _initial_setup_task(self):
        """Async initialization to prevent blocking the main loop startup"""
        try:
            # 1. Connect Streamer
            self.streamer = UpstoxStreamer(self.upstox_token)
            self.streamer.connect_market_data([self.futures_key], mode="ltpc", on_message=self.on_market_data)
            
            # Wait for connection
            logger.info("⏳ [CORE] Waiting for WebSocket connection...")
            for _ in range(5):
                time.sleep(1)
                if self.streamer.market_data_connected:
                    logger.info("✅ [CORE] WebSocket connection confirmed")
                    break
            else:
                 logger.warning("⚠️ [CORE] WebSocket not confirmed within 5s")
            
            # 2. Fetch initial quote for OI setup AND Futures Price
            quote = get_market_quote_for_instrument(self.upstox_token, self.oi_analyzer.underlying_key)
            spot = quote.get('last_price', 0) if quote else 0
            
            # 2a. Fetch Futures Price Initial Snapshot
            f_quote = get_market_quote_for_instrument(self.upstox_token, self.futures_key)
            if f_quote:
                self.futures_price = f_quote.get('last_price', 0.0)
                self.log(f"📉 [CORE] Initial Futures Price set to {self.futures_price}", "CORE")
            
            if spot > 0:
                # 3. Get Expiry and Strike Step
                self.cached_expiry = get_expiry_for_strategy(self.upstox_token, self.config['expiry_type'], self.config['underlying'])
                chain = get_option_chain_atm(self.upstox_token, self.oi_analyzer.underlying_key, self.cached_expiry, strikes_above=2, strikes_below=2)
                
                if not chain.empty:
                    strikes = sorted(chain['strike_price'].unique())
                    if len(strikes) >= 2:
                        self.strike_step = int(strikes[1] - strikes[0])
                
                # 4. Fix OI Strikes
                atm = round(spot / self.strike_step) * self.strike_step
                radius = self.config.get('oi_strikes_radius', 4)
                self.fixed_oi_strikes = [atm + (i * self.strike_step) for i in range(-radius, radius + 1)]
                self.log(f"🎯 [CORE] OI Strikes Initialized: {self.fixed_oi_strikes}", "CORE")
                
            self.log("✅ [UPSTOX] WebSocket and OI setup complete", "UPSTOX")
        except Exception as e:
            self.log(f"⚠️ [CORE] Async Initialization Warning: {e}", "CORE")

    def on_market_data(self, data):
        if isinstance(data, dict):
            key = data.get('instrument_key')
            ltp = data.get('ltp')
            if key and ltp:
                self.ltp_cache[key] = ltp
                
                # Feed tick to VWAP calculator (tick-level VWAP)
                if self.futures_key and key == self.futures_key:
                    volume = data.get('volume', 1)  # Use 1 if volume not available
                    self.vwap_calculator.add_tick(key, ltp, volume)
                    self.futures_price = ltp
                
                # Update core positions (Execution Layer)
                with self.lock:
                    self.update_position_prices(key, ltp)

    def run(self):
        if not self.initialize(): return
        
        interval = self.config['candle_interval_minutes']
        while True:
            try:
                # 0. Global Kill Switch Check
                if os.path.exists("c:/algo/upstox/.STOP_TRADING"):
                    self.log("🛑 Global Kill Switch Detected (.STOP_TRADING). Stopping Strategy.", "CORE")
                    self.execute_exit_all("Portfolio Manager Kill Switch")
                    break

                now = datetime.now()
                # 1. Market Close Check
                exit_h, exit_m = map(int, self.config['exit_time'].split(':'))
                if now.time() >= dt_time(exit_h, exit_m):
                    self.execute_exit_all("Market Close")
                    break

                # 2. Candle Processing (Background Thread)
                if self.last_candle_check is None or now >= self.last_candle_check + timedelta(minutes=interval):
                    self.last_candle_check = now.replace(second=0, microsecond=0)
                    threading.Thread(target=self.process_iteration, daemon=True).start()

                # 3. Real-time Monitoring (Always Live)
                self.check_realtime_exits()
                self.check_realtime_entries()
                
                # 4. Heartbeat Status
                status = self.get_trade_status()
                if status:
                    # Detailed Status Line
                    msg = f"Fut: {self.futures_price:.1f} | {status['symbol']}: {status['ltp']:.1f} ({status['lots']}L) | Entry: {status['entry']:.1f} | PnL: {status['pnl']:+.1f} | TSL: {status['tsl']:.1f}"
                    self.log(msg, "HEARTBEAT")
                else:
                    self.log(f"WAITING | Fut: {self.futures_price:.2f} | VWAP: {self.current_vwap:.2f} | ST: {self.current_st_direction} ({self.current_st_value:.2f})", "HEARTBEAT")
                
                time.sleep(1)
                
            except KeyboardInterrupt:
                self.log("🛑 [CORE] Termination requested", "CORE")
                if self.streamer:
                    self.streamer._terminating = True
                    self.streamer.disconnect_all()
                self.execute_exit_all("Manual Stop")
                os._exit(0)
            except Exception as e:
                logger.error(f"Main Loop Error: {e}")
                print(f"❌ [CORE] Main Loop Error: {e}") # Ensure visibility
                time.sleep(5)

    def process_iteration(self):
        # === Data Stitching: Deep History (Stable ATR) + Fresh Intraday (Live) ===
        from lib.api.historical import get_intraday_data_v3, get_historical_data
        
        # 1. Fetch Deep History (Last 5 days) for Indicator Stability
        interval_str = f"{self.config['candle_interval_minutes']}minute"
        hist_data = get_historical_data(self.upstox_token, self.futures_key, interval_str, 500)
        
        # 2. Fetch Fresh Intraday Data (Current Day)
        intraday_data = get_intraday_data_v3(
            self.upstox_token, 
            self.futures_key, 
            "minute", 
            self.config['candle_interval_minutes']
        )
        
        if not hist_data and not intraday_data: return

        # 3. Operations: Convert -> Stitch -> Deduplicate
        df_hist = pd.DataFrame(hist_data) if hist_data else pd.DataFrame()
        df_intraday = pd.DataFrame(intraday_data) if intraday_data else pd.DataFrame()
        
        if not df_hist.empty: df_hist['timestamp'] = pd.to_datetime(df_hist['timestamp'])
        if not df_intraday.empty: df_intraday['timestamp'] = pd.to_datetime(df_intraday['timestamp'])
        
        # Combine: Intraday overwrites overlapping history
        if not df_hist.empty and not df_intraday.empty:
            # Drop rows from history that are present in intraday (by timestamp)
            df_hist = df_hist[~df_hist['timestamp'].isin(df_intraday['timestamp'])]
            df = pd.concat([df_hist, df_intraday]).sort_values('timestamp').reset_index(drop=True)
        elif not df_intraday.empty:
            df = df_intraday
        else:
            df = df_hist
        
        # === INDICATOR UPDATES ===
        # 1. Supertrend: Uses full stitched dataset for ATR stability
        self.update_indicators(df)
        
        # 2. VWAP: Uses tick-level data from WebSocket (zero API calls!)
        #    VWAPCalculator automatically resets at session start (9:15 AM)
        self.current_vwap = self.vwap_calculator.get_vwap(self.futures_key)
        
        
        
        
        pcr = self.last_pcr
        if self.config.get('oi_check_enabled'):
            try:
                if not self.cached_expiry:
                    self.cached_expiry = get_expiry_for_strategy(self.upstox_token, self.config['expiry_type'], self.config['underlying'])
                
                option_chain_df = get_option_chain_atm(
                    self.upstox_token, self.oi_analyzer.underlying_key, self.cached_expiry,
                    strikes_above=self.config.get('oi_strikes_radius', 4) + 2, 
                    strikes_below=self.config.get('oi_strikes_radius', 4) + 2
                )
                
                if not option_chain_df.empty:
                    oi_data = self.oi_analyzer.calculate_cumulative_oi(self.fixed_oi_strikes, option_chain_df)
                    if "error" not in oi_data:
                        pcr = oi_data.get('pcr', 0.0)
                        self.last_pcr = pcr
            except Exception as e:
                logger.debug(f"PCR Error: {e}")
        
        self.log(f"Fut: {self.futures_price:.2f} | VWAP: {self.current_vwap:.2f} | ST: {self.current_st_direction} ({self.current_st_value:.2f}) | PCR: {pcr:.2f}")

        trade_action = None
        
        with self.lock:
            if self.positions:
                # Check for Trend Reversal Exit (If Configured for Candle Close)
                if self.config.get('exit_on_candle_close', True):
                    should_exit, ext_type, reason = self.check_exit_signal_candle()
                    if should_exit:
                        self.execute_exit_all(f"{ext_type}: {reason}")
                        return

                # Check for Pyramiding (Once per candle)
                can_py, py_reason = self.can_add_pyramid()
                if can_py: 
                     trade_action = ("PYRAMID", self.current_direction, py_reason)
            
            # Check for Entry (If Configured for Candle Close)
            elif self.config.get('enter_on_candle_close', False):
                should_enter, direction, reason = self.check_entry_signal(pcr)
                if should_enter:
                    trade_action = ("ENTRY", direction, reason)

        # Execute Trade Outside Lock
        if trade_action:
            if trade_action[0] == "ENTRY":
                self.execute_trade(trade_action[1], trade_action[2])
            elif trade_action[0] == "PYRAMID":
                self.execute_trade(trade_action[1], trade_action[2], is_pyramid=True)

    def check_realtime_exits(self):
        with self.lock:
            if not self.positions: return
            
            # 1. TSL Check (Always Live)
            should_exit, ext_type, reason = self.check_exit_signal() 
            if should_exit: 
                self.execute_exit_all(f"{ext_type}: {reason}")
                return

            # 2. Trend Reversal Check (If Configured for Tick-by-Tick)
            if not self.config.get('exit_on_candle_close', True):
                should_exit, ext_type, reason = self.check_exit_signal_candle()
                if should_exit:
                    self.execute_exit_all(f"{ext_type} (Realtime): {reason}")

    def check_realtime_entries(self):
        """Checks for entries tick-by-tick based on static indicators"""
        should_enter = False
        direction = None
        reason = ""
        
        if self.config.get('enter_on_candle_close', False):
            return

        with self.lock:
            if not self.positions:
                should_enter, direction, reason = self.check_entry_signal(self.last_pcr)
        
        if should_enter: 
            # CALL EXECUTE OUTSIDE LOCK to avoid blocking WebSocket updates while fetching option chain
            if time.time() - self.last_entry_log_time > 10:
                self.execute_trade(direction, reason)
                self.last_entry_log_time = time.time()

    def find_short_buildup_strike(self, direction: str, ideal_strike: int, atm_strike: int) -> Optional[int]:
        """Scans option chain for short buildup candidates: Price Dec >= 20% and OI Inc >= 30%
        Also enforces minimum OTM offset from ATM.
        """
        if not self.config.get('short_buildup_enabled', True):
            return ideal_strike
            
        try:
            # 1. Cache Expiry
            if not self.cached_expiry:
                self.cached_expiry = get_expiry_for_strategy(self.upstox_token, self.config['expiry_type'], self.config['underlying'])
            
            # 2. Cache Option Chain (60-second TTL)
            now_ts = time.time()
            if self.cached_chain.empty or (now_ts - self.last_chain_fetch > 60):
                self.log("🔄 [CORE] Fetching fresh option chain for buildup scan...", "CORE")
                self.cached_chain = get_option_chain_atm(
                    self.upstox_token, self.oi_analyzer.underlying_key, self.cached_expiry,
                    strikes_above=15, strikes_below=15
                )
                self.last_chain_fetch = now_ts
                
            chain = self.cached_chain
            
            if chain.empty:
                self.log("⚠️ [CORE] Option chain empty during short buildup scan", "CORE")
                return None
            
            # Filter by direction and then by buildup criteria
            df = chain[chain['instrument_type'] == direction].copy()
            df = df.fillna(0) # Safety against NaN values
            
            p_threshold = self.config.get('short_buildup_p_dec_threshold', 0.20)
            oi_threshold = self.config.get('short_buildup_oi_inc_threshold', 0.30)
            min_otm = self.config.get('min_otm_offset', 100)
            
            # Calculate percentages with safe division
            df['p_dec_pct'] = np.where(df['prev_ltp'] > 0, (df['prev_ltp'] - df['ltp']) / df['prev_ltp'], 0)
            df['oi_inc_pct'] = np.where(df['prev_oi'] > 0, (df['oi'] - df['prev_oi']) / df['prev_oi'], 0)
            
            # 1. Buildup Criteria
            df_buildup = df[
                (df['p_dec_pct'] >= p_threshold) & 
                (df['oi_inc_pct'] >= oi_threshold)
            ].copy()
            
            # 2. OTM Displacement Criteria (Enforce minimum distance from ATM)
            if direction == 'CE':
                df_buildup = df_buildup[df_buildup['strike_price'] >= atm_strike + min_otm]
            else:
                df_buildup = df_buildup[df_buildup['strike_price'] <= atm_strike - min_otm]

            if df_buildup.empty:
                # Find the closest strike to show its values in log
                df['strike_diff'] = abs(df['strike_price'] - ideal_strike)
                closest = df.sort_values('strike_diff').iloc[0]
                self.log(f"📉 [CORE] No {direction} strikes meet Short Buildup + OTM (Best: {int(closest['strike_price'])} | P-Dec: {closest['p_dec_pct']*100:.1f}/{p_threshold*100}% | OI-Inc: {closest['oi_inc_pct']*100:.1f}/{oi_threshold*100}%)", "CORE")
                return None
            
            # Find the strike closest to our ideal strike among qualifying ones
            df_buildup['strike_diff'] = abs(df_buildup['strike_price'] - ideal_strike)
            best_match = df_buildup.sort_values('strike_diff').iloc[0]
            
            chosen_strike = int(best_match['strike_price'])
            self.log(f"🎯 [CORE] Short Buildup Strike Found: {chosen_strike} (P-Dec: {best_match['p_dec_pct']*100:.1f}%, OI-Inc: {best_match['oi_inc_pct']*100:.1f}%, OTM: {abs(chosen_strike-atm_strike)})", "CORE")
            
            return chosen_strike
            
        except Exception as e:
            self.log(f"❌ [CORE] Error scanning for short buildup: {e}", "CORE")
            return None

    def execute_trade(self, direction: str, reason: str, is_pyramid: bool = False):
        self.log(f"⚡ [CORE] ENTRY SIGNAL: {reason}", "CORE")
        
        try:
            # Performance: Use cached expiry and WebSocket spot
            if not self.cached_expiry:
                self.cached_expiry = get_expiry_for_strategy(self.upstox_token, self.config['expiry_type'], self.config['underlying'])
            
            expiry_dt = datetime.strptime(self.cached_expiry, "%Y-%m-%d")

            if not is_pyramid:
                # Performance: Use WebSocket spot instead of REST quote
                spot = self.futures_price
                if spot == 0:
                    quote = get_market_quote_for_instrument(self.upstox_token, self.oi_analyzer.underlying_key)
                    spot = quote.get('last_price', 0)
                
                s_step = self.strike_step if self.strike_step > 0 else 50
                atm_strike = int(round(spot / s_step) * s_step)
                offset = self.config['atm_offset_ce'] if direction == 'CE' else self.config['atm_offset_pe']
                ideal_strike = atm_strike + offset
                
                # Apply Short Buildup Filter (with OTM constraint)
                strike = self.find_short_buildup_strike(direction, ideal_strike, atm_strike)
                if strike is None:
                    self.log(f"🚫 [CORE] Entry Aborted: No {direction} strike found with short buildup.", "CORE")
                    return
                
                u_key = get_option_instrument_key(self.config['underlying'], strike, direction, self.nse_data)
            else:
                strike = self.positions[0].strike
                u_key = self.positions[0].instrument_key

            _, k_symbol = get_strike_token(self.kotak_broker, strike, direction, expiry_dt)
            
            # FIX: Enforce NSE_FO| prefix for Upstox subscription
            if u_key and not u_key.startswith("NSE_FO|"):
                self.log(f"⚠️ [CORE] Fixing missing prefix for {u_key}", "CORE")
                u_key = f"NSE_FO|{u_key}"

            if not k_symbol or not u_key:
                self.log(f"❌ [CORE] Failed to resolve symbols for strike {strike}", "CORE")
                return

            ls = get_lot_size(u_key, self.nse_data)
            
            # Place Order
            # Place Order
            order_id = self.order_mgr.place_order(
                symbol=k_symbol, 
                qty=int(self.config['lot_size'] * ls), 
                transaction_type='S', 
                product="MIS" if self.config['product_type'] == 'D' else 'NRML',
                tag=f"VWAP_ST_{direction}"
            )
            
            if order_id:
                self.log(f"✅ [KOTAK] Sold {k_symbol}. Order ID: {order_id}", "KOTAK")
                opt_quote = get_market_quote_for_instrument(self.upstox_token, u_key)
                entry_price = opt_quote.get('last_price', 100)
                
                with self.lock:
                    new_pos = Position(direction, strike, entry_price, self.config['lot_size'], len(self.positions), u_key, ls)
                    self.positions.append(new_pos)
                    self.current_direction = direction
                
                # Monitor this option via WebSocket
                self.streamer.subscribe_market_data([u_key], mode="ltpc")
                
        except Exception as e:
            self.log(f"❌ [CORE] Entry Execution Error: {e}", "CORE")

    def execute_exit_all(self, reason: str):
        with self.lock:
            if not self.positions: return
            self.log(f"🚪 [CORE] EXIT ALL: {reason}", "CORE")
            
            if not self.cached_expiry:
                self.cached_expiry = get_expiry_for_strategy(self.upstox_token, self.config['expiry_type'], self.config['underlying'])
            
            expiry_dt = datetime.strptime(self.cached_expiry, "%Y-%m-%d")

            for pos in self.positions:
                _, symbol = get_strike_token(self.kotak_broker, pos.strike, pos.direction, expiry_dt)
                try:
                    self.order_mgr.place_order(
                        symbol=symbol, 
                        qty=int(pos.lot_size * pos.pnl_multiplier), 
                        transaction_type='B', 
                        product="MIS" if self.config['product_type'] == 'D' else 'NRML',
                        tag=f"VWAP_ST_EXIT"
                    )
                except Exception as e:
                    self.log(f"❌ [CORE] Failed to exit {symbol}: {e}", "CORE")
            self.clear_positions()
            self.log("✅ [KOTAK] Positions Cleared", "KOTAK")

if __name__ == "__main__":
    from lib.core.authentication import get_access_token
    token = get_access_token()
    if not token:
        print("❌ [CORE] Error: Access token not found. Please authenticate first.")
        sys.exit(1)
        
    strat = FuturesVWAPSupertrendLive(token, CONFIG)
    strat.run()

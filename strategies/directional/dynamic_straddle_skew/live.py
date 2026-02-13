"""
Dynamic Straddle Skew - Live Execution Script

STRATEGY OVERVIEW
-----------------
This strategy executes a dynamic straddle/strangle with skew-based position management.
It starts neutral and adapts to market trends by pyramiding on the winning side and 
defensively reducing risk on the losing side or rolling positions.

LOGIC SUMMAY
------------
1. ENTRY:
   - Time: 09:20 AM (Configurable)
   - Action: Sell CE + PE (Straddle or Strangle based on config).
   - RSI Filter: Optionally check if 14-period RSI is within a neutral range (e.g. 40-60).
   - Lot Size: 'initial_lots' (Default 1+1).

2. SKEW DETECTION (Bias):
   - Trigger: Premium of one leg drops significantly below the other.
   - Condition: winning_leg_price < losing_leg_price * (1 - skew_threshold_pct).
   - Persistence: Must hold for 'skew_persistence_ticks' (e.g., 5s) to filter noise.

3. PYRAMIDING (Aggressive Trend Following):
   - Trigger: Winning leg price decays by 10% from its last reference price.
     (Independent Leg Tracking: Does not use Total Portfolio Premium).
   - Action: Add 'pyramid_lot_size' (1 lot) to the WINNING side.
   - Safety: BLOCKED if Current Total Premium > Weighted Entry Premium (Net Loss Guard).
     (Ensures we only pyramid if the overall position including all lots is green).
   - Limit: Up to 'max_pyramid_lots' additional lots.

4. ROLL ADJUSTMENT (Capacity Reset):
   - Trigger: Skew > 35% AND Winning Prem < Losing Prem * 0.8.
   - Guard: ONLY Executes if Pyramiding is Full (Max Lots Reached).
     (Pyramid Priority: We ride the trend until full, then reset/roll).
   - Action: Close winning leg and re-enter closer to losing leg premium.

5. DEFENSIVE REDUCTION (Reversal):
   - Trigger: Winning leg price rises by 'reduction_recovery_pct' (e.g., 30%) 
     from its lowest point (Trailing Stop for the Pyramid).
   - Action: Reduce 1 lot from the winning side (De-pyramid).
   - CRITICAL INVERSION EXIT:
     - Trigger: Winning Leg Price > Losing Leg Price (Trend Failure).
     - Action: IMMEDIATELY EXIT ALL PYRAMID LOTS to return to Neutral (1v1).

6. RISK MANAGEMENT:
   - Max Loss: Daily fixed limit (e.g., 10k).
   - Target Profit: % of deployed capital (e.g., 30%).
   - Profit Locking: Ratchet mechanism (Lock 50% at 2k, 60% at 4k, etc.).
   - TSL (Trailing SL) Action: IMMEDIATELY EXIT ALL PYRAMID LOTS to return to Neutral. 
   - Neutral Continuity: If no pyramid lots exist, resets anchors and continues (No Cooldown).
   - Individual Leg SL: 60% hard stop per leg (Emergency).
   - Global SL: Combined Premium Stop Loss ( Implicit via Max Loss/Skew management).

7. EXIT:
   - Time Based: 15:15 PM.
   - Stop Loss/Target Hit.
"""

import sys
import os
import logging
import time
import threading
from datetime import datetime, timedelta
from typing import Optional

# Add project root to path
root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if root not in sys.path:
    sys.path.append(root)

# Import core strategy logic
from strategies.directional.dynamic_straddle_skew.strategy_core import DynamicStraddleSkewCore, LegPosition
from strategies.directional.dynamic_straddle_skew.config import CONFIG, validate_config

# Import library functions
from lib.api.market_data import download_nse_market_data, get_market_quote_for_instrument, fetch_historical_data
from lib.api.streaming import UpstoxStreamer
from lib.api.market_quotes import get_ltp_quote
from lib.utils.instrument_utils import get_option_instrument_key
from lib.utils.expiry_cache import get_expiry_for_strategy
from lib.utils.indicators import calculate_rsi
from lib.core.authentication import check_existing_token, perform_authentication, save_access_token

# Kotak Neo API Imports
from kotak_api.lib.broker import BrokerClient
from kotak_api.lib.order_manager import OrderManager
from kotak_api.lib.trading_utils import get_strike_token

# Logger setup
logger = logging.getLogger("DynamicStraddleSkew")
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

class DynamicStraddleSkewLive(DynamicStraddleSkewCore):
    def __init__(self, access_token: str, config: dict):
        super().__init__(config)
        self.access_token = access_token
        self.nse_data = None
        self.streamer = None
        self.kotak_broker = BrokerClient()
        self.order_mgr = None
        self.expiry = None
        
        self.underlying_key = {
            "NIFTY": "NSE_INDEX|Nifty 50",
            "BANKNIFTY": "NSE_INDEX|Nifty Bank",
            "FINNIFTY": "NSE_INDEX|Nifty Fin Service"
        }.get(config['underlying'], None)
        
        if not self.underlying_key:
            self.log(f"⚠️ Unknown underlying: {config['underlying']}. Defaulting to NIFTY key.")
            self.underlying_key = "NSE_INDEX|Nifty 50"
            
        self.realized_pnl = 0.0
        self.current_net_pnl = 0.0
        self.pnl_anchor = 0.0 # Tracks realized PnL at start of current session
        self.current_spot = 0.0
        
    def initialize(self):
        self.log("📋 Validating configuration...")
        validate_config()
        self.log("📊 [UPSTOX] Loading market data...")
        self.nse_data = download_nse_market_data()
        self.expiry = get_expiry_for_strategy(self.access_token, self.config['expiry_type'], self.config['underlying'])
        
        self.log("🔐 [KOTAK] Authenticating execution broker...")
        kotak_client = self.kotak_broker.authenticate()
        if kotak_client:
            self.order_mgr = OrderManager(kotak_client, dry_run=self.config.get('dry_run', False))
            self.kotak_broker.load_master_data()
        
        if self.config.get('use_websockets', True):
            self.streamer = UpstoxStreamer(self.access_token)
            self.streamer.add_market_callback(self.on_market_data)
            
            # Subscribe to Spot immediately for real-time updates
            self.streamer.connect_market_data([self.underlying_key], mode='ltpc')
            
            # Wait for connection
            self.log("⏳ Waiting for WebSocket connection...")
            for _ in range(5):
                time.sleep(1)
                if self.streamer.market_data_connected:
                    self.log("✅ WebSocket connection confirmed")
                    break
            else:
                 self.log("⚠️ WebSocket not confirmed within 5s")
            
        # Initial Spot Fetch
        try:
            quote = get_market_quote_for_instrument(self.access_token, self.underlying_key)
            if quote:
                self.current_spot = quote.get('last_price', 0)
        except:
            pass
            
        # Get lot size for P&L calculations
        from lib.utils.instrument_utils import get_lot_size, get_future_instrument_key
        self.lot_size = 75 # Default fallback
        try:
            # CORRECT WAY: Get Future Instrument for the underlying (e.g. NIFTY Futures)
            # The Index itself (NSE_INDEX|...) usually has NaN for lot_size in master data
            fut_key = get_future_instrument_key(self.config['underlying'], self.nse_data)
            if fut_key:
                self.lot_size = get_lot_size(fut_key, self.nse_data)
                self.log(f"✅ Resolved Lot Size: {self.lot_size} (via Future: {fut_key})")
            else:
                self.log(f"⚠️ Could not find Future for {self.config['underlying']}. Trying Kotak fallback...")
                raise ValueError("No future found")
        except Exception as e:
            self.log(f"⚠️ Could not fetch lot size from Upstox: {e}. Trying Kotak...")
            try:
                # Fallback to Kotak resolution
                strike = self.get_atm_strike()
                expiry_dt = datetime.strptime(self.expiry, "%Y-%m-%d")
                _, trading_symbol = get_strike_token(self.kotak_broker, strike, 'CE', expiry_dt)
                if trading_symbol:
                    from kotak_api.lib.trading_utils import get_lot_size as get_kotak_lot_size
                    self.lot_size = get_kotak_lot_size(self.kotak_broker.master_df, trading_symbol)
            except Exception as ke:
                self.log(f"⚠️ Could not fetch lot size from Kotak: {ke}. Using fallback 75.")
            
        self.log(f"✅ Initialized for {self.config['underlying']} | Expiry: {self.expiry} | Lot Size: {self.lot_size}")
        return True

    def log(self, message: str):
        logger.info(message)

    def get_atm_strike(self) -> int:
        # 1. Use cached spot from WebSocket if available
        spot = self.current_spot
        
        # 2. Fallback to API if WebSocket hasn't received first tick yet
        if spot <= 0:
            quote = get_market_quote_for_instrument(self.access_token, self.underlying_key)
            if quote:
                spot = quote.get('last_price', 0)
        
        if spot <= 0:
            self.log("⚠️ [UPSTOX] Could not fetch spot price. Using fallback 24500 (Check market hours).")
            return 24500 # Slightly better fallback for current market
            
        strike_step = 50 if self.config['underlying'] == "NIFTY" else 100
        return round(spot / strike_step) * strike_step

    def get_current_rsi(self) -> float:
        """
        Fetch 1-min candles for the underlying and calculate current 14-period RSI.
        Used as an entry guard to ensure neutral market conditions.
        
        Returns:
            float: Current RSI value, or -1 if calculation fails.
        """
        try:
            # 1. Calculate dates for historical fetch
            end_date = datetime.now()
            start_date = end_date - timedelta(days=1) # Fetch at least 1 day to ensure enough candles
            
            # 2. Fetch candles
            df = fetch_historical_data(
                self.access_token, 
                self.underlying_key, 
                interval_type='minute', 
                interval=1,
                start_date=start_date,
                end_date=end_date
            )
            
            if df.empty:
                self.log("⚠️ [CORE] Could not fetch candles for RSI. Skipping RSI check.")
                return -1
            
            # 3. Calculate RSI
            period = self.config.get('rsi_period', 14)
            rsi_val = calculate_rsi(df, period=period)
            
            return rsi_val
        except Exception as e:
            self.log(f"⚠️ [CORE] Error calculating RSI: {e}")
            return -1

    def execute_trade(self, option_type: str, action: str, lots: int, price: float, strike: int = None):
        """Action: ENTRY, PYRAMID, REDUCE, EXIT"""
        leg = self.ce_leg if option_type == 'CE' else self.pe_leg
        if not leg and action != "ENTRY": return
        
        transaction_type = 'S' if action in ['ENTRY', 'PYRAMID'] else 'B'
        
        # Resolve Kotak Symbol
        # Priority: Provided Strike -> Leg Strike -> Strategy Target Strike
        trade_strike = strike if strike else (leg.strike if leg else self.target_strike)
        
        expiry_dt = datetime.strptime(self.expiry, "%Y-%m-%d")
        _, trading_symbol = get_strike_token(self.kotak_broker, trade_strike, option_type, expiry_dt)
        
        from kotak_api.lib.trading_utils import get_lot_size as get_kotak_lot_size
        klot_size = get_kotak_lot_size(self.kotak_broker.master_df, trading_symbol)
        quantity = lots * klot_size
        
        self.log(f"⚖️ [KOTAK] {action} {option_type} {trade_strike}: {lots} lots @ {price}")
        
        order_id = self.order_mgr.place_order(
            symbol=trading_symbol,
            qty=quantity,
            transaction_type=transaction_type,
            tag=f"Skew_{action}",
            order_type="MKT"
        )
        if order_id:
             self.log(f"✅ Order Placed: {order_id}")
             
             # agent_best_practices: Verify execution price
             # Wait briefly for fill details to propagate if needed (though place_order waits 1s)
             exec_price = self.order_mgr.get_execution_price(order_id)
             
             if exec_price > 0:
                 self.log(f"✅ Order Placed: {order_id} @ Avg {exec_price:.2f}")
                 if abs(exec_price - price) > (price * 0.05): # 5% Slippage Warning
                     self.log(f"⚠️ Slippage Detected: Req {price} -> Exec {exec_price}")
                 return order_id, exec_price
             else:
                 self.log(f"✅ Order Placed: {order_id} (Price Unavailable)")
                 self.log(f"⚠️ [CORE] Exec Price not available yet. Using LTP {price} as fallback.")
                 return order_id, price
                 
        return None, 0.0

    def on_market_data(self, data):
        if 'marketInfo' in data: data = data['marketInfo']
        key = data.get('instrument_key')
        ltp = data.get('last_price', 0)
        if not ltp: ltp = data.get('ltpc', {}).get('ltp', 0)
        
        if not ltp: return
        
        with self.lock:
            if key == self.underlying_key:
                self.current_spot = ltp
            elif self.ce_leg and key == self.ce_leg.instrument_key:
                self.ce_leg.update_price(ltp)
            elif self.pe_leg and key == self.pe_leg.instrument_key:
                self.pe_leg.update_price(ltp)

    def run(self):
        self.log("▶️ Live Monitoring Started")
        
        while True:
            # 0. Global Kill Switch Check
            if os.path.exists("c:/algo/upstox/.STOP_TRADING"):
                self.log("🛑 Global Kill Switch Detected (.STOP_TRADING). Stopping Strategy.")
                self.exit_all() # Ensure we are flat
                self.running = False
                break

            current_time = datetime.now().time()
            entry_time = datetime.strptime(self.config['entry_start_time'], '%H:%M').time()
            exit_time = datetime.strptime(self.config['exit_time'], '%H:%M').time()
            
            if current_time < entry_time:
                time.sleep(10)
                continue
            
            if current_time > exit_time:
                self.log("🚪 Exit Time Reached. Closing all.")
                self.exit_all()
                break

            if not self.base_entered:
                if self.enter_base_straddle():
                    self.base_entered = True
                else:
                    # If entry skipped due to skew, wait and retry
                    time.sleep(10)
                    continue

            # Logic checks every 5 seconds
            # === Stale Data Check ===
            current_ts = datetime.now()
            max_delay = 5 # seconds
            
            # Check CE Leg Stale
            if self.ce_leg and (current_ts - self.ce_leg.last_update_time).total_seconds() > max_delay:
                # self.log(f"⚠️ CE Data Stale (> {max_delay}s). Fetching via REST...")
                try:
                    q = get_market_quote_for_instrument(self.access_token, self.ce_leg.instrument_key)
                    if q and 'last_price' in q:
                         self.ce_leg.update_price(q['last_price'])
                except Exception as e:
                    pass # self.log(f"Error fetching CE: {e}")

            # Check PE Leg Stale
            if self.pe_leg and (current_ts - self.pe_leg.last_update_time).total_seconds() > max_delay:
                 # self.log(f"⚠️ PE Data Stale (> {max_delay}s). Fetching via REST...")
                 try:
                    q = get_market_quote_for_instrument(self.access_token, self.pe_leg.instrument_key)
                    if q and 'last_price' in q:
                         self.pe_leg.update_price(q['last_price'])
                 except Exception as e:
                    pass

            try:
                self.monitor_and_adjust()
                # Update P&L before logic checks to ensure zero-delay accuracy
                self.update_pnl()
            except Exception as e:
                self.log(f"⚠️ [CORE] Error in monitoring loop: {e}")
                import traceback
                traceback.print_exc()
            
            # 1. Global Max Loss Check (Critical)
            if self.current_net_pnl <= -abs(self.config['max_loss_per_day']):
                self.log(f"🛑 [CORE] GLOBAL MAX LOSS HIT: {self.current_net_pnl:.2f} (Limit: {self.config['max_loss_per_day']})")
                self.exit_all()
                break

            # 2. Profit Lock & Session Stop Check (Session PnL)
            session_pnl = self.current_net_pnl - self.pnl_anchor
            should_stop, reason = self.check_profit_goals(session_pnl)
            
            if should_stop:
                if "Profit Lock" in reason:
                    self.log(f"🛑 [CORE] PROFIT LOCK HIT: {reason}")
                    
                    # Check for pyramid lots
                    ce_pyr = (self.ce_leg.lots - self.config['initial_lots']) if self.ce_leg else 0
                    pe_pyr = (self.pe_leg.lots - self.config['initial_lots']) if self.pe_leg else 0
                    
                    if ce_pyr > 0 or pe_pyr > 0:
                        self.log(f"⚠️ [CORE] Pyramid lots detected (CE:{ce_pyr}, PE:{pe_pyr}). Exiting pyramid lots to return to Neutral.")
                        
                        # Track if all exits succeed
                        all_exits_successful = True
                        
                        for leg, pyr_lots in [(self.ce_leg, ce_pyr), (self.pe_leg, pe_pyr)]:
                            if leg and pyr_lots > 0:
                                self.log(f"🚪 [CORE] Exiting {pyr_lots} pyramid lots from {leg.option_type} {leg.strike}")
                                oid, exec_price = self.execute_trade(leg.option_type, 'REDUCE', pyr_lots, leg.current_price, strike=leg.strike)
                                
                                if oid:
                                    # Update Realized P&L
                                    pnl = (leg.entry_price - exec_price) * pyr_lots * self.lot_size
                                    self.realized_pnl += pnl
                                    
                                    # Restore to base state
                                    leg.lots = self.config['initial_lots']
                                    leg.entry_price = leg.base_entry_price  # Restore original entry price
                                    leg.reset_lowest_price(leg.current_price)
                                else:
                                    self.log(f"❌ [CORE] Failed to exit pyramid lots for {leg.option_type}. Aborting TSL reset.")
                                    all_exits_successful = False
                                    break
                        
                        # Only reset state if all exits were successful
                        if all_exits_successful:
                            # Reset strategy state to neutral
                            self.winning_type = None
                            self.last_pyramid_price = 0.0
                            self.last_pyramid_total_prem = 0.0
                            self.last_pyramid_entry_price = 0.0
                            self.log("✅ [CORE] Returned to Neutral state with base lots. Skipping cooldown.")
                        else:
                            self.log("⚠️ [CORE] TSL reset aborted due to order failure. Exiting all positions for safety.")
                            self.exit_all()
                            break
                    else:
                        self.log("ℹ️ [CORE] No pyramid lots exist. Continuing with base lots and resetting anchors.")

                    # Reset profit locking anchors to allow fresh tracking from current peak (Session P&L becomes 0)
                    self.pnl_anchor = self.current_net_pnl 
                    self.max_profit_reached = 0.0
                    self.locked_profit = 0.0
                    
                    continue # Continue monitoring without exiting base lots or entering cooldown
                    
                self.log(f"🛑 [CORE] GLOBAL EXIT TRIGGERED: {reason}")
                self.exit_all()
                break
                
            self.display_status()
            time.sleep(1)

    def update_pnl(self):
        """Calculates net P&L across all legs and updates current_net_pnl."""
        with self.lock:
            if not self.ce_leg or not self.pe_leg: return
            
            lot_size = getattr(self, 'lot_size', 75)
            ce_ltp = self.ce_leg.current_price
            pe_ltp = self.pe_leg.current_price
            
            ce_pnl = (self.ce_leg.entry_price - ce_ltp) * self.ce_leg.lots * lot_size
            pe_pnl = (self.pe_leg.entry_price - pe_ltp) * self.pe_leg.lots * lot_size
            total_unrealized = ce_pnl + pe_pnl
            self.current_net_pnl = self.realized_pnl + total_unrealized

    def display_status(self):
        with self.lock:
            if not self.ce_leg or not self.pe_leg: return
            
            # 1. Spot (Maintained via WebSocket)
            spot = self.current_spot
            
            # 2. Use Dynamic Lot Size for P&L
            lot_size = getattr(self, 'lot_size', 75)
            
            ce_ltp = self.ce_leg.current_price
            pe_ltp = self.pe_leg.current_price
            
            # 3. Calculate Skew %
            if ce_ltp > 0 and pe_ltp > 0:
                skew = abs(ce_ltp - pe_ltp) / max(ce_ltp, pe_ltp) * 100
            else:
                skew = 0
            
            # 4. P&L (Already updated via update_pnl)
            ce_pnl = (self.ce_leg.entry_price - ce_ltp) * self.ce_leg.lots * lot_size
            pe_pnl = (self.pe_leg.entry_price - pe_ltp) * self.pe_leg.lots * lot_size
            total_unrealized = ce_pnl + pe_pnl
            
            # 5. Calculate Total Premium Points (Weighted)
            total_entry_prem = (self.ce_leg.entry_price * self.ce_leg.lots) + (self.pe_leg.entry_price * self.pe_leg.lots)
            total_live_prem = (ce_ltp * self.ce_leg.lots) + (pe_ltp * self.pe_leg.lots)
            
            # 6. Winning side & Reduction Trigger
            winner_str = f"Winner: {self.winning_type or 'None'}"
            trigger_str = ""
            
            if self.winning_type:
               win_leg = self.ce_leg if self.winning_type == 'CE' else self.pe_leg
               # Calculate trigger: Lowest Price * (1 + recovery_pct)
               # Calculate Reduction Trigger: Lowest Price * (1 + recovery_pct)
               rec_pct = self.config['reduction_recovery_pct']
               trigger_price = win_leg.lowest_price * (1 + rec_pct)
               trigger_str = f" | RE.TRIG: {trigger_price:.1f}"

               # Calculate Pyramid Trigger (Price Based - Matches check_pyramid_signal)
               trigger_decay_pct = self.config.get('pyramid_trigger_decay_pct', 0.10)
               if self.last_pyramid_price > 0:
                   reference_price = self.last_pyramid_price
               else:
                   reference_price = win_leg.entry_price
               
               pyr_trigger_price = reference_price * (1 - trigger_decay_pct)
               trigger_str += f" | PYR.TRIG: {pyr_trigger_price:.1f}"

            # 7. Format terminal output
            # Format terminal output (clean ticker)
            now = datetime.now().strftime("%H:%M:%S")
            session_pnl = self.current_net_pnl - self.pnl_anchor
            status = (
                f"\r{now} | SPOT: {spot:7.1f} | "
                f"CE: {ce_ltp:5.1f} ({self.ce_leg.lots}L) | "
                f"PE: {pe_ltp:5.1f} ({self.pe_leg.lots}L) | "
                f"SKEW: {skew:4.1f}% | "
                f"TOT P&L: {self.current_net_pnl:+8.1f} | "
                f"SES P&L: {session_pnl:+8.1f} | "
                f"LOCK: {self.locked_profit:4.0f} | "
                f"{winner_str}{trigger_str}"
            )
            
            # Print with a clear end-of-line to prevent overlap
            sys.stdout.write(status.ljust(110))
            sys.stdout.flush()

    def log(self, message: str):
        # Move cursor to new line before printing log to avoid clashing with \r ticker
        print("\n" + message)
        logger.info(message) # Also keep in file log if configured

    def find_strike_by_premium(self, option_type: str, target_premium: float, max_premium: Optional[float] = None) -> int:
        """
        Find the strike closest to target premium using Batch API.
        If max_premium is provided, it filters out any strike with LTP > max_premium.
        """
        atm = self.get_atm_strike()
        step = self.lot_size if self.lot_size > 0 else 50 
        if "NIFTY" in self.config['underlying']: step = 50
        if "BANKNIFTY" in self.config['underlying']: step = 100
        
        # self.log(f"🔎 [CORE] Premium Scan Params: ATM={atm}, Step={step}, Target={target_premium}")
        
        # 1. Collect Candidate Keys
        direction = 1 if option_type == 'CE' else -1 # CE Up (OTM), PE Down (OTM)
        candidate_map = {} # {key: strike}
        keys_to_fetch = []
        
        current_strike = atm
        for i in range(20): # Scan 20 strikes
            key = get_option_instrument_key(self.config['underlying'], current_strike, option_type, self.nse_data, expiry_date=self.expiry)
            if key:
                candidate_map[key] = current_strike
                keys_to_fetch.append(key)
            current_strike += (step * direction)
            
        if not keys_to_fetch:
            self.log(f"❌ [CORE] No keys found for scanning {option_type}")
            return atm

        # 2. Batch Fetch Quotes
        from lib.api.market_data import get_market_quotes
        self.log(f"📡 [CORE] Fetching quotes for {len(keys_to_fetch)} strikes...")
        quotes = get_market_quotes(self.access_token, keys_to_fetch)
        # self.log(f"DEBUG: API returned {len(quotes)} quotes.")
        
        # 3. Find Best Match
        best_strike = atm
        min_diff = float('inf')
        
        found_strikes_log = []
        
        for key, data in quotes.items():
            # Match price (Upstox V2 uses 'last_price', some other points use 'ltp')
            ltp = data.get('last_price') or data.get('ltp')
            
            if ltp is not None:
                strike = None
                # 1. Match via Token (Reliable)
                token = data.get('instrument_token')
                if token:
                    strike = candidate_map.get(token)
                    
                # 2. Fallback: Match via Key (Normalized)
                if not strike:
                     strike = candidate_map.get(key)
                if not strike:
                     strike = candidate_map.get(key.replace(':', '|'))
                
                if strike:
                    # Apply strict limit if requested
                    if max_premium is not None and ltp > max_premium:
                        continue

                    diff = abs(ltp - target_premium)
                    found_strikes_log.append(f"{strike}:{ltp:.1f}")
                    
                    if diff < min_diff:
                        min_diff = diff
                        best_strike = strike
                # else:
                #     self.log(f"🔸 [DEBUG] Unmatched: {key} (Token: {token})")
        
        if found_strikes_log:
            self.log(f"🔎 [CORE] Scanned {option_type}: {', '.join(found_strikes_log)}")
            self.log(f"✨ [CORE] Selected {option_type}: {best_strike} (Diff: {min_diff:.1f})")
        else:
            self.log(f"⚠️ [CORE] Batch fetch returned no valid quotes for {option_type}. Defaulting to ATM.")
            
        return best_strike

    def enter_base_straddle(self):
        atm_strike = self.get_atm_strike()
        
        # Strike Selection Logic
        mode = self.config.get('strike_selection_type')
        
        if mode == 'STRANGLE_OFFSET':
            spread = self.config.get('strangle_spread', 100)
            ce_strike = atm_strike + spread
            pe_strike = atm_strike - spread
            self.log(f"📐 [CORE] Mode: STRANGLE_OFFSET (ATM {atm_strike} +/- {spread})")
            
        elif mode == 'STRANGLE_PREMIUM':
            target = self.config.get('target_premium', 50)
            self.log(f"🔍 [CORE] Searching for strikes near ₹{target}...")
            ce_strike = self.find_strike_by_premium('CE', target)
            pe_strike = self.find_strike_by_premium('PE', target)
            self.log(f"📐 [CORE] Mode: STRANGLE_PREMIUM (CE: {ce_strike}, PE: {pe_strike})")
            
        elif mode == 'STRANGLE' and self.config.get('strangle_spread'): # Backward compat
             spread = self.config.get('strangle_spread', 100)
             ce_strike = atm_strike + spread
             pe_strike = atm_strike - spread
             self.log(f"📐 [CORE] Mode: STRANGLE (Legacy) (ATM {atm_strike} +/- {spread})")

        else:
            ce_strike = atm_strike
            pe_strike = atm_strike
            self.log(f"📐 [CORE] Mode: STRADDLE (ATM {atm_strike})")

        self.target_strike = atm_strike # Reference only, legs maintain their own strikes
        
        ce_key = get_option_instrument_key(self.config['underlying'], ce_strike, 'CE', self.nse_data, expiry_date=self.expiry)
        pe_key = get_option_instrument_key(self.config['underlying'], pe_strike, 'PE', self.nse_data, expiry_date=self.expiry)
        # Initial entries
        def fetch_ready_price(key):
            quote = get_market_quote_for_instrument(self.access_token, key)
            if quote:
                price = quote.get('last_price', 0)
                if price > 0: return price
            self.log(f"⚠️ [UPSTOX] Could not get price for {key}. Quote: {quote}")
            return 0.0

        ce_price = fetch_ready_price(ce_key)
        pe_price = fetch_ready_price(pe_key)
        
        # If still 0, try a quick fallback to v3 LTP
        if ce_price == 0:
            q = get_ltp_quote(self.access_token, ce_key)
            if q and 'data' in q:
                d = q.get('data', {})
                ce_price = next((v['last_price'] for k, v in d.items() if k.replace(':', '|') == ce_key), 0.0)
            
        if pe_price == 0:
            q = get_ltp_quote(self.access_token, pe_key)
            if q and 'data' in q:
                d = q.get('data', {})
                pe_price = next((v['last_price'] for k, v in d.items() if k.replace(':', '|') == pe_key), 0.0)

        # === Entry Skew Validation ===
        if ce_price > 0 and pe_price > 0:
            entry_skew = abs(ce_price - pe_price) / max(ce_price, pe_price) * 100
            if entry_skew > 10.0:
                self.log(f"⚠️ [CORE] Entry Skipped: Skew too high ({entry_skew:.1f}% > 10%). Waiting for neutrality...")
                return False
        else:
            self.log("⚠️ [CORE] Entry Skipped: Could not fetch valid prices.")
            return False

        # === RSI Entry Filter ===
        if self.config.get('rsi_filter_enabled'):
            rsi_val = self.get_current_rsi()
            lower = self.config.get('rsi_lower_threshold', 40)
            upper = self.config.get('rsi_upper_threshold', 60)
            
            if rsi_val != -1:
                status = "Allowed" if lower <= rsi_val <= upper else "Skipped"
                self.log(f"🔍 [CORE] RSI Check: {rsi_val:.2f} | Thresholds: {lower}-{upper} | Status: {status}")
                
                if status == "Skipped":
                    return False
            else:
                self.log("⚠️ [CORE] RSI Filter enabled but value unavailable. Proceeding for safety.")

        # Updated Execution Logic with Atomic Rollback
        oid_ce, exec_ce = self.execute_trade('CE', 'ENTRY', self.config['initial_lots'], ce_price, strike=ce_strike)
        
        if oid_ce:
            oid_pe, exec_pe = self.execute_trade('PE', 'ENTRY', self.config['initial_lots'], pe_price, strike=pe_strike)
            
            if oid_pe:
                # Both Successful
                self.ce_leg = LegPosition('CE', ce_strike, exec_ce, self.config['initial_lots'], ce_key)
                self.pe_leg = LegPosition('PE', pe_strike, exec_pe, self.config['initial_lots'], pe_key)
                
                if self.streamer:
                    self.streamer.connect_market_data([self.underlying_key, ce_key, pe_key], mode='ltpc')
                    
                # Calculate Initial Capital using REAL prices
                self.initial_capital = (exec_ce * self.config['initial_lots'] * self.lot_size) + \
                                       (exec_pe * self.config['initial_lots'] * self.lot_size)
                self.log(f"🎯 [CORE] Positions entered: CE {ce_strike} @ {exec_ce} | PE {pe_strike} @ {exec_pe}")
                self.log(f"💰 [CORE] Initial Capital Deployed: ₹{self.initial_capital:.2f}")
                return True
            else:
                # PE Failed - Rollback CE
                self.log("❌ [CORE] PE entry failed. Rolling back CE for safety...")
                self.execute_trade('CE', 'EXIT', self.config['initial_lots'], exec_ce, strike=ce_strike)
        
        return False

    def monitor_and_adjust(self):
        with self.lock:
            if not self.ce_leg or not self.pe_leg: return
            
            # 1. Skew Detection (First Bias)
            if not self.winning_type:
                winner = self.check_skew_signal(self.ce_leg.current_price, self.pe_leg.current_price)
                if winner:
                    self.winning_type = winner
                    self.log(f"⚖️ [CORE] Skew detected: {winner} side winning")
                    self.do_pyramid()
            
            # 2. Skew Adjustment (Hybrid: Roll vs Pyramid)
            # Only run if we have a winning side (either just detected or existing)
            if self.winning_type:
                # Check for Roll Signal First (Strong Trend)
                should_roll, roll_reason = self.check_roll_signal()
                
                if should_roll:
                    self.log(f"🔄 [CORE] ROLL Trigger: {roll_reason}")
                    self.do_roll_adjustment()
                    
                # Else check for Pyramid (Moderate Trend)
                else: 
                     should_pyr, reason = self.check_pyramid_signal()
                     if should_pyr:
                         self.log(f"📈 [CORE] Pyramid Trigger: {reason}")
                         self.do_pyramid()
                         
                     # 3. Reduction (Defensive)
                     else:
                         should_red, reason = self.check_reduction_signal()
                         if should_red:
                             self.log(f"📉 [CORE] Reduction Trigger: {reason}")
                             self.do_reduction(reason)
                             
                         # 4. Profit Booking (Scalping)
                         else:
                             should_book, reason = self.check_profit_booking_signal()
                             if should_book:
                                 self.log(f"💰 [CORE] Pyramid Profit Booking: {reason}")
                                 self.do_reduction()

    def do_roll_adjustment(self):
        """
        Execute the roll:
        1. Identify new target strike (match premium of losing leg).
        2. Exit old winning leg.
        3. Enter new winning leg.
        4. Reset state specific to that leg.
        """
        if not self.winning_type: return
        
        # Identify legs
        win_leg = self.ce_leg if self.winning_type == 'CE' else self.pe_leg
        lose_leg = self.pe_leg if self.winning_type == 'CE' else self.ce_leg
        
        # 1. Find New Strike
        # Target premium = losing leg price * match_pct (e.g. 1.0)
        match_ratio = self.config.get('roll_premium_match_pct', 1.0)
        target_prem = lose_leg.current_price * match_ratio
        
        self.log(f"🔎 [CORE] ROLLING {self.winning_type}. Target Premium: {target_prem:.1f} (Max: {lose_leg.current_price:.1f})")
        
        # Enforce "Not selling above losing side premium"
        new_strike = self.find_strike_by_premium(self.winning_type, target_prem, max_premium=lose_leg.current_price)
        
        if new_strike == win_leg.strike:
            self.log("⚠️ [CORE] Roll Aborted: Best strike is same as current strike.")
            return

        # 2. Exit Old Leg
        self.log(f"🚪 [CORE] Rolling Out: Exiting {self.winning_type} {win_leg.strike} ({win_leg.lots} Lots)")
        oid_exit, exec_exit = self.execute_trade(self.winning_type, 'EXIT', win_leg.lots, win_leg.current_price, strike=win_leg.strike)
        
        # Calculate Realized P&L using REAL exit price
        final_exit_price = exec_exit if oid_exit else win_leg.current_price
        leg_pnl = (win_leg.entry_price - final_exit_price) * win_leg.lots * self.lot_size
        self.realized_pnl += leg_pnl
        self.log(f"💰 [CORE] Realized P&L from Roll: {leg_pnl:.2f}")

        # 3. Enter New Leg
        # Determine lots for the new leg
        # Condition: If Pyramided AND Skew > 35% -> Move with 1 lot only
        skew = abs(win_leg.current_price - lose_leg.current_price) / max(win_leg.current_price, lose_leg.current_price)
        
        if win_leg.lots > self.config['initial_lots'] and skew > 0.35:
            self.log(f"⚠️ [CORE] Aggressive Roll (Skew {skew*100:.1f}% > 35% & Pyramided). Reducing to initial lots ({self.config['initial_lots']}).")
            roll_lots = self.config['initial_lots']
        else:
            roll_lots = win_leg.lots 
        
        # Fetch new price (for record keeping, though execute_trade might fetch it too)
        new_key = get_option_instrument_key(self.config['underlying'], new_strike, self.winning_type, self.nse_data, expiry_date=self.expiry)
        q = get_market_quote_for_instrument(self.access_token, new_key)
        new_price = q.get('last_price', 0) if q else 0
        
        oid_entry, exec_entry = self.execute_trade(self.winning_type, 'ENTRY', roll_lots, new_price, strike=new_strike)
        
        if oid_entry:
            # Update Strategy State with REAL entry price
            new_leg = LegPosition(self.winning_type, new_strike, exec_entry, roll_lots, new_key)
            
            if self.winning_type == 'CE':
                self.ce_leg = new_leg
            else:
                self.pe_leg = new_leg
                
            # Subscribe to new key
            if self.streamer:
                self.streamer.connect_market_data([new_key], mode='ltpc')
                
            self.log(f"✅ [CORE] Rolled Into: {self.winning_type} {new_strike} @ {exec_entry} ({roll_lots} Lots)")
            
            # 4. Reset State
            # Reset lowest price anchor for the new leg
            new_leg.reset_lowest_price(new_price)
            
            # Reset Bias? 
            # Plan said "Reset winning_type".
            # If we roll to match premiums, we are theoretically neutral now.
            self.winning_type = None
            self.last_pyramid_price = 0.0
            
            # Reset Total Premium Anchor (New Basis)
            curr_ce_val = self.ce_leg.current_price * self.ce_leg.lots
            curr_pe_val = self.pe_leg.current_price * self.pe_leg.lots
            self.last_pyramid_total_prem = curr_ce_val + curr_pe_val
            
            self.mark_action_executed() # Global Cooldown Start

    def do_pyramid(self):
        leg = self.ce_leg if self.winning_type == 'CE' else self.pe_leg
        price = leg.current_price
        
        oid, exec_price = self.execute_trade(self.winning_type, 'PYRAMID', self.config['pyramid_lot_size'], price)
        if oid:
            leg.add_lots(self.config['pyramid_lot_size'], exec_price)
            self.last_pyramid_price = price
            self.last_pyramid_entry_price = price # Store specific entry for profit booking
            
            # Update Total Premium Anchor for Credit-Based Pyramiding
            curr_ce_val = self.ce_leg.current_price * self.ce_leg.lots
            curr_pe_val = self.pe_leg.current_price * self.pe_leg.lots
            self.last_pyramid_total_prem = curr_ce_val + curr_pe_val
            
            self.log(f"⚓ [CORE] New Pyramid Anchor: Total Prem {self.last_pyramid_total_prem:.1f}")
            self.mark_action_executed() # Global Cooldown Start

    def do_reduction(self, reason: str = ""):
        leg = self.ce_leg if self.winning_type == 'CE' else self.pe_leg
        exit_price = leg.current_price
        
        # Determine lots to reduce
        if reason == "INVERSION_CRITICAL":
            # Critical Safety: Exit ALL pyramid lots to return to base
            lots_to_reduce = leg.lots - self.config['initial_lots']
            self.log(f"🚨 [CORE] INVERSION DETECTED! Force Exiting ALL {lots_to_reduce} pyramid lots.")
        else:
            # Standard Reduction: Step down by pyramid size
            lots_to_reduce = self.config['pyramid_lot_size']
            
        # Safety: Ensure we don't reduce below base
        if lots_to_reduce <= 0: return

        oid, exec_exit = self.execute_trade(self.winning_type, 'REDUCE', lots_to_reduce, exit_price)
        if oid:
            # Calculate realized P&L for reduced lots using REAL price
            pnl = (leg.entry_price - exec_exit) * lots_to_reduce * self.lot_size
            self.realized_pnl += pnl
            
            leg.lots -= lots_to_reduce
            
            # === Bias Reset Logic ===
            # If we are back to initial lots, reset the winning side bias
            # This allows the strategy to catch a reversal if the other side becomes the winner
            
            # Record reduction for Hysteresis optimization (Total Premium)
            curr_tot_prem = (self.ce_leg.current_price * self.ce_leg.lots) + \
                            (self.pe_leg.current_price * self.pe_leg.lots)
            self.last_reduction_map[self.winning_type] = (datetime.now(), curr_tot_prem)
            self.log(f"🛑 [CORE] Recorded reduction for {self.winning_type} @ {exit_price} (TotalPrem: {curr_tot_prem:.1f})")
            self.mark_action_executed() # Global Cooldown Start
            
            # === FIX: Reset Lowest Price to Prevent Cascade ===
            # We just reduced because price rose. We must reset the 'Lowest' anchor 
            # to the current price so we don't trigger again immediately.
            # We want to trigger again ONLY if it dips and rises again, or rises drastically further.
            leg.reset_lowest_price(leg.current_price)
            
            if leg.lots <= self.config['initial_lots']:
                self.log(f"🔄 [CORE] Position reduced to base. Resetting bias for {self.winning_type}")
                
                # Store the side for cooldown before resetting winning_type
                exited_side = self.winning_type
                
                # Reset bias and pyramid state
                leg.entry_price = leg.base_entry_price  # Restore original entry price
                self.winning_type = None
                self.last_pyramid_price = 0.0
                self.last_pyramid_total_prem = 0.0 # Reset anchor
                
                # ✅ FIX: Reset profit lock variables for fresh start
                self.max_profit_reached = 0.0
                self.locked_profit = 0.0
                # ✅ FIX: Reset session anchor to current P&L for fresh session tracking
                self.pnl_anchor = self.current_net_pnl
                self.log(f"🔓 [CORE] Profit lock reset. Starting fresh P&L tracking from {self.current_net_pnl:.2f}.")
                
                # ✅ FIX: Update cooldown with current premium (already recorded at line 819, just logging)
                cooldown_mins = self.config.get('reduction_cooldown_minutes', 3)
                self.log(f"⏳ [CORE] Cooldown activated for {exited_side} ({cooldown_mins} mins)")
            else:
                # After reduction, reset pyramid anchor to latest price to avoid immediate re-entry
                self.last_pyramid_price = exit_price
                # Also reset total prem anchor so we require fresh decay from HERE
                curr_ce_val = self.ce_leg.current_price * self.ce_leg.lots
                curr_pe_val = self.pe_leg.current_price * self.pe_leg.lots
                self.last_pyramid_total_prem = curr_ce_val + curr_pe_val
                
                # Reset Specific Entry Price to prevent stale profit booking triggers
                self.last_pyramid_entry_price = 0.0

    def exit_all(self):
        if self.ce_leg:
            try:
                self.execute_trade('CE', 'EXIT', self.ce_leg.lots, self.ce_leg.current_price)
            except Exception as e:
                self.log(f"❌ Error closing CE: {e}")
        if self.pe_leg:
            try:
                self.execute_trade('PE', 'EXIT', self.pe_leg.lots, self.pe_leg.current_price)
            except Exception as e:
                self.log(f"❌ Error closing PE: {e}")
        self.ce_leg = None
        self.pe_leg = None

if __name__ == "__main__":
    from lib.core.authentication import get_access_token
    token = get_access_token()
    if not token: sys.exit(1)
    
    strategy = DynamicStraddleSkewLive(token, CONFIG)
    if strategy.initialize():
        try:
            strategy.run()
        except KeyboardInterrupt:
            strategy.log("⚠️ Interrupted. Exiting...")
            strategy.exit_all()
            if strategy.streamer: strategy.streamer.disconnect_all()
            os._exit(0)

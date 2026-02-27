"""
Inside Candle Breakout Strategy - Live Execution
-----------------------------------------------
This strategy captures high-momentum breakouts after consolidation (Inside Bar pattern).

Strategy Logic Summary:
1. Signal Detection (CORE):
   - Timeframe: 5-minute candles.
   - Pattern: High/Low of 'Baby' candle(s) stays inside 'Mother' candle range.
   - Trigger: Nifty Spot price breaks Mother High (Bullish) or Mother Low (Bearish).

2. Strategy Execution (KOTAK):
   - Bullish Breakout: Sell ATM-100 Put (PE).
   - Bearish Breakdown: Sell ATM+100 Call (CE).

3. Risk Management (CORE/KOTAK):
   - Spot SL: Exit if spot returns to Mother Low (for Bullish) or Mother High (for Bearish).
   - Tiered TSL: 
     - < 10% Profit: No trail or wide trail.
     - > 10% Profit: Move TSL to Breakeven.
     - > 20% Profit: Lock 10% profit (10% trail).
     - > 40% Profit: Lock extra profit (5% trail).
   - Time Exit: Hard square-off at 15:15 PM.
"""

import sys
import os
import time
import logging
from datetime import datetime, timedelta
import pandas as pd

# Path setup
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from lib.core.authentication import check_existing_token, perform_authentication, save_access_token
from lib.api.market_data import download_nse_market_data, get_market_quotes
from lib.api.historical import get_intraday_data_v3
from lib.utils.instrument_utils import get_future_instrument_key, get_option_instrument_key
from lib.utils.expiry_cache import get_expiry_for_strategy
from lib.utils.date_utils import is_market_open
from strategies.directional.inside_candle.config import StrategyConfig
from strategies.directional.inside_candle.strategy_core import InsideCandleAnalyzer

# Kotak Imports
from kotak_api.lib.broker import BrokerClient
from kotak_api.lib.order_manager import OrderManager

# Logger Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', force=True)
logger = logging.getLogger("InsideCandleLive")

def log_core(msg): logger.info(f"[CORE] {msg}")
def log_upstox(msg): logger.info(f"[UPSTOX] {msg}")
def log_kotak(msg): logger.info(f"[KOTAK] {msg}")

class InsideCandleLive:
    def __init__(self, access_token, nse_data, dry_run=False):

        self.access_token = access_token
        self.nse_data = nse_data
        self.dry_run = dry_run
        
        self.analyzer = InsideCandleAnalyzer()
        self.config = StrategyConfig
        
        # Kotak Setup
        self.kotak_broker = None
        self.kotak_order_manager = None
        
        # State
        self.active_position = None # {symbol, type, entry_price, spot_sl, qty}
        self.last_candle_time = None
        
    def initialize(self):
        log_core("Initializing Inside Candle Live Strategy...")
        try:
            self.kotak_broker = BrokerClient()
            self.kotak_broker.authenticate()
            self.kotak_order_manager = OrderManager(self.kotak_broker.client, dry_run=self.dry_run)
            log_kotak("Kotak Execution Engine Ready")
        except Exception as e:
            logger.error(f"[KOTAK] Execution Init Failed: {e}")
            return False
            
        return True

    def fetch_spot_candles(self):
        """Fetch 5-minute candles for NIFTY Index"""
        # Hardcoded for Nifty Index
        instrument_key = "NSE_INDEX|Nifty 50" 
        candles = get_intraday_data_v3(
            self.access_token, 
            instrument_key, 
            self.config.CANDLE_INTERVAL, 
            self.config.CANDLE_PERIOD
        )
        if not candles:
            return None
            
        df = pd.DataFrame(candles)
        # Sort and clean
        df['datetime'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('datetime').reset_index(drop=True)
        return df

    def get_spot_ltp(self):
        key = "NSE_INDEX|Nifty 50"
        quotes = get_market_quotes(self.access_token, [key])
        return quotes[key]['last_price'] if key in quotes else 0.0

    def execute_entry(self, signal):
        spot_ltp = signal['trigger_price']
        trade_type = signal['type'] # BULLISH or BEARISH
        spot_sl = signal['sl']
        
        log_core(f"Signal Triggered: {trade_type} @ Next {spot_ltp}")
        
        # 1. Determine Strike
        atm_strike = round(spot_ltp / 50) * 50
        
        if trade_type == "BULLISH":
            # Underlying is going UP -> Sell PE
            # Logic: ATM - 100
            strike = atm_strike - self.config.STRIKE_DISTANCE
            option_type = "PE"
        else:
            # Underlying is going DOWN -> Sell CE
            # Logic: ATM + 100
            strike = atm_strike + self.config.STRIKE_DISTANCE
            option_type = "CE"
            
        # 2. Get Instrument Key & Symbol
        # Need Expiry
        expiry = get_expiry_for_strategy(self.access_token, self.config.EXPIRY_TYPE, "NIFTY")
        
        opt_key = get_option_instrument_key("NIFTY", strike, option_type, self.nse_data, expiry_date=expiry)
        
        # Resolve Kotak Symbol
        # Note: Ideally usage of helper to get kotak symbol from upstox key or strike/expiry
        # For now assume we use standard Kotak symbol naming or lookup logic if available
        # Simplified: Using a hypothetical resolver or assume manual construction if needed
        # BUT we have `get_strike_token` in Kotak lib.
        from kotak_api.lib.trading_utils import get_strike_token
        expiry_dt = datetime.strptime(expiry, "%Y-%m-%d")
        k_token, k_symbol = get_strike_token(self.kotak_broker, strike, option_type, expiry_dt)
        
        if not k_symbol:
            logger.error("[KOTAK] Could not resolve Kotak Symbol")
            return

        # 3. Place Order
        qty = self.config.LOT_SIZE
        log_kotak(f"Placing Sell Order: {k_symbol} | Qty: {qty} | Type: {option_type}")
        
        order_id = self.kotak_order_manager.place_order(
            k_symbol, qty, "S", tag="INSIDE_BAR", product="MIS"
        )
        
        if not order_id:
            logger.error("[KOTAK] Order Placement Failed")
            return
            
        log_kotak(f"Order Placed Successfully. ID: {order_id}")
        
        # 4. Record Position
        # Need entry price for TSL
        # For simplicity, fetching LTP of option
        opt_quotes = get_market_quotes(self.access_token, [opt_key])
        
        entry_price = 0.0
        if opt_quotes and opt_key in opt_quotes:
             entry_price = opt_quotes[opt_key].get('last_price', 0.0)
        else:
             print("⚠️ Warning: Could not fetch Option Entry Price. TSL might be delayed.")
             # Fallback or risk of TSL failure? defaulting to 0 might break TSL calc logic.
             # TSL = lowest * 1.2. If lowest is 0, TSL is 0. 
             # If price is 100, 100 > 0 -> Exit immediately. Bad.
             # Ideally get from order response or retry. 
             # For now, if 0, we can't set active position correctly? 
             # Let's retry once or assume Spot SL is primary.
             time.sleep(1)
             retry_q = get_market_quotes(self.access_token, [opt_key])
             if retry_q and opt_key in retry_q:
                 entry_price = retry_q[opt_key].get('last_price', 0.0)
        
        if entry_price == 0:
            log_core("Start Price failed. Using rudimentary TSL base.")
            # Use a dummy high value for Short? No, we short, so lowest matters.
            # If we assume we sold at 0, logic is broken.
            # Let's skip TSL until we get next price update? 
            # monitoring loop updates lowest_price. So initialize with a high num.
            entry_price = 99999.9
        
        self.active_position = {
            "symbol": k_symbol,
            "instrument_key": opt_key,
            "type": option_type,
            "entry_price": entry_price,
            "spot_sl": spot_sl,
            "qty": qty,
            "lowest_price": entry_price # For Short, lower is better
        }
        log_core(f"Position Active: {k_symbol} @ {entry_price} | Spot SL: {spot_sl}")

    def monitor_active_position(self, spot_ltp):
        if not self.active_position: return
        
        pos = self.active_position
        
        # 1. Spot SL Check
        if pos['type'] == "PE": # Bullish Trade, Short PE
            # Spot SL is Mother Low. If Spot Breaks BELOW Low -> Exit
            if spot_ltp < pos['spot_sl']:
                log_core(f"Spot SL Hit! Nifty {spot_ltp} < {pos['spot_sl']}")
                self.exit_all()
                return
        else: # Bearish Trade, Short CE
            # Spot SL is Mother High. If Spot Breaks ABOVE High -> Exit
            if spot_ltp > pos['spot_sl']:
                log_core(f"Spot SL Hit! Nifty {spot_ltp} > {pos['spot_sl']}")
                self.exit_all()
                return

        # 2. Option TSL Check
        # Fetch Option LTP
        q = get_market_quotes(self.access_token, [pos['instrument_key']])
        if pos['instrument_key'] not in q:
            return
            
        opt_ltp = q[pos['instrument_key']]['last_price']
        
        # Update Lowest Price (Max Favorable Excursion for Short)
        if opt_ltp < pos['lowest_price']:
            pos['lowest_price'] = opt_ltp
            
        # --- Tiered TSL Logic ---
        # Calculate Max Profit % reached so far
        entry_val = pos['entry_price']
        low_val = pos['lowest_price']
        
        if entry_val > 0:
            max_profit_pct = (entry_val - low_val) / entry_val
        else:
            max_profit_pct = 0.0
            
        # Determine Trail Gap based on Tier
        current_gap = self.config.OPTION_TSL_PCT # Default 20%
        
        if max_profit_pct >= self.config.TSL_TIER_3_TRIGGER: # > 40%
            current_gap = self.config.TSL_TIER_3_PCT # 5%
        elif max_profit_pct >= self.config.TSL_TIER_2_TRIGGER: # > 20%
            current_gap = self.config.TSL_TIER_2_PCT # 10%
            
        # Calculate Base TSL Price
        tsl_price = low_val * (1 + current_gap)
        
        # Tier 1: Breakeven check
        # If we crossed Tier 1 trigger (10%), ensure TSL never exceeds Entry Price
        if max_profit_pct >= self.config.TSL_TIER_1_TRIGGER:
            tsl_price = min(tsl_price, entry_val)
            
        # Trigger Check
        if opt_ltp > tsl_price:
             log_core(f"Trailing SL Hit! Price {opt_ltp} > TSL {tsl_price:.2f} (Gap: {current_gap*100}%)")
             log_core(f"   Stats: Entry {entry_val} | Low {low_val} | MaxProfit {max_profit_pct*100:.1f}%")
             self.exit_all()
             return
             
    def exit_all(self):
        if not self.active_position: return
        pos = self.active_position
        log_kotak(f"Exiting {pos['symbol']}...")
        oid = self.kotak_order_manager.place_order(pos['symbol'], pos['qty'], "B", tag="SL_EXIT", product="MIS")
        if oid: log_kotak(f"Exit Order Placed: {oid}")
        self.active_position = None
        # Reset analyzer state to allow fresh patterns? 
        # Strategy rules didn't specify re-entry same day, but generally yes.
        self.analyzer.reset()

    def run(self):
        if not self.initialize(): return
        
        log_upstox("Waiting for market data...")
        
        while True:
            try:
                # 0. Global Kill Switch Check
                if os.path.exists("c:/algo/upstox/.STOP_TRADING"):
                    log_core("Global Kill Switch Detected (.STOP_TRADING). Stopping Strategy.")
                    self.exit_all()
                    break

                # Time check
                now = datetime.now()
                if now.time() > self.config.EXIT_TIME:
                    log_core("Market Closing time. Exiting.")
                    if self.active_position: self.exit_all()
                    break
                    
                # 1. Fetch Spot Data
                df = self.fetch_spot_candles()
                if df is None or len(df) < 2:
                    if now.second % 30 == 0:
                        log_upstox(f"Waiting for sufficient candles (Got: {len(df) if df is not None else 0})...")
                    time.sleep(1)
                    continue
                    
                spot_ltp = self.get_spot_ltp()
                
                # 2. Check for New Candle Close
                curr_candle_time = df.iloc[-1]['datetime']
                
                # Check Entry Time Window
                if now.time() < self.config.ENTRY_START_TIME:
                     if now.second % 30 == 0:
                         log_core(f"Waiting for Start Time {self.config.ENTRY_START_TIME}...")
                     time.sleep(1)
                     continue
                
                # If we have a new closed candle (assumed valid as per fetch delay)
                if self.last_candle_time != curr_candle_time:
                    self.last_candle_time = curr_candle_time
                    # Run Pattern Detection
                    is_inside = self.analyzer.detect_pattern(df)
                    if is_inside:
                        log_core("Inside Bar Pattern Detected. Watching for Breakout...")
                
                # 3. Check Signal / Monitor
                if self.active_position:
                    self.monitor_active_position(spot_ltp)
                else:
                    # Check for Breakout if pattern active
                    signal = self.analyzer.check_breakout(spot_ltp)
                    if signal:
                        self.execute_entry(signal)
                        
                time.sleep(5) # 1s poll might be too fast, 5s is fine
                
            except KeyboardInterrupt:
                log_core("Stopping Strategy...")
                break
            except Exception as e:
                logger.error(f"[CORE] Error in main loop: {e}")
                time.sleep(5)

if __name__ == "__main__":
    if not check_existing_token():
        perform_authentication()
        
    with open("lib/core/accessToken.txt", "r") as f: token = f.read().strip()
    nse_data = download_nse_market_data()
    
    strategy = InsideCandleLive(token, nse_data, dry_run=True) # Defaulting to Dry Run for safety
    strategy.run()

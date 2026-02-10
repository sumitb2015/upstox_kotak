"""
VWAP Straddle Strategy v2 - Live Trading Implementation

STRATEGY OVERVIEW
-----------------
This is a non-directional strategy that sells an ATM Straddle (CE + PE) when the 
combined premium (CP) shows specific decay signals relative to VWAP and previous 
day's lows. It uses a "combined premium" approach where both legs are treated 
as a single unit for indicator calculation and risk management.

LOGIC SUMMARY
-------------
1. SELECTION:
   - Instrument: NIFTY 50 (Atm Strike).
   - Expiry: Nearest Weekly Expiry.
   - Entry Time: 09:20 AM (Configurable).

2. ENTRY CONDITIONS:
   - CP < Previous Day Combined Low (Trend confirmation of decay).
   - CP < VWAP (Calculated on Combined Premium and Total Volume).
   - Skew Filter: Initial width between CE and PE must be < 'max_straddle_width_pct' (Default 20%).
     (Ensures we don't enter during extreme one-sided spikes).

3. MONITORING & INDICATORS:
   - Combined Premium (CP): Close_CE + Close_PE.
   - Combined VWAP: sum(CP * Total_Volume) / sum(Total_Volume).
   - Real-Time: Uses WebSockets for per-second P&L and TSL monitoring.

4. EXIT CONDITIONS:
   - Stop Loss (SL): CP > Entry Price + 'stop_loss_points' (Default 30 pts).
   - Trailing SL (TSL): CP > Lowest CP reached + 'trailing_sl_points' (Default 20 pts).
   - VWAP Reversal: CP crosses above VWAP (Signal that decay has stalled/reversed).
   - Skew Exit: Individual leg divergence > 'max_skew_exit_pct' (Default 60%).
   - Time Exit: 15:15 PM (Intraday Square-off).

5. RISK MANAGEMENT:
   - Max Straddle Width: Prevents entry if premiums are too asymmetric.
   - Trailing Profit Lock: Uses a trailing stop based on the lowest premium reached.
   - Product Type: MIS (Intraday).
"""

import sys
import os
import time
import pandas as pd
from datetime import datetime, timedelta, time as dt_time
import logging

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'kotak_api'))) # Removed to avoid shadowing 'lib'

from strategies.non_directional.vwap_straddle_v2.core import VWAPStraddleCore
from lib.api.market_data import download_nse_market_data
from lib.api.historical import get_historical_data, get_intraday_data_v3
from lib.api.option_chain import get_option_chain_dataframe, get_atm_strike_from_chain, get_nearest_expiry
from lib.utils.instrument_utils import get_option_instrument_key
from kotak_api.lib.broker import BrokerClient
from kotak_api.lib.order_manager import OrderManager
from kotak_api.lib.trading_utils import get_strike_token, get_lot_size

# Logger setup
logger = logging.getLogger("VWAPStraddleLive")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

class VWAPStraddleLive(VWAPStraddleCore):
    """
    Live trading implementation of VWAP Straddle Strategy.
    """
    
    def __init__(self, access_token: str, config: dict):
        # Initialize Core Logic
        super().__init__(config)
        
        self.access_token = access_token
        self.dry_run = config.get('dry_run', False)
        self.candle_interval = config.get('candle_interval_minutes', 5)
        self.entry_time_str = config.get('entry_time', "09:20")
        self.exit_time_str = config.get('exit_time', "15:15")
        
        # Parse times
        self.entry_time = datetime.strptime(self.entry_time_str, "%H:%M").time()
        self.exit_time = datetime.strptime(self.exit_time_str, "%H:%M").time()
        
        # Components
        self.kotak_broker = None
        self.kotak_order_manager = None
        
        # State
        self.atm_strike = None
        self.ce_key = None
        self.pe_key = None
        self.ce_symbol = None
        self.pe_symbol = None
        self.is_running = False
        self.positions_open = False
        
        # Cache
        self.df_cache = pd.DataFrame()
        self.ltp_cache = {}
        self.streamer = None
        self.use_websockets = config.get('use_websockets', True)

    def initialize(self):
        """Initialize connections and strategy state."""
        logger.info("🚀 Initializing VWAP Straddle Strategy (Live)...")
        
        # 1. Kotak Authentication
        try:
            logger.info("🔐 Authenticating Kotak Neo...")
            self.kotak_broker = BrokerClient()
            self.kotak_broker.authenticate()
            self.kotak_broker.load_master_data()
            self.kotak_order_manager = OrderManager(self.kotak_broker.client, dry_run=self.dry_run)
            logger.info("✅ Kotak Connected")
        except Exception as e:
            logger.error(f"❌ Kotak Auth Failed: {e}")
            return False
            
        # 2. ATM Selection (Wait for market data if needed)
        if not self._select_atm_contracts():
            return False
            
        # 3. Previous Day Logic
        if not self._calculate_prev_day_metrics():
            logger.warning("⚠️ Could not calculate Prev Day metrics. Strategy may not enter if conditions require it.")
            if self.prev_day_cp_low == float('inf'):
                 logger.error("❌ Prev Day Low is infinite. Cannot proceed.")
                 return False

        # 4. Initialize WebSocket Streamer
        if self.use_websockets:
            from lib.api.streaming import UpstoxStreamer
            logger.info("📡 Connecting to Upstox Market Data Feed...")
            try:
                self.streamer = UpstoxStreamer(self.access_token)
                self.streamer.connect_market_data(
                    instrument_keys=[self.ce_key, self.pe_key],
                    mode="ltpc",
                    on_message=self.on_market_data
                )
                logger.info("⏳ Waiting for WebSocket connection...")
                for _ in range(5):
                    time.sleep(1)
                    if self.streamer.market_data_connected:
                        logger.info("✅ WebSocket connection confirmed")
                        break
                else:
                    logger.warning("⚠️ WebSocket not confirmed within 5s, proceeding anyway...")
            except Exception as e:
                logger.error(f"❌ WebSocket Initialization Failed: {e}")
                self.use_websockets = False
                 
        logger.info("✅ Initialization Complete")
        return True

    def on_market_data(self, data):
        try:
            # logger.info(f"DEBUG: Received Data: {data}")
            # Handle both Object and Dict formats
            # data structure: {'feeds': {'key': {'ltpc': {'ltp': ...}}}} or Object with .feeds
            
            feeds = None
            if hasattr(data, 'feeds'):
                feeds = data.feeds
            elif isinstance(data, dict) and 'feeds' in data:
                feeds = data['feeds']
            
            if feeds:
                for key, feed in feeds.items():
                    ltp = None
                    # Try Object access
                    if hasattr(feed, 'ltpc') and feed.ltpc:
                         # Check if ltpc is object or dict
                         if hasattr(feed.ltpc, 'ltp'):
                            ltp = feed.ltpc.ltp
                         elif isinstance(feed.ltpc, dict) and 'ltp' in feed.ltpc:
                            ltp = feed.ltpc['ltp']
                            
                    elif hasattr(feed, 'ff') and feed.ff: # Full Feed try
                         if hasattr(feed.ff, 'marketFF') and feed.ff.marketFF:
                              ltp = feed.ff.marketFF.ltp
                    
                    # Try Dict access
                    if ltp is None and isinstance(feed, dict):
                         if 'ltpc' in feed and 'ltp' in feed['ltpc']:
                              ltp = feed['ltpc']['ltp']
                         elif 'ff' in feed and 'marketFF' in feed['ff'] and 'ltp' in feed['ff']['marketFF']:
                              ltp = feed['ff']['marketFF']['ltp']

                    if ltp is not None:
                        self.ltp_cache[key] = float(ltp)
                        
        except Exception as e:
            logger.error(f"Error in on_market_data: {e}")

    def _select_atm_contracts(self):
        """Find ATM strike and resolve keys."""
        logger.info("🔍 Selecting ATM Contracts...")
        
        # Get Option Chain for NIFTY
        expiry = get_nearest_expiry(self.access_token)
        
        # Fetch detailed chain from Upstox
        try:
            chain_df = get_option_chain_dataframe(self.access_token, "NSE_INDEX|Nifty 50", expiry)
            if chain_df is None or chain_df.empty:
                logger.error("❌ Failed to fetch Option Chain")
                return False
                
            self.atm_strike = get_atm_strike_from_chain(chain_df)
            spot = chain_df['spot_price'].iloc[0]
            logger.info(f"🎯 Spot: {spot:.2f} | ATM: {self.atm_strike}")
            
            # Extract keys from chain_df
            atm_row = chain_df[chain_df['strike_price'] == self.atm_strike]
            if atm_row.empty:
                logger.error("❌ ATM Strike not found in chain")
                return False
                
            self.ce_key = atm_row.iloc[0]['ce_key']
            self.pe_key = atm_row.iloc[0]['pe_key']
            
            # Resolve Kotak Symbols
            if isinstance(expiry, str):
                expiry_dt = datetime.strptime(expiry, "%Y-%m-%d")
            else:
                # If it's already a date or datetime
                expiry_dt = datetime.combine(expiry, datetime.min.time()) if hasattr(expiry, 'year') and not hasattr(expiry, 'hour') else expiry
                
            _, self.ce_symbol = get_strike_token(self.kotak_broker, self.atm_strike, "CE", expiry_dt)
            _, self.pe_symbol = get_strike_token(self.kotak_broker, self.atm_strike, "PE", expiry_dt)
            
            logger.info(f"✅ Selected: CE {self.ce_symbol} ({self.ce_key}) | PE {self.pe_symbol} ({self.pe_key})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Contract Selection Failed: {e}")
            return False

    def _calculate_prev_day_metrics(self):
        """Fetch historical data to find prev day low."""
        logger.info("📊 Calculating Previous Day Metrics...")
        
        prev_date = datetime.now() - timedelta(days=1)
        # Handle weekends
        while prev_date.weekday() >= 5:
            prev_date -= timedelta(days=1)
            
        date_str = prev_date.strftime("%Y-%m-%d")
        
        # Fetch 1-min data
        ce_hist = self.fetch_data_historical(self.ce_key, date_str)
        pe_hist = self.fetch_data_historical(self.pe_key, date_str)
        
        if not ce_hist or not pe_hist: 
            logger.error(f"❌ No historical data for {date_str}")
            return False
            
        # Convert to DF
        df_ce = pd.DataFrame(ce_hist).set_index('timestamp')
        df_pe = pd.DataFrame(pe_hist).set_index('timestamp')
        
        # Join
        df = df_ce.join(df_pe, lsuffix='_ce', rsuffix='_pe', how='inner')
        
        # Use Core Logic
        self.prev_day_cp_low = self.calculate_prev_day_low(df)
        logger.info(f"📉 Prev Day Combined Low ({date_str}): {self.prev_day_cp_low:.2f}")
        return True

    def fetch_data(self, instrument_key: str):
        """Fetch Intra-day data for live monitoring."""
        return get_intraday_data_v3(
            self.access_token, 
            instrument_key, 
            "minutes", 
            self.candle_interval
        )

    def fetch_data_historical(self, instrument_key: str, date_str: str):
        """Adapter for historical data used in init."""
        return get_historical_data(
            self.access_token,
            instrument_key,
            "1minute",
            1 # days back (approx, utility handles ranges actually but using simple call here)
        )

    def execute_trade(self, action: str, ce_symbol: str = None, pe_symbol: str = None):
        """Execute orders via Kotak with atomic entry/exit and rollback. Returns (success, ce_price, pe_price)."""
        if action == "ENTRY":
            logger.info("⚡ Executing ENTRY Orders (Atomic)...")
            qty = self.lot_size
            
            # Step 1: Place CE order
            ce_oid = self.kotak_order_manager.place_order(
                self.ce_symbol, qty, "S", tag="VWAP_ENTRY", product="MIS"
            )
            
            if ce_oid:
                logger.info(f"✅ CE Entry Order Placed: {ce_oid}")
                
                # Get actual CE execution price
                ce_exec_price = self.kotak_order_manager.get_execution_price(ce_oid)
                logger.info(f"📊 CE Execution Price: ₹{ce_exec_price:.2f}")
                
                # Step 2: Place PE order
                pe_oid = self.kotak_order_manager.place_order(
                    self.pe_symbol, qty, "S", tag="VWAP_ENTRY", product="MIS"
                )
                
                if pe_oid:
                    logger.info(f"✅ PE Entry Order Placed: {pe_oid}")
                    
                    # Get actual PE execution price
                    pe_exec_price = self.kotak_order_manager.get_execution_price(pe_oid)
                    logger.info(f"📊 PE Execution Price: ₹{pe_exec_price:.2f}")
                    logger.info("✅ Both legs entered successfully")
                    
                    self.positions_open = True
                    return (True, ce_exec_price, pe_exec_price)
                else:
                    # PE failed - Rollback CE
                    logger.error("❌ PE Entry Order FAILED. Rolling back CE position...")
                    rollback_oid = self.kotak_order_manager.place_order(
                        self.ce_symbol, qty, "B", tag="VWAP_ROLLBACK", product="MIS"
                    )
                    if rollback_oid:
                        logger.info(f"✅ CE Rollback successful: {rollback_oid}")
                    else:
                        logger.error("❌ CRITICAL: CE Rollback FAILED. Manual intervention required!")
                    return (False, 0.0, 0.0)
            else:
                logger.error("❌ CE Entry Order FAILED. Aborting entry.")
                return (False, 0.0, 0.0)
            
        elif action == "EXIT":
            logger.info("🛑 Executing EXIT Orders...")
            qty = self.lot_size
            
            ce_oid = self.kotak_order_manager.place_order(
                self.ce_symbol, qty, "B", tag="VWAP_EXIT", product="MIS"
            )
            pe_oid = self.kotak_order_manager.place_order(
                self.pe_symbol, qty, "B", tag="VWAP_EXIT", product="MIS"
            )
            
            ce_exit_price = 0.0
            pe_exit_price = 0.0
            
            if ce_oid:
                ce_exit_price = self.kotak_order_manager.get_execution_price(ce_oid)
                logger.info(f"✅ CE Exit Order: {ce_oid} @ ₹{ce_exit_price:.2f}")
            else:
                logger.error("❌ CE Exit Order FAILED")
                
            if pe_oid:
                pe_exit_price = self.kotak_order_manager.get_execution_price(pe_oid)
                logger.info(f"✅ PE Exit Order: {pe_oid} @ ₹{pe_exit_price:.2f}")
            else:
                logger.error("❌ PE Exit Order FAILED")
            
            # Mark positions as closed even if one leg fails
            # (Manual reconciliation needed for partial exits)
            if ce_oid or pe_oid:
                self.positions_open = False
                if not (ce_oid and pe_oid):
                    logger.warning("⚠️ Partial exit occurred. Manual reconciliation required.")
                return (True, ce_exit_price, pe_exit_price)
            else:
                logger.error("❌ Both exit orders failed!")
                return (False, 0.0, 0.0)

    def run(self):
        """Main Strategy Loop."""
        self.is_running = True
        logger.info("🎬 Strategy Loop Started")
        
        while self.is_running:
            try:
                now = datetime.now()
                
                # Check Time Boundaries
                if now.time() < self.entry_time:
                    sleep_sec = 60
                    logger.info(f"⏳ Waiting for start time {self.entry_time_str}...")
                    time.sleep(sleep_sec)
                    continue
                    
                if now.time() >= self.exit_time:
                    logger.info("⏰ Exit Time Reached. Closing positions if any.")
                    if self.positions_open:
                       self.execute_trade("EXIT")
                    break

                # Main Logic Interval
                # Fetch Data
                ce_candles = self.fetch_data(self.ce_key)
                pe_candles = self.fetch_data(self.pe_key)
                
                if not ce_candles or not pe_candles:
                    logger.warning("⚠️ Waiting for data...")
                    time.sleep(10)
                    continue
                    
                # Process Data
                df_ce = pd.DataFrame(ce_candles).set_index('timestamp')
                df_pe = pd.DataFrame(pe_candles).set_index('timestamp')
                
                # Inner Join to align timestamps
                df = df_ce.join(df_pe, lsuffix='_ce', rsuffix='_pe', how='inner')
                
                if df.empty:
                    time.sleep(10)
                    continue
                    
                # Shared Calculations
                df['vwap'] = self.calculate_vwap(df)
                
                latest = df.iloc[-1]
                cp = latest['close_ce'] + latest['close_pe']
                vwap = latest['vwap']
                
                logger.info(f"📊 State: CP {cp:.2f} | VWAP {vwap:.2f} | PrevLow {self.prev_day_cp_low:.2f}")

                # Entry/Exit Logic
                if not self.positions_open:
                    should_enter, reason = self.validate_entry_conditions(
                        cp, vwap, self.prev_day_cp_low, latest['close_ce'], latest['close_pe']
                    )
                    
                    if should_enter:
                        logger.info(f"✅ ENTRY SIGNAL: {reason}")
                        # Execute trade first, then record entry only if successful
                        success, ce_exec_price, pe_exec_price = self.execute_trade("ENTRY")
                        if success:
                            # Use actual execution prices instead of market quotes
                            actual_combined_premium = ce_exec_price + pe_exec_price
                            self.record_entry(actual_combined_premium)
                            logger.info(f"📊 Entry Recorded: CE ₹{ce_exec_price:.2f} + PE ₹{pe_exec_price:.2f} = ₹{actual_combined_premium:.2f}")
                        else:
                            logger.error("❌ Entry failed. Skipping record_entry.")
                    else:
                         logger.info(f"⏳ No Entry: {reason}")
                else:
                    # POSITIONS OPEN: Check exits
                    # 1. Check Candle-Close Exits first (Standard)
                    exit_reason, details = self.check_exit_conditions(
                        cp, vwap, self.entry_price_combined, latest['close_ce'], latest['close_pe']
                    )
                    
                    if exit_reason:
                        logger.info(f"🛑 EXIT SIGNAL (Candle): {exit_reason} ({details})")
                        self.execute_trade("EXIT")
                        break
                
                # Status / Heartbeat Wait Loop (Real-Time Monitoring)
                sleep_seconds = self.candle_interval * 60
                check_interval = 1 # Tick check every 1s
                
                for i in range(0, sleep_seconds, check_interval):
                    if not self.is_running: break
                    remaining = sleep_seconds - i
                    
                    # ----------------------------------------------
                    # Real-Time Tick Monitoring
                    # ----------------------------------------------
                    if self.positions_open and self.use_websockets:
                        ce_ltp = self.ltp_cache.get(self.ce_key)
                        pe_ltp = self.ltp_cache.get(self.pe_key)
                        
                        if ce_ltp and pe_ltp:
                            live_cp = ce_ltp + pe_ltp
                            
                            # Check Exits using LIVE price vs Candle VWAP
                            # Note: check_exit_conditions updates lowest_cp state!
                            exit_reason, details = self.check_exit_conditions(
                                live_cp, vwap, self.entry_price_combined, ce_ltp, pe_ltp
                            )
                            
                            if exit_reason:
                                logger.info(f"🛑 EXIT SIGNAL (Tick): {exit_reason} ({details})")
                                self.execute_trade("EXIT")
                                self.is_running = False # Stop after exit
                                break
                            
                            # Update Status Message with Live Data
                            status_msg = f"🦄 LIVE | CP: {live_cp:.2f} (L: {self.lowest_cp_since_entry:.2f})"
                            tsl_level = self.lowest_cp_since_entry + self.trailing_sl_points
                            pnl = (self.entry_price_combined - live_cp) * self.lot_size
                            status_msg += f" | PnL: {pnl:+.0f} | TSL: {tsl_level:.2f}"
                        else:
                            status_msg = f"⚠️ Waiting for Ticks..."
                    else:
                        # Fallback Status
                        status_msg = f"💓 Monitor | CP: {cp:.2f} | VWAP: {vwap:.2f}"
                        if self.positions_open:
                             pnl = (self.entry_price_combined - cp) * self.lot_size
                             status_msg += f" | PnL: {pnl:+.0f}"
                    
                    if True: # Log every second as requested
                         logger.info(f"{status_msg} | Candle In: {remaining}s")
                         
                    time.sleep(check_interval)
                
            except KeyboardInterrupt:
                logger.info("👋 User Stopped Strategy")
                self.is_running = False
            except Exception as e:
                logger.error(f"❌ Loop Error: {e}")
                time.sleep(10)

if __name__ == "__main__":
    # Load Token
    from lib.core.authentication import get_access_token
    access_token = get_access_token()
    
    if not access_token:
        logger.error("❌ Failed to retrieve valid Upstox Access Token")
        sys.exit(1)
        
    config = {
        'lot_size': 65, # 1 Lots
        'stop_loss_points': 30.0,
        'max_straddle_width_pct': 0.20,
        'max_skew_exit_pct': 0.60,
        'candle_interval_minutes': 5,
        'entry_time': "09:20",
        'dry_run': False,
        'use_websockets': True  # Set to False to disable Tick Monitoring
    }
    
    strategy = VWAPStraddleLive(access_token, config)
    if strategy.initialize():
        strategy.run()

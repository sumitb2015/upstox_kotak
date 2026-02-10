
"""
RSI VWAP Strangle Strategy - Live Implementation

Strategy Logic Summary:
-----------------------
1. Entry Conditions:
   - RSI (14, 5min) must be between 40 and 60 (Consolidation).
   - Value Check: Combined Premium (CE+PE) < Combined Intraday VWAP (CE+PE).
   - Strike Selection: CE and PE strikes closest to TARGET_PREMIUM.

2. Exit Conditions:
   - Target Profit: Exit leg if profit reaches 50% of collected premium.
   - Stop Loss: 20% of Entry Price per leg.
   - Time Based: Intraday square-off at EXIT_TIME (Default: 15:18).

3. Risk Management:
   - Stop Loss: Hard SL of 20% on each leg. Supports SL Hardening (locks to cost at 15% profit) and TSL (trails price at 20% buffer).
   - Re-entry: If a leg hits SL (Naked state), monitor its price. Re-enter if price returns to the mid-point of entry and exit.
     - On Re-entry: Update Entry Price to current LTP.
   - Pyramiding: 
     - Trigger: If position is Naked and Profit on active leg increases by 10% *from the moment it became naked*.
     - Action: Add 1 Lot (Max 3 adds total).
   - Atomic Execution: Uses rollback logic to ensure both legs are filled or none.

4. State Persistence:
   - Saves state to 'rsi_strangle_state.json' for crash recovery.
"""

import sys
import os
import time
import logging
import json
from datetime import datetime, time as dt_time, timedelta
from typing import Optional, Tuple, Dict, List

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

# Import configuration
from strategies.non_directional.rsi_vwap_strangle.config import *

# Import library functions
from lib.core.authentication import check_existing_token
from lib.api.market_data import download_nse_market_data
from lib.api.option_chain import get_option_chain_dataframe, get_atm_strike_from_chain
from lib.utils.expiry_cache import get_expiry_for_strategy
from lib.api.streaming import UpstoxStreamer
from lib.api.historical import get_historical_data, get_intraday_data_v3
from lib.utils.indicators import calculate_rsi, calculate_vwap
import pandas as pd
import numpy as np

# Kotak API Imports
from kotak_api.lib.broker import BrokerClient
from kotak_api.lib.order_manager import OrderManager
from kotak_api.lib.trading_utils import get_strike_token, get_lot_size

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("rsi_vwap_strangle.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

logger = logging.getLogger(__name__)

class Position:
    def __init__(self, ce_symbol, pe_symbol, ce_entry, pe_entry, ce_qty, pe_qty, ce_strike, pe_strike):
        self.ce_symbol = ce_symbol
        self.pe_symbol = pe_symbol
        self.ce_entry_price = ce_entry
        self.pe_entry_price = pe_entry
        self.ce_qty = ce_qty
        self.pe_qty = pe_qty
        self.ce_strike = ce_strike
        self.pe_strike = pe_strike
        
        # Initial Quantities (for Pyramid Reduction)
        self.initial_ce_qty = ce_qty
        self.initial_pe_qty = pe_qty
        
        # State
        self.ce_sl_hit = False
        self.pe_sl_hit = False
        self.saved_ce_open = 0.0
        self.saved_pe_open = 0.0
        self.ce_reentry_armed = False  # Tracks if price has moved above trigger
        self.pe_reentry_armed = False  # Tracks if price has moved above trigger
        
        # Pyramiding
        self.pyramid_count = 0
        self.last_pyramid_profit_pct = 0.0
        
        # Current Prices (updated via Websocket)
        self.ce_ltp = ce_entry
        self.pe_ltp = pe_entry
        
        # Stop Loss Prices (Dynamic for TSL)
        self.ce_sl_price = ce_entry * (1 + SL_PCT)
        self.pe_sl_price = pe_entry * (1 + SL_PCT)
        
        # Naked state reference for Pyramiding
        self.naked_ref_price = 0.0

        # P&L Tracking
        self.realized_pnl = 0.0

    @property
    def is_naked(self):
        """A position is naked if exactly one leg is open."""
        return (self.ce_qty > 0 and self.pe_qty == 0) or (self.pe_qty > 0 and self.ce_qty == 0)

    @property
    def is_closed(self):
        return self.ce_sl_hit and self.pe_sl_hit

class RSIVWAPStrangle:
    def __init__(self, upstox_token: str):
        self.upstox_token = upstox_token
        self.nse_data = None
        self.expiry_dt = None
        self.expiry_obj = None
        self.position: Optional[Position] = None
        self.upstox_streamer = None
        
        # Kotak components
        self.kotak_broker = BrokerClient()
        self.kotak_client = None
        self.order_mgr = None
        
        # Instrument Keys for Mapping
        self.ce_token_map = {} # Symbol -> Key
        self.pe_token_map = {} # Symbol -> Key
        
        # Dynamic Recovery % based on DTE
        self.dynamic_recovery_pct = REENTRY_RECOVERY_PCT
        self.upstox_key_map = {} # Upstox Key -> Symbol
        
        # Logging State
        self.last_status_log_time = 0
        self.last_heartbeat_time = 0

    def initialize(self):
        logger.info("="*80)
        logger.info("🚀 [CORE] Initializing RSI VWAP Strangle Strategy")
        logger.info("="*80)
        
        # Validate Config
        if TARGET_PREMIUM <= 0 or SL_PCT <= 0:
            logger.error("❌ [CORE] Invalid Config: TARGET_PREMIUM and SL_PCT must be positive")
            sys.exit(1)
        
        # Load Data
        logger.info("📊 [UPSTOX] Loading NSE market data...")
        self.nse_data = download_nse_market_data()
        
        # Determine Short Symbol for Expiry Cache
        short_symbol = "NIFTY"
        if "Bank" in INDEX_NAME: short_symbol = "BANKNIFTY"
        elif "Fin" in INDEX_NAME: short_symbol = "FINNIFTY"
        self.short_symbol = short_symbol
        
        self.expiry_dt = get_expiry_for_strategy(self.upstox_token, "current_week", short_symbol)
        if isinstance(self.expiry_dt, str):
            self.expiry_obj = datetime.strptime(self.expiry_dt, '%Y-%m-%d')
        else:
            self.expiry_obj = self.expiry_dt
            self.expiry_dt = self.expiry_obj.strftime('%Y-%m-%d')
            
        
        # Calculate DTE and set Dynamic Recovery Percentage
        today_date = datetime.now().date()
        dte = (self.expiry_obj.date() - today_date).days
        
        if dte <= 0:
            self.dynamic_recovery_pct = 0.20 # 20% on Expiry Day
        elif dte == 1:
            self.dynamic_recovery_pct = 0.15 # 15% on Day before Expiry
        elif dte == 2:
            self.dynamic_recovery_pct = 0.10 # 10% on T-2
        else:
            self.dynamic_recovery_pct = 0.05 # 5% on T-3 or more
            
        logger.info(f"📅 [CORE] DTE: {dte} days. Set Dynamic Re-entry Recovery to {self.dynamic_recovery_pct*100:.0f}%")
        
        logger.info(f"📅 [UPSTOX] Expiry identified: {self.expiry_dt} ({short_symbol})")
        
        # Setup Kotak
        logger.info("🔐 [KOTAK] Authenticating...")
        self.kotak_client = self.kotak_broker.authenticate()
        self.kotak_broker.load_master_data()
        self.order_mgr = OrderManager(self.kotak_client, dry_run=DRY_RUN)
        
        # Setup Upstox Streamer
        self.upstox_streamer = UpstoxStreamer(self.upstox_token)

    def get_strikes_by_premium(self, target_premium: float) -> Tuple[Optional[int], Optional[int]]:
        """Find strikes closest to target premium"""
        chain_df = get_option_chain_dataframe(self.upstox_token, INDEX_NAME, self.expiry_dt)
        if chain_df is None or chain_df.empty:
            return None, None
            
        # Find closest CE
        chain_df['ce_diff'] = abs(chain_df['ce_ltp'] - target_premium)
        ce_row = chain_df.sort_values('ce_diff').iloc[0]
        ce_strike = int(ce_row['strike_price'])
        
        # Find closest PE
        chain_df['pe_diff'] = abs(chain_df['pe_ltp'] - target_premium)
        pe_row = chain_df.sort_values('pe_diff').iloc[0]
        pe_strike = int(pe_row['strike_price'])
        
        logger.info(f"🎯 [CORE] Selected Strikes for Premium {target_premium}: CE {ce_strike} (₹{ce_row['ce_ltp']}), PE {pe_strike} (₹{pe_row['pe_ltp']})")
        return ce_strike, pe_strike

    def check_rsi_condition(self) -> bool:
        """Check if RSI(14) is between 40 and 60 on the configured timeframe"""
        try:
            # 1. Fetch Historical Data (Previous Days)
            # Fetch 5 days of 1-minute data for a strong baseline
            hist_candles = get_historical_data(self.upstox_token, INDEX_NAME, "minute", lookback_minutes=2000)
            
            # 2. Fetch Intraday Data (Today)
            intra_candles = get_intraday_data_v3(self.upstox_token, INDEX_NAME, "minute", 1)
            
            if not hist_candles and not intra_candles: 
                logger.warning("⚠️ [CORE] No historical or intraday data available for RSI")
                return False
            
            # 3. Process Historical
            df_hist = pd.DataFrame(hist_candles) if hist_candles else pd.DataFrame()
            if not df_hist.empty:
                df_hist['timestamp'] = pd.to_datetime(df_hist['timestamp'])
                # Upstox V3 historical timestamps are usually in ISO format with offset
                # If not, assume UTC and convert
                if df_hist['timestamp'].dt.tz is None:
                    df_hist['timestamp'] = df_hist['timestamp'].dt.tz_localize('UTC').dt.tz_convert('Asia/Kolkata')
                else:
                    df_hist['timestamp'] = df_hist['timestamp'].dt.tz_convert('Asia/Kolkata')
            
            # 4. Process Intraday
            df_intra = pd.DataFrame(intra_candles) if intra_candles else pd.DataFrame()
            if not df_intra.empty:
                df_intra['timestamp'] = pd.to_datetime(df_intra['timestamp'])
                if df_intra['timestamp'].dt.tz is None:
                    df_intra['timestamp'] = df_intra['timestamp'].dt.tz_localize('UTC').dt.tz_convert('Asia/Kolkata')
                else:
                    df_intra['timestamp'] = df_intra['timestamp'].dt.tz_convert('Asia/Kolkata')
            
            # 5. Merge and Deduplicate
            if not df_hist.empty and not df_intra.empty:
                # Use start of today to clean history
                start_of_today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).astimezone(df_hist['timestamp'].dt.tz)
                df_hist = df_hist[df_hist['timestamp'] < start_of_today]
                df_merged = pd.concat([df_hist, df_intra]).sort_values('timestamp').drop_duplicates('timestamp')
            else:
                df_merged = df_intra if not df_intra.empty else df_hist
            
            if df_merged.empty: return False
                
            # 6. Resample to Target Timeframe (e.g., "3minute" -> "3min")
            try:
                interval_min = int(''.join(filter(str.isdigit, RSI_TIMEFRAME)))
                resample_rule = f"{interval_min}min"
            except Exception as e:
                logger.warning(f"⚠️ [CORE] Could not parse RSI_TIMEFRAME: {e}. Defaulting to 5min.")
                resample_rule = "5min"
            
            df_merged.set_index('timestamp', inplace=True)
            df_resampled = df_merged.resample(resample_rule).agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }).dropna()
            
            if len(df_resampled) <= RSI_PERIOD:
                logger.warning(f"⚠️ [CORE] Not enough candles for RSI calculation (Need {RSI_PERIOD}, got {len(df_resampled)})")
                return False
            
            # 7. Calculate RSI
            last_candle_ts = df_resampled.index[-1]
            rsi = calculate_rsi(df_resampled, period=RSI_PERIOD)
            
            logger.info(f"📊 [CORE] Current RSI({RSI_PERIOD}) [Last Candle: {last_candle_ts.strftime('%H:%M')}]: {rsi:.2f}")
            
            return RSI_MIN <= rsi <= RSI_MAX
            
        except Exception as e:
            logger.error(f"❌ [CORE] RSI Calculation Error: {e}")
            import traceback
            traceback.print_exc()
            return False

    def check_vwap_condition(self, ce_key: str, pe_key: str, ce_ltp: float, pe_ltp: float) -> bool:
        """Check if Combined Premium < Combined VWAP"""
        try:
            # We use get_intraday_data_v3 for VWAP as it needs volume from start of day
            # Get Intraday Data for CE
            ce_candles = get_intraday_data_v3(self.upstox_token, ce_key, "minute", 1)
            pe_candles = get_intraday_data_v3(self.upstox_token, pe_key, "minute", 1)
            
            if not ce_candles or not pe_candles:
                logger.warning("⚠️ [UPSTOX] Could not fetch intraday data for VWAP check")
                return False
                
            ce_df = pd.DataFrame(ce_candles)
            pe_df = pd.DataFrame(pe_candles)
            
            ce_vwap = calculate_vwap(ce_df)
            pe_vwap = calculate_vwap(pe_df)
            
            combined_premium = ce_ltp + pe_ltp
            combined_vwap = ce_vwap + pe_vwap
            
            logger.info(f"💰 [CORE] Value Check: Premium {combined_premium:.2f} vs VWAP {combined_vwap:.2f}")
            
            return combined_premium < combined_vwap
            
        except Exception as e:
            logger.error(f"❌ [CORE] Error checking VWAP: {e}")
            return False

    def enter_strategy(self):
        logger.info("="*80)
        logger.info("🚀 [CORE] Attempting Entry...")
        
        # 1. Select Strikes
        ce_strike, pe_strike = self.get_strikes_by_premium(TARGET_PREMIUM)
        if not ce_strike or not pe_strike: 
            logger.warning("⚠️ [CORE] Could not select strikes")
            return
        
        # 2. Get Keys/Symbols
        from lib.utils.instrument_utils import get_option_instrument_key
        ce_key = get_option_instrument_key(self.short_symbol, ce_strike, "CE", self.nse_data)
        pe_key = get_option_instrument_key(self.short_symbol, pe_strike, "PE", self.nse_data)
        
        # Kotak usually defaults NIFTY symbols correctly, but we can pass symbol just in case
        ce_token, ce_symbol = get_strike_token(self.kotak_broker, ce_strike, "CE", self.expiry_obj, symbol=self.short_symbol)
        pe_token, pe_symbol = get_strike_token(self.kotak_broker, pe_strike, "PE", self.expiry_obj, symbol=self.short_symbol)

        
        if not ce_key or not pe_key or not ce_symbol or not pe_symbol:
            logger.error("❌ [CORE] Failed to resolve keys/symbols")
            return

        # 3. Get LTPs (Snapshot)
        chain_df = get_option_chain_dataframe(self.upstox_token, INDEX_NAME, self.expiry_dt)
        ce_ltp = chain_df[chain_df['strike_price'] == ce_strike].iloc[0]['ce_ltp']
        pe_ltp = chain_df[chain_df['strike_price'] == pe_strike].iloc[0]['pe_ltp']
        
        # 4. Check Conditions
        if not self.check_rsi_condition():
            logger.info("⏳ [CORE] RSI Conditions not met")
            return
            
        if not self.check_vwap_condition(ce_key, pe_key, ce_ltp, pe_ltp):
            logger.info("⏳ [CORE] VWAP Conditions not met (Premium > VWAP)")
            return
            
        logger.info("✅ [CORE] All Entry Conditions Met! Executing Strangle.")
        
        # 5. ATOMIC EXECUTION w/ Rollback
        # User mandate: "Strategy entering multiple legs MUST implement Atomic Execution with Rollback logic"
        
        qty = get_lot_size(self.kotak_broker.master_df, ce_symbol) * 1 
        executed_legs = []
        
        try:
            # Place Leg 1: CE
            logger.info(f"🚀 [KOTAK] Placing CE Order: {ce_symbol} x {qty}")
            ce_oid = self.order_mgr.place_order(ce_symbol, qty, "S", tag="RSI_Strangle_Entry")
            
            if ce_oid:
                executed_legs.append({'symbol': ce_symbol, 'qty': qty, 'type': 'S'})
                
                # Place Leg 2: PE
                logger.info(f"🚀 [KOTAK] Placing PE Order: {pe_symbol} x {qty}")
                pe_oid = self.order_mgr.place_order(pe_symbol, qty, "S", tag="RSI_Strangle_Entry")
                
                if pe_oid:
                    executed_legs.append({'symbol': pe_symbol, 'qty': qty, 'type': 'S'})
            
            # Validation
            if len(executed_legs) < 2:
                logger.error("❌ [CORE] Atomic Execution Failed! Rolling back positions...")
                for leg in executed_legs:
                    logger.warning(f"⏪ [KOTAK] Rolling back {leg['symbol']}...")
                    # Reverse Type
                    exit_type = "B" if leg['type'] == "S" else "S"
                    self.order_mgr.place_order(leg['symbol'], leg['qty'], exit_type, tag="Rollback")
                return # Exit without position object

            # Success
            self.position = Position(ce_symbol, pe_symbol, ce_ltp, pe_ltp, qty, qty, ce_strike, pe_strike)
            
            # Map keys for streaming
            self.upstox_key_map[ce_key] = ce_symbol
            self.upstox_key_map[pe_key] = pe_symbol
            self.ce_token_map[ce_symbol] = ce_key
            self.pe_token_map[pe_symbol] = pe_key
            
            # Start Streaming
            self.start_streaming([ce_key, pe_key])
            
            logger.info("✅ [CORE] Strangle Entered Successfully (Atomic)")
            
        except Exception as e:
            logger.error(f"❌ [CORE] Execution Exception: {e}")
            # Rollback any executed
            for leg in executed_legs:
                logger.warning(f"⏪ [KOTAK] Rolling back {leg['symbol']}...")
                exit_type = "B" if leg['type'] == "S" else "S"
                self.order_mgr.place_order(leg['symbol'], leg['qty'], exit_type, tag="Rollback")

    def show_current_conditions_snapshot(self):
        """Show current RSI and VWAP status for user feedback (Heartbeat)"""
        try:
            # Re-use signal logic for feedback
            ce_strike, pe_strike = self.get_strikes_by_premium(TARGET_PREMIUM)
            if not ce_strike or not pe_strike: return
            
            self.check_rsi_condition() 
            
            from lib.utils.instrument_utils import get_option_instrument_key
            ce_key = get_option_instrument_key(self.short_symbol, ce_strike, "CE", self.nse_data)
            pe_key = get_option_instrument_key(self.short_symbol, pe_strike, "PE", self.nse_data)
            
            chain_df = get_option_chain_dataframe(self.upstox_token, INDEX_NAME, self.expiry_dt)
            ce_ltp = chain_df[chain_df['strike_price'] == ce_strike].iloc[0]['ce_ltp']
            pe_ltp = chain_df[chain_df['strike_price'] == pe_strike].iloc[0]['pe_ltp']
            
            self.check_vwap_condition(ce_key, pe_key, ce_ltp, pe_ltp)
        except Exception as e:
            logger.debug(f"Heartbeat logic error: {e}")

    def start_streaming(self, keys):
        def on_msg(data):
            try:
                key = data.get('instrument_key')
                ltp = data.get('ltp') or data.get('last_price')
                
                if not ltp: return
                
                symbol = self.upstox_key_map.get(key)
                if self.position:
                    if symbol == self.position.ce_symbol:
                        if ltp != self.position.ce_ltp:
                            self.position.ce_ltp = ltp
                    elif symbol == self.position.pe_symbol:
                        if ltp != self.position.pe_ltp:
                            self.position.pe_ltp = ltp
            except Exception as e:
                logger.debug(f"Stream update error: {e}")
            
        logger.info(f"📡 [UPSTOX] Subscribing to {len(keys)} instruments...")
        self.upstox_streamer.connect_market_data(keys, "full", on_msg)

    def manage_position(self):
        if not self.position: return
        
        pos = self.position
        now = time.time()
        
        # 0. Real-time Status Log (Every 5 seconds)
        if now - self.last_status_log_time >= 5:
            self.last_status_log_time = now
            
            ce_pnl = (pos.ce_entry_price - pos.ce_ltp) * pos.ce_qty if pos.ce_qty > 0 else 0
            pe_pnl = (pos.pe_entry_price - pos.pe_ltp) * pos.pe_qty if pos.pe_qty > 0 else 0
            total_unrealized = ce_pnl + pe_pnl
            total_strategy_pnl = pos.realized_pnl + total_unrealized
            
            ce_sl = pos.ce_entry_price * (1 + SL_PCT)
            pe_sl = pos.pe_entry_price * (1 + SL_PCT)
            
            # CE Status
            # CE Status
            if pos.ce_qty > 0:
                ce_pnl = (pos.ce_entry_price - pos.ce_ltp) * pos.ce_qty
                logger.info(f"📊 [CORE] {pos.ce_symbol} | Entry: {pos.ce_entry_price:.2f} | LTP: {pos.ce_ltp:.2f} | SL: {pos.ce_sl_price:.2f} | PnL: {ce_pnl:.2f}")
            elif pos.ce_sl_hit:
                logger.info(f"📊 [CORE] {pos.ce_symbol} | SL HIT ❌ | LTP: {pos.ce_ltp:.2f} | Re-entry Trigger: {pos.saved_ce_open:.2f}")
            
            # PE Status
            if pos.pe_qty > 0:
                pe_pnl = (pos.pe_entry_price - pos.pe_ltp) * pos.pe_qty
                logger.info(f"📊 [CORE] {pos.pe_symbol} | Entry: {pos.pe_entry_price:.2f} | LTP: {pos.pe_ltp:.2f} | SL: {pos.pe_sl_price:.2f} | PnL: {pe_pnl:.2f}")
            elif pos.pe_sl_hit:
                logger.info(f"📊 [CORE] {pos.pe_symbol} | SL HIT ❌ | LTP: {pos.pe_ltp:.2f} | Re-entry Trigger: {pos.saved_pe_open:.2f}")
                
            logger.info(f"💰 [CORE] Total Strategy PnL: {total_strategy_pnl:.2f} (Realized: {pos.realized_pnl:.2f}, Unrealized: {total_unrealized:.2f})")
            logger.info("-" * 40)
        
        # 1. Stop Loss Check (Trailing + Hardening)
        tsl_pct = PYRAMID_TSL_PCT if pos.pyramid_count > 0 else TRAILING_SL_PCT
        
        # CE
        if not pos.ce_sl_hit and pos.ce_qty > 0:
            # A. Update TSL Trail (Uses tighter % if pyramided)
            trail_price = pos.ce_ltp * (1 + tsl_pct)
            if trail_price < pos.ce_sl_price:
                pos.ce_sl_price = trail_price
                
            # B. Check for SL Hardening (Lock at Cost)
            # If current profit > 15% and SL is still above entry, move SL to entry
            current_profit_pct = (pos.ce_entry_price - pos.ce_ltp) / pos.ce_entry_price
            if current_profit_pct >= SL_HARDENING_PROFIT_PCT:
                if pos.ce_sl_price > pos.ce_entry_price:
                    pos.ce_sl_price = pos.ce_entry_price
                    logger.info(f"⚓ [CORE] CE SL Hardened to Cost: {pos.ce_sl_price:.2f}")

            if pos.ce_ltp >= pos.ce_sl_price:
                # Pyramid Reduction Check
                if pos.ce_qty > pos.initial_ce_qty and pos.initial_ce_qty > 0:
                    reduction_qty = pos.ce_qty - pos.initial_ce_qty
                    logger.info(f"🔽 [CORE] CE Pyramid Reduction triggered! Exiting extra {reduction_qty} lots.")
                    order_id = self.order_mgr.place_order(pos.ce_symbol, reduction_qty, "B", tag="Pyramid_Exit")
                    if order_id:
                        # Realize profit/loss for the lots closed
                        realized = (pos.ce_entry_price - pos.ce_ltp) * reduction_qty
                        pos.realized_pnl += realized
                        
                        pos.ce_qty = pos.initial_ce_qty
                        pos.pyramid_count = 0 
                        pos.naked_ref_price = 0.0
                        # Reset SL to standard 20% for the remaining core lot
                        pos.ce_sl_price = pos.ce_entry_price * (1 + SL_PCT)
                        logger.info(f"🛡️ [CORE] CE Reduced. Realized: {realized:.2f}. SL reset to 20%: {pos.ce_sl_price:.2f}")
                else:
                    logger.info(f"🛑 [CORE] CE Stop Loss Hit! {pos.ce_ltp} >= {pos.ce_sl_price:.2f}")
                    order_id = self.order_mgr.place_order(pos.ce_symbol, pos.ce_qty, "B", tag="SL_Exit")
                    if order_id:
                        # Realize profit/loss
                        realized = (pos.ce_entry_price - pos.ce_ltp) * pos.ce_qty
                        pos.realized_pnl += realized
                        
                        pos.ce_sl_hit = True
                        # Set re-entry trigger: require X% recovery from exit price
                        pos.saved_ce_open = pos.ce_ltp * (1 - self.dynamic_recovery_pct)
                        pos.ce_reentry_armed = False  # Reset: wait for price to move above trigger first
                        logger.info(f"💾 [CORE] CE SL Hit. Realized: {realized:.2f}. Re-entry Trigger: {pos.saved_ce_open:.2f} ({self.dynamic_recovery_pct*100:.0f}% recovery)")
                        pos.ce_qty = 0

        # PE
        if not pos.pe_sl_hit and pos.pe_qty > 0:
            # A. Update TSL Trail (Uses tighter % if pyramided)
            trail_price = pos.pe_ltp * (1 + tsl_pct)
            if trail_price < pos.pe_sl_price:
                pos.pe_sl_price = trail_price
                
            # B. Check for SL Hardening (Lock at Cost)
            current_profit_pct = (pos.pe_entry_price - pos.pe_ltp) / pos.pe_entry_price
            if current_profit_pct >= SL_HARDENING_PROFIT_PCT:
                if pos.pe_sl_price > pos.pe_entry_price:
                    pos.pe_sl_price = pos.pe_entry_price
                    logger.info(f"⚓ [CORE] PE SL Hardened to Cost: {pos.pe_sl_price:.2f}")

            if pos.pe_ltp >= pos.pe_sl_price:
                # Pyramid Reduction Check
                if pos.pe_qty > pos.initial_pe_qty and pos.initial_pe_qty > 0:
                    reduction_qty = pos.pe_qty - pos.initial_pe_qty
                    logger.info(f"🔽 [CORE] PE Pyramid Reduction triggered! Exiting extra {reduction_qty} lots.")
                    order_id = self.order_mgr.place_order(pos.pe_symbol, reduction_qty, "B", tag="Pyramid_Exit")
                    if order_id:
                        # Realize profit/loss
                        realized = (pos.pe_entry_price - pos.pe_ltp) * reduction_qty
                        pos.realized_pnl += realized
                        
                        pos.pe_qty = pos.initial_pe_qty
                        pos.pyramid_count = 0
                        pos.naked_ref_price = 0.0
                        # Reset SL to standard 20% for the remaining core lot
                        pos.pe_sl_price = pos.pe_entry_price * (1 + SL_PCT)
                        logger.info(f"🛡️ [CORE] PE Reduced. Realized: {realized:.2f}. SL reset to 20%: {pos.pe_sl_price:.2f}")
                else:
                    logger.info(f"🛑 [CORE] PE Stop Loss Hit! {pos.pe_ltp} >= {pos.pe_sl_price:.2f}")
                    order_id = self.order_mgr.place_order(pos.pe_symbol, pos.pe_qty, "B", tag="SL_Exit")
                    if order_id:
                        # Realize profit/loss
                        realized = (pos.pe_entry_price - pos.pe_ltp) * pos.pe_qty
                        pos.realized_pnl += realized
                        
                        pos.pe_sl_hit = True
                        # Set re-entry trigger: require X% recovery from exit price
                        pos.saved_pe_open = pos.pe_ltp * (1 - self.dynamic_recovery_pct)
                        pos.pe_reentry_armed = False  # Reset: wait for price to move above trigger first
                        logger.info(f"💾 [CORE] PE SL Hit. Realized: {realized:.2f}. Re-entry Trigger: {pos.saved_pe_open:.2f} ({self.dynamic_recovery_pct*100:.0f}% recovery)")
                        pos.pe_qty = 0

        # 2. Re-entry Logic (If Naked)
        if pos.ce_sl_hit and pos.ce_qty == 0:
            # First, check if price has moved above trigger (arming the re-entry)
            if pos.ce_ltp >= pos.saved_ce_open:
                if not pos.ce_reentry_armed:
                    pos.ce_reentry_armed = True
                    logger.info(f"🔓 [CORE] CE Re-entry ARMED. Price {pos.ce_ltp:.2f} >= Trigger {pos.saved_ce_open:.2f}")
            
            # Only allow re-entry if armed AND price drops below trigger
            if pos.ce_reentry_armed and pos.ce_ltp < pos.saved_ce_open:
                logger.info(f"🔄 [CORE] CE Re-entry Signal! Price {pos.ce_ltp} < Saved {pos.saved_ce_open}")
                target_qty = pos.pe_qty
                if target_qty > 0:
                     order_id = self.order_mgr.place_order(pos.ce_symbol, target_qty, "S", tag="ReEntry")
                     if order_id:
                         pos.ce_qty = target_qty
                         pos.ce_sl_hit = False 
                         pos.ce_reentry_armed = False  # Reset for next cycle
                         pos.ce_entry_price = pos.ce_ltp # Updated entry price
                         # Reset SL Price for the re-entered leg
                         pos.ce_sl_price = pos.ce_entry_price * (1 + SL_PCT)
                         logger.info(f"✅ [CORE] Re-entered CE at {pos.ce_entry_price:.2f}. New SL: {pos.ce_sl_price:.2f}")

        if pos.pe_sl_hit and pos.pe_qty == 0:
            # First, check if price has moved above trigger (arming the re-entry)
            if pos.pe_ltp >= pos.saved_pe_open:
                if not pos.pe_reentry_armed:
                    pos.pe_reentry_armed = True
                    logger.info(f"🔓 [CORE] PE Re-entry ARMED. Price {pos.pe_ltp:.2f} >= Trigger {pos.saved_pe_open:.2f}")
            
            # Only allow re-entry if armed AND price drops below trigger
            if pos.pe_reentry_armed and pos.pe_ltp < pos.saved_pe_open:
                logger.info(f"🔄 [CORE] PE Re-entry Signal! Price {pos.pe_ltp} < Saved {pos.saved_pe_open}")
                target_qty = pos.ce_qty
                if target_qty > 0:
                     order_id = self.order_mgr.place_order(pos.pe_symbol, target_qty, "S", tag="ReEntry")
                     if order_id:
                         pos.pe_qty = target_qty
                         pos.pe_sl_hit = False
                         pos.pe_reentry_armed = False  # Reset for next cycle
                         pos.pe_entry_price = pos.pe_ltp # Updated entry price
                         # Reset SL Price for the re-entered leg
                         pos.pe_sl_price = pos.pe_entry_price * (1 + SL_PCT)
                         logger.info(f"✅ [CORE] Re-entered PE at {pos.pe_entry_price:.2f}. New SL: {pos.pe_sl_price:.2f}")

        # 3. Pyramiding
        if pos.is_naked and PYRAMID_ENABLED:
            active_side = "CE" if pos.ce_qty > 0 else "PE"
            current_price = pos.ce_ltp if active_side == "CE" else pos.pe_ltp
            symbol = pos.ce_symbol if active_side == "CE" else pos.pe_symbol
            
            # Set reference price if entering naked state for the first time
            if pos.naked_ref_price == 0.0:
                pos.naked_ref_price = current_price
                logger.info(f"📍 [CORE] Set {active_side} Naked Reference Price: {pos.naked_ref_price}")
            
            # Profit % calculation relative to the price when we became naked (or last added)
            current_profit_pct = (pos.naked_ref_price - current_price) / pos.naked_ref_price
            
            if current_profit_pct >= PYRAMID_PROFIT_STEP_PCT and pos.pyramid_count < MAX_PYRAMID_LOTS:
                logger.info(f"⛰️ [CORE] Pyramiding Triggered! Profit {current_profit_pct*100:.1f}% >= {PYRAMID_PROFIT_STEP_PCT*100}% (Last Ref: {pos.naked_ref_price})")
                
                # Step-Locking: Ladder the SL to the PREVIOUS reference price to lock in profit
                # This ensures we don't lose the gains from the previous move as we add size.
                prev_ref = pos.naked_ref_price
                
                lot_size = get_lot_size(self.kotak_broker.master_df, symbol)
                add_qty = lot_size
                
                order_id = self.order_mgr.place_order(symbol, add_qty, "S", tag="Pyramid_Entry")
                if order_id:
                    # Update Weighted Average Entry Price for accurate P&L and SL
                    if active_side == "CE": 
                        pos.ce_entry_price = ((pos.ce_entry_price * pos.ce_qty) + (current_price * add_qty)) / (pos.ce_qty + add_qty)
                        pos.ce_qty += add_qty
                        pos.ce_sl_price = min(pos.ce_sl_price, prev_ref) # Lock SL at previous step
                    else: 
                        pos.pe_entry_price = ((pos.pe_entry_price * pos.pe_qty) + (current_price * add_qty)) / (pos.pe_qty + add_qty)
                        pos.pe_qty += add_qty
                        pos.pe_sl_price = min(pos.pe_sl_price, prev_ref) # Lock SL at previous step
                    
                    pos.pyramid_count += 1
                    # Update reference price for NEXT sequential step (e.g., 100 -> 90 -> 81)
                    pos.naked_ref_price = current_price
                    logger.info(f"🔒 [CORE] {active_side} SL Laddered to Step: {prev_ref:.2f}")
                    logger.info(f"📍 [CORE] Updated {active_side} Avg Entry: {pos.ce_entry_price if active_side == 'CE' else pos.pe_entry_price:.2f}")
                    logger.info(f"📍 [CORE] Updated {active_side} Naked Reference Price for next step: {pos.naked_ref_price}")
        else:
            # Reset reference price if not naked (Strangle state or completely closed)
            pos.naked_ref_price = 0.0

        # 4. Target Exit
        if pos.ce_qty > 0:
            profit_pct = (pos.ce_entry_price - pos.ce_ltp)/pos.ce_entry_price
            if profit_pct >= TARGET_PROFIT_PCT:
                logger.info(f"🎯 [CORE] Target Hit CE! {profit_pct*100:.1f}%")
                order_id = self.order_mgr.place_order(pos.ce_symbol, pos.ce_qty, "B", tag="Target_Exit")
                if order_id:
                    # Realize profit/loss
                    realized = (pos.ce_entry_price - pos.ce_ltp) * pos.ce_qty
                    pos.realized_pnl += realized
                    pos.ce_qty = 0

        if pos.pe_qty > 0:
            profit_pct = (pos.pe_entry_price - pos.pe_ltp)/pos.pe_entry_price
            if profit_pct >= TARGET_PROFIT_PCT:
                logger.info(f"🎯 [CORE] Target Hit PE! {profit_pct*100:.1f}%")
                order_id = self.order_mgr.place_order(pos.pe_symbol, pos.pe_qty, "B", tag="Target_Exit")
                if order_id:
                    # Realize profit/loss
                    realized = (pos.pe_entry_price - pos.pe_ltp) * pos.pe_qty
                    pos.realized_pnl += realized
                    pos.pe_qty = 0
                
        # 5. Reset if fully closed
        if pos.ce_qty == 0 and pos.pe_qty == 0:
            logger.info("🏁 [CORE] All legs closed. Resetting strategy for fresh signal search.")
            self.position = None

        # Save State after updates
        self.save_state()


    def save_state(self):
        """Save position state to JSON"""
        try:
            if not self.position:
                if os.path.exists("rsi_strangle_state.json"):
                    os.remove("rsi_strangle_state.json")
                return

            pos = self.position
            data = {
                "ce_symbol": pos.ce_symbol,
                "pe_symbol": pos.pe_symbol,
                "ce_entry_price": pos.ce_entry_price,
                "pe_entry_price": pos.pe_entry_price,
                "ce_qty": pos.ce_qty,
                "pe_qty": pos.pe_qty,
                "initial_ce_qty": pos.initial_ce_qty,
                "initial_pe_qty": pos.initial_pe_qty,
                "ce_strike": pos.ce_strike,
                "pe_strike": pos.pe_strike,
                "ce_sl_hit": pos.ce_sl_hit,
                "pe_sl_hit": pos.pe_sl_hit,
                "ce_sl_price": pos.ce_sl_price,
                "pe_sl_price": pos.pe_sl_price,
                "saved_ce_open": pos.saved_ce_open,
                "saved_pe_open": pos.saved_pe_open,
                "ce_reentry_armed": pos.ce_reentry_armed,
                "pe_reentry_armed": pos.pe_reentry_armed,
                "pyramid_count": pos.pyramid_count,
                "naked_ref_price": pos.naked_ref_price,
                "realized_pnl": pos.realized_pnl,
                "expiry": self.expiry_dt
            }
            
            with open("rsi_strangle_state.json", "w") as f:
                json.dump(data, f)
                
        except Exception as e:
            logger.error(f"❌ [CORE] State Save Error: {e}")

    def load_state(self):
        """Load position state from JSON"""
        try:
            if not os.path.exists("rsi_strangle_state.json"):
                return
                
            with open("rsi_strangle_state.json", "r") as f:
                data = json.load(f)
                
            # Check expiry match
            if data.get("expiry") != self.expiry_dt:
                logger.warning("⚠️ [CORE] Found old state from different expiry. Ignoring.")
                return

            self.position = Position(
                data["ce_symbol"], data["pe_symbol"],
                data["ce_entry_price"], data["pe_entry_price"],
                data["ce_qty"], data["pe_qty"],
                data["ce_strike"], data["pe_strike"]
            )
            # Restore extra fields
            self.position.ce_sl_hit = data["ce_sl_hit"]
            self.position.pe_sl_hit = data["pe_sl_hit"]
            self.position.ce_sl_price = data.get("ce_sl_price", self.position.ce_sl_price)
            self.position.pe_sl_price = data.get("pe_sl_price", self.position.pe_sl_price)
            self.position.saved_ce_open = data["saved_ce_open"]
            self.position.saved_pe_open = data["saved_pe_open"]
            self.position.ce_reentry_armed = data.get("ce_reentry_armed", False)
            self.position.pe_reentry_armed = data.get("pe_reentry_armed", False)
            self.position.pyramid_count = data["pyramid_count"]
            self.position.naked_ref_price = data.get("naked_ref_price", 0.0)
            self.position.initial_ce_qty = data.get("initial_ce_qty", self.position.ce_qty)
            self.position.initial_pe_qty = data.get("initial_pe_qty", self.position.pe_qty)
            self.position.realized_pnl = data.get("realized_pnl", 0.0)
            
            # Re-map keys for streaming
            # We need to re-resolve keys or store them?
            # Re-resolving is safer using short_symbol
            from lib.utils.instrument_utils import get_option_instrument_key
            ce_key = get_option_instrument_key(self.short_symbol, self.position.ce_strike, "CE", self.nse_data)
            pe_key = get_option_instrument_key(self.short_symbol, self.position.pe_strike, "PE", self.nse_data)
            
            self.upstox_key_map[ce_key] = self.position.ce_symbol
            self.upstox_key_map[pe_key] = self.position.pe_symbol
            self.ce_token_map[self.position.ce_symbol] = ce_key
            self.pe_token_map[self.position.pe_symbol] = pe_key
            
            self.start_streaming([ce_key, pe_key])
            logger.info("✅ [CORE] State Restored Successfully")
            
        except Exception as e:
            logger.error(f"❌ [CORE] State Load Error: {e}")

    def run(self):
        self.initialize()
        
        if STATE_RESTORATION_ENABLED:
            self.load_state() # Load after init
        else:
            # Clear any legacy state file to ensure fresh start
            if os.path.exists("rsi_strangle_state.json"):
                os.remove("rsi_strangle_state.json")
                logger.info("🧹 [CORE] State restoration disabled. Cleared legacy state file.")
        
        # Parse Start/Exit Times
        start_time_obj = datetime.strptime(START_TIME, "%H:%M:%S").time()
        exit_time_obj = datetime.strptime(EXIT_TIME, "%H:%M:%S").time()
        
        # Parse Interval from Config (e.g., "3minute" -> 3)
        try:
            candle_interval = int(''.join(filter(str.isdigit, RSI_TIMEFRAME)))
        except:
             logger.warning(f"⚠️ [CORE] Could not parse RSI_TIMEFRAME '{RSI_TIMEFRAME}'. Defaulting to 5 minutes.")
             candle_interval = 5
             
        logger.info(f"⏰ [CORE] Strategy Loop Started. Start Time: {START_TIME}, Interval: {candle_interval} min")
        
        self.last_checked_minute = -1
        
        while True:
            try:
                now = datetime.now()
                
                # 0. Check Exit Time (Intraday Square-off)
                if now.time() >= exit_time_obj:
                    logger.info(f"🛑 [CORE] Intraday Exit Time {EXIT_TIME} Reached! Squaring off all positions...")
                    if self.position:
                        # Realize P&L before closing
                        if self.position.ce_qty > 0:
                            realized = (self.position.ce_entry_price - self.position.ce_ltp) * self.position.ce_qty
                            self.position.realized_pnl += realized
                            order_id = self.order_mgr.place_order(self.position.ce_symbol, self.position.ce_qty, "B", tag="Intraday_Exit")
                            if order_id:
                                logger.info(f"✅ [CORE] CE Closed at EOD. Realized: {realized:.2f}")
                        
                        if self.position.pe_qty > 0:
                            realized = (self.position.pe_entry_price - self.position.pe_ltp) * self.position.pe_qty
                            self.position.realized_pnl += realized
                            order_id = self.order_mgr.place_order(self.position.pe_symbol, self.position.pe_qty, "B", tag="Intraday_Exit")
                            if order_id:
                                logger.info(f"✅ [CORE] PE Closed at EOD. Realized: {realized:.2f}")
                        
                        # Log final day's P&L
                        logger.info(f"💰 [CORE] Final Day P&L: {self.position.realized_pnl:.2f}")
                        
                        self.position = None
                        self.save_state() # Clear state
                        
                    logger.info("✅ [CORE] Day Complete. Exiting strategy.")
                    sys.exit(0)

                # 1. Check Start Time
                if now.time() < start_time_obj:
                    logger.info(f"zzZ [CORE] Waiting for Start Time {START_TIME}...")
                    time.sleep(60) # Sleep longer if before start
                    continue

                if not self.position:
                    # Sync with Candle Close (Dynamic Interval)
                    
                    # Heartbeat while waiting
                    time_to_next_sync = candle_interval - (now.minute % candle_interval)
                    if now.minute % candle_interval != 0:
                        if time.time() - self.last_heartbeat_time >= 30:
                            self.last_heartbeat_time = time.time()
                            logger.info(f"⏳ [CORE] Idle Heartbeat | Next Check in ~{time_to_next_sync} min(s) | Current Conditions:")
                            self.show_current_conditions_snapshot()
                            logger.info("-" * 40)

                    # We check at the START of the minute divisible by interval
                    if now.minute % candle_interval == 0:
                        if now.minute != self.last_checked_minute:
                            # New candle just closed
                            logger.info(f"🕯️ [CORE] Candle Close Detected ({now.strftime('%H:%M')}). Checking Signals...")
                            
                            # Add delay to ensure broker data is ready (User req: at least 5 sec)
                            time.sleep(5) 
                            logger.info("⚡ [CORE] Wait complete. Executing Entry Logic...")
                            
                            self.enter_strategy()
                            
                            # Mark this minute as checked
                            self.last_checked_minute = now.minute
                    else:
                         # Reset if we move past the check minute (e.g., 9:06)
                         if self.last_checked_minute != -1 and now.minute != self.last_checked_minute:
                             # Just to be clean, though logic holds without this
                             pass
                else:
                    self.manage_position()
                
                time.sleep(1)
            except KeyboardInterrupt:
                logger.warning("⚠️ [CORE] User interrupted")
                break
            except Exception as e:
                logger.error(f"❌ [CORE] Loop Exception: {e}")
                time.sleep(5)

if __name__ == "__main__":
    from lib.core.authentication import get_access_token
    token = get_access_token()
    if not token: sys.exit(1)
    
    s = RSIVWAPStrangle(token)
    s.run()

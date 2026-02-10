"""
VWAP Theta Straddle Strategy (Intraday)
Timeframe: 5-minute Candles
Entry: 09:20 AM
Logic:
1. Combined Premium (CP) = Close(CE) + Close(PE)
2. Entry if CP < Prev Day Low AND CP < VWAP
3. Exit if CP > VWAP or Stop Loss Hit
4. Static Strikes (No Rolling)
"""

import sys
import os
import time
import pandas as pd
import numpy as np
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List, Optional

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'Kotak_Api'))) # Commented to fix lib conflict

# --- Upstox Imports ---
from lib.api.option_chain import (
    get_option_chain_dataframe, get_atm_strike_from_chain
)
from lib.api.market_data import download_nse_market_data, get_market_quotes
from lib.api.historical import get_historical_data, get_historical_range, get_historical_data_v3, get_intraday_data_v3
from lib.utils.tick_aggregator import TickAggregator
from lib.api.streaming import UpstoxStreamer
from lib.utils.instrument_utils import get_option_instrument_key
from lib.utils.expiry_cache import get_expiry_for_strategy

# --- Kotak Imports ---
from Kotak_Api.lib.broker import BrokerClient
from Kotak_Api.lib.order_manager import OrderManager
from Kotak_Api.lib.trading_utils import get_strike_token, get_lot_size

class VWAPStraddleStrategy:
    def __init__(self, access_token: str, nse_data, 
                 lot_size: int = 65,
                 stop_loss_points: float = 30.0,
                 max_straddle_width_pct: float = 0.20,
                 max_skew_exit_pct: float = 0.60,
                 exit_cooldown_minutes: int = 2,
                 candle_interval_minutes: int = 5,
                 expiry_type: str = "current_week",
                 dry_run: bool = False):
        
        self.access_token = access_token
        self.nse_data = nse_data
        self.lot_size = lot_size
        self.stop_loss_points = stop_loss_points
        self.max_straddle_width_pct = max_straddle_width_pct
        self.max_skew_exit_pct = max_skew_exit_pct
        self.exit_cooldown_minutes = exit_cooldown_minutes
        self.candle_interval_minutes = candle_interval_minutes
        self.expiry_type = expiry_type
        self.dry_run = dry_run
        
        self.kotak_broker = None
        self.kotak_order_manager = None
        self.option_chain_df = None
        self.expiry_date = None
        self.atm_strike = None
        
        # Strategy State
        self.ce_instrument = None # {key, symbol, token}
        self.pe_instrument = None
        self.positions = [] # List of dicts
        self.is_position_open = False
        
        # Analysis Data
        # Analysis Data
        self.prev_day_cp_low = -1.0
        self.prev_day_cp_close = -1.0
        self.live_vwap = 0.0
        self.current_cp = 0.0
        self.entry_price_combined = 0.0 # Track entry price for SL
        self.last_exit_time = None # Track last exit for cooldown
        
        # Aggregators
        self.ce_aggregator = TickAggregator(candle_interval_minutes)
        self.pe_aggregator = TickAggregator(candle_interval_minutes)
        self.streamer = None
        
        self.log_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'logs', 'vwap_straddle')
        if not os.path.exists(self.log_dir):
            try: os.makedirs(self.log_dir)
            except: pass
        self.log_file = os.path.join(self.log_dir, f"vwap_straddle_{datetime.now().strftime('%Y%m%d')}.log")

    def log(self, message):
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {message}")
        try:
            with open(self.log_file, "a") as f:
                f.write(f"[{ts}] {message}\n")
        except: pass

    def initialize(self):
        self.log("🚀 Initializing VWAP Straddle Strategy...")
        # Auth Kotak
        try:
            self.kotak_broker = BrokerClient()
            self.kotak_broker.authenticate()
            self.kotak_broker.load_master_data()
            self.kotak_order_manager = OrderManager(self.kotak_broker.client, dry_run=self.dry_run)
            self.log("✅ Kotak Neo Connected")
        except Exception as e:
            self.log(f"❌ Kotak Init Failed: {e}")
            return False
            
        # Get Expiry using library
        self.log(f"📅 Selecting {self.expiry_type} expiry (using cache if available)...")
        try:
            expiry_str = get_expiry_for_strategy(
                access_token=self.access_token,
                expiry_type=self.expiry_type,
                instrument="NIFTY",
                force_refresh=False
            )
            self.expiry_date = expiry_str
            self.log(f"📅 Selected {self.expiry_type} expiry: {self.expiry_date}")
        except Exception as e:
            self.log(f"❌ Expiry selection failed: {e}")
            return False
        
        return True

    def get_latest_candle(self, instrument_key):
        # Fetch candles from Aggregator
        if instrument_key in [self.ce_instrument['key'], self.pe_instrument['key']]:
            is_ce = (instrument_key == self.ce_instrument['key'])
            agg = self.ce_aggregator if is_ce else self.pe_aggregator
            df = agg.get_dataframe(instrument_key)
            if not df.empty:
                return df.to_dict('records')
        
        # Fallback to REST (or for warmup)
        data = get_intraday_data_v3(
            self.access_token, 
            instrument_key, 
            "minutes", 
            self.candle_interval_minutes
        )
        return data if data else None

    def calculate_synthetic_vwap(self, ce_candles, pe_candles):
        # Align candles by timestamp
        # Build DataFrame
        df_ce = pd.DataFrame(ce_candles).set_index('timestamp')
        df_pe = pd.DataFrame(pe_candles).set_index('timestamp')
        
        # Inner Join to find matching timestamps
        df = df_ce.join(df_pe, lsuffix='_ce', rsuffix='_pe', how='inner')
        
        # Filter for today only (VWAP is intraday)
        today_str = datetime.now().strftime('%Y-%m-%d')
        df = df[df.index.str.startswith(today_str)]
        
        if df.empty: return 0.0, 0.0, 0.0
        
        # Calculate Combined Metrics
        # Combined Close = Close_CE + Close_PE
        df['cp_close'] = df['close_ce'] + df['close_pe']
        
        # Total Volume = Vol_CE + Vol_PE
        df['total_vol'] = df['volume_ce'] + df['volume_pe']
        
        # VWAP Math
        # Typical Price for VWAP is usually (H+L+C)/3, but for Options Synthetic CP, Close is cleaner.
        # Weighted Price = CP_Close * Total_Vol
        df['pv'] = df['cp_close'] * df['total_vol']
        
        cumulative_pv = df['pv'].cumsum()
        cumulative_vol = df['total_vol'].cumsum()
        
        df['vwap'] = cumulative_pv / cumulative_vol
        
        latest = df.iloc[-1]
        return latest['vwap'], latest['cp_close'], latest.name # VWAP, CP, Timestamp

    def get_prev_day_combined_low(self, ce_key, pe_key):
        # Calculate Dates
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d') # Last 5-7 days
        
        # V3 Update: Fetch DIRECT 5-minute data using Upstox V3 API
        # Unit: 'minutes', Interval: 5
        ce_data = get_historical_data_v3(self.access_token, ce_key, "minutes", 5, start_date, end_date)
        pe_data = get_historical_data_v3(self.access_token, pe_key, "minutes", 5, start_date, end_date)
        
        if not ce_data or not pe_data: return -1.0, -1.0
        
        df_ce = pd.DataFrame(ce_data).set_index('timestamp')
        df_pe = pd.DataFrame(pe_data).set_index('timestamp')
        
        # Align timestamps (they should match if 5-min boundaries are standard)
        df = df_ce.join(df_pe, lsuffix='_ce', rsuffix='_pe', how='inner')
        
        # Identify "Yesterday"
        dates = sorted(list(set([ts.split('T')[0] for ts in df.index])))
        today = datetime.now().strftime('%Y-%m-%d')
        
        if today in dates: dates.remove(today)
        
        if not dates: return float('inf'), float('inf')
        
        yesterday = dates[-1]
        
        # Validate expected prev day
        expected_yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        if yesterday != expected_yesterday:
            self.log(f"⚠️ Using {yesterday} as prev day (expected {expected_yesterday} - may be weekend/holiday)")
        
        df_yesterday = df[df.index.str.startswith(yesterday)].copy()
        
        if df_yesterday.empty: return -1.0, -1.0
        
        # Calculate CP Metrics (Directly on 5-min data)
        df_yesterday['cp_close'] = df_yesterday['close_ce'] + df_yesterday['close_pe']
        min_low = df_yesterday['cp_close'].min()
        last_close = df_yesterday['cp_close'].iloc[-1]
        
        self.log(f"📉 Prev Day ({yesterday}) Combined Low (V3 5-Min): {min_low:.2f} | Close: {last_close:.2f}")
        return min_low, last_close

    def execute_entry(self):
        # 1. Place Orders (MIS)
        self.log(f"⚡ Executing VWAP Straddle Entry")
        
        # Sell CE
        qty = self.lot_size
        ce_oid = self.kotak_order_manager.place_order(self.ce_instrument['symbol'], qty, "S", tag="VWAP_ENTRY", product="MIS")
        
        # Sell PE
        pe_oid = self.kotak_order_manager.place_order(self.pe_instrument['symbol'], qty, "S", tag="VWAP_ENTRY", product="MIS")
        
        if ce_oid: self.log(f"✅ CE Entry Order: {ce_oid}")
        if pe_oid: self.log(f"✅ PE Entry Order: {pe_oid}")
        
        self.positions.append({'symbol': self.ce_instrument['symbol'], 'type': 'CE', 'qty': qty})
        self.positions.append({'symbol': self.pe_instrument['symbol'], 'type': 'PE', 'qty': qty})
        self.is_position_open = True
        
        # Record Entry CP for SL (using current CP from analysis)
        self.entry_price_combined = self.current_cp
        
        # Update positions with entry prices (using current 5min close as a proxy for entry if executed at that time, or better, the limit price? 
        # For simplicity in this logic, we use the candle close that triggered entry as the 'entry price' reference for PnL, 
        # or we should fetch the actual trade price. 
        # Since this is a bot, we can assume 'current_cp' legs.
        # But wait, 'current_cp' comes from 'calculate_synthetic_vwap' which uses the *latest 5min candle close*.
        # So we use that.
        
        self.positions[-2]['entry_price'] = self.ce_instrument['last_close']
        self.positions[-1]['entry_price'] = self.pe_instrument['last_close']
        
        self.log(f"📝 Entry Recorded @ CP: {self.entry_price_combined:.2f} | SL Target: {self.entry_price_combined + self.stop_loss_points:.2f}")

    def calculate_pnl(self):
        if not self.positions: return {'total': 0.0}
        
        total_pnl = 0.0
        details = []
        
        # We need current prices to calc PnL. 
        # In run loop, we update self.ce_instrument['last_close'] and pe...
        # So we can use that.
        
        for pos in self.positions:
            # Short Position: (Entry - Current) * Qty
            current_price = 0.0
            if pos['type'] == 'CE' and 'last_close' in self.ce_instrument:
                current_price = self.ce_instrument['last_close']
            elif pos['type'] == 'PE' and 'last_close' in self.pe_instrument:
                current_price = self.pe_instrument['last_close']
                
            pnl = (pos['entry_price'] - current_price) * pos['qty']
            total_pnl += pnl
            pos['current_pnl'] = pnl # Cache for display
            pos['current_price'] = current_price
            
        return {'total': total_pnl}

    def display_status(self):
        pnl = self.calculate_pnl()
        ts = datetime.now().strftime('%H:%M:%S')
        
        # Build Leg String
        pos_str = ""
        if self.positions:
            legs = []
            for pos in self.positions:
                # Format: CE25500(120.5)
                price = pos.get('current_price', 0.0)
                legs.append(f"{pos['type']}{pos['symbol'][-5:]}({price:.1f})") # Extract Strike roughly from symbol or use logic
                # Better: Use type + strike. We rely on symbol having strike? 
                # Symbol is like 'NIFTY...CE'. 
                # Let's just use the type and captured price.
            pos_str = " | ".join(legs)
        else:
            # If no position, show monitored strikes
            ce_p = self.ce_instrument.get('last_close', 0.0)
            pe_p = self.pe_instrument.get('last_close', 0.0)
            pos_str = f"CE({ce_p:.1f}) | PE({pe_p:.1f})"
            
        # Ref CP (Prev Day Low is effectively our 'Reference' for breakdown, but for PnL we check Entry)
        # Ref CP (Prev Day Low is effectively our 'Reference' for breakdown, but for PnL we check Entry)
        ref_str = f"Ref: {self.entry_price_combined:.2f}" if self.is_position_open else f"Low: {self.prev_day_cp_low:.2f}"
        
        status_msg = f"PnL: {pnl['total']:>8.2f} | CP: {self.current_cp:.2f} ({ref_str}) | VWAP: {self.live_vwap:.2f} | {pos_str}"
        self.log(status_msg)

    def exit_all(self, reason):
        self.log(f"🛑 Closing All Positions: {reason}")
        for pos in self.positions:
            oid = self.kotak_order_manager.place_order(pos['symbol'], pos['qty'], "B", tag="VWAP_EXIT", product="MIS")
            if oid: self.log(f"✅ Exit Order for {pos['symbol']}: {oid}")
        
        self.positions = []
        self.is_position_open = False
        self.last_exit_time = datetime.now()  # Track exit time for cooldown
        self.log("ℹ️ Positions Closed. Resuming Monitoring for Re-entry...")
        # sys.exit(0) Removed to allow re-entry

    def run(self):
        if not self.initialize(): return
        
        # 1. Update Option Chain & Selection
        self.option_chain_df = get_option_chain_dataframe(self.access_token, "NSE_INDEX|Nifty 50", self.expiry_date)
        self.atm_strike = get_atm_strike_from_chain(self.option_chain_df)
        self.log(f"🎯 ATM Strike: {self.atm_strike}")
        
        # 2. Resolve Symbols
        ce_token, ce_sym = get_strike_token(self.kotak_broker, self.atm_strike, "CE", datetime.strptime(self.expiry_date, "%Y-%m-%d"))
        pe_token, pe_sym = get_strike_token(self.kotak_broker, self.atm_strike, "PE", datetime.strptime(self.expiry_date, "%Y-%m-%d"))
        
        ce_key = get_option_instrument_key("NIFTY", self.atm_strike, "CE", self.nse_data)
        pe_key = get_option_instrument_key("NIFTY", self.atm_strike, "PE", self.nse_data)
        
        self.ce_instrument = {'key': ce_key, 'symbol': ce_sym, 'token': ce_token}
        self.pe_instrument = {'key': pe_key, 'symbol': pe_sym, 'token': pe_token}
        
        # 3. Streamer & Aggregator Warmup
        self.log(f"🔥 Warming up Aggregators for {ce_sym} & {pe_sym}...")
        self.streamer = UpstoxStreamer(self.access_token)
        self.streamer.connect_market_data([ce_key, pe_key], mode="ltpc", on_message=self.on_market_data)
        
        # Wait for WebSocket Connection
        self.log("⏳ Waiting for WebSocket connection...")
        for _ in range(5):
            time.sleep(1)
            if self.streamer.market_data_connected:
                self.log("✅ WebSocket connection confirmed")
                break
        else:
             self.log("⚠️ WebSocket not confirmed within 5s, will rely on REST Fallbacks")
        
        # Seed History
        try:
            ce_hist = get_intraday_data_v3(self.access_token, ce_key, "minutes", self.candle_interval_minutes)
            if ce_hist: self.ce_aggregator.update_historical(ce_key, pd.DataFrame(ce_hist))
            
            pe_hist = get_intraday_data_v3(self.access_token, pe_key, "minutes", self.candle_interval_minutes)
            if pe_hist: self.pe_aggregator.update_historical(pe_key, pd.DataFrame(pe_hist))
        except Exception as e:
            self.log(f"⚠️ Warmup Error: {e}")
        
        # 3. Get Prev Day Low
        # 3. Get Prev Day Low
        self.prev_day_cp_low, self.prev_day_cp_close = self.get_prev_day_combined_low(ce_key, pe_key)
        
        self.log("⏳ Waiting for 09:20 AM...")
        # Main Loop
        while True:
            now = datetime.now()
            
            # Wait for 09:20
            if now.time() < dt_time(9, 20):
                time.sleep(30)
                continue
                
            # One-time ATM Refresh at 09:20
            # One-time ATM Refresh at 09:20 (or first loop execution after 09:20)
            if not getattr(self, 'metrics_initialized', False):
                self.log("🔄 Refreshing ATM & Instruments for Entry Time...")
                self.option_chain_df = get_option_chain_dataframe(self.access_token, "NSE_INDEX|Nifty 50", self.expiry_date)
                self.atm_strike = get_atm_strike_from_chain(self.option_chain_df)
                self.log(f"🎯 Updated ATM: {self.atm_strike}")
                
                # Re-resolve symbols
                ce_token, ce_sym = get_strike_token(self.kotak_broker, self.atm_strike, "CE", datetime.strptime(self.expiry_date, "%Y-%m-%d"))
                pe_token, pe_sym = get_strike_token(self.kotak_broker, self.atm_strike, "PE", datetime.strptime(self.expiry_date, "%Y-%m-%d"))
                
                ce_key = get_option_instrument_key("NIFTY", self.atm_strike, "CE", self.nse_data)
                pe_key = get_option_instrument_key("NIFTY", self.atm_strike, "PE", self.nse_data)
                
                self.ce_instrument = {'key': ce_key, 'symbol': ce_sym, 'token': ce_token}
                self.pe_instrument = {'key': pe_key, 'symbol': pe_sym, 'token': pe_token}
                
                # Reset Prev Data Low check to ensure we fetch for NEW strikes
                self.prev_day_cp_low = -1.0
                self.prev_day_cp_close = -1.0
                self.metrics_initialized = True 

            # Wait for strict X-minute intervals (Candle Close)
            # e.g. 09:25, 09:30.
            # We want to run logic at 09:25:01 to check the 09:20-09:25 candle.
            
            now = datetime.now()
            interval = self.candle_interval_minutes
            next_candle_mark = now + timedelta(minutes = interval - now.minute % interval)
            next_candle_mark = next_candle_mark.replace(second=2, microsecond=0) # Run at :02 seconds
            
            wait_seconds = (next_candle_mark - now).total_seconds()
            
            if wait_seconds > 0:
                # Smart Wait Logic: Poll every 15s for SL Check
                end_wait_time = datetime.now() + timedelta(seconds=wait_seconds)
                sl_triggered = False
                
                while datetime.now() < end_wait_time:
                    # Sleep 15s or remaining time
                    remaining = (end_wait_time - datetime.now()).total_seconds()
                    sleep_time = min(15, remaining)
                    if sleep_time <= 0: break
                    
                    time.sleep(sleep_time)
                    
                    # Poll for Realtime PnL / SL Check if position is open
                    if self.is_position_open and self.ce_instrument and self.pe_instrument:
                        try:
                            # 1. Fetch Quotes (LTP) using Market Quote API
                            quotes = get_market_quotes(self.access_token, [self.ce_instrument['key'], self.pe_instrument['key']])
                            
                            if quotes:
                                # Extract LTPs
                                ce_ltp = quotes.get(self.ce_instrument['key'], {}).get('last_price', 0.0)
                                pe_ltp = quotes.get(self.pe_instrument['key'], {}).get('last_price', 0.0)
                                
                                if ce_ltp > 0 and pe_ltp > 0:
                                    current_cp_ltp = ce_ltp + pe_ltp
                                    
                                    # PnL Est
                                    pnl_est = (self.entry_price_combined - current_cp_ltp) * self.lot_size
                                    
                                    # Log Realtime Status
                                    self.log(f"⚡ [Realtime] CP: {current_cp_ltp:.2f} | PnL: {pnl_est:.2f} | Ref: {self.entry_price_combined:.2f}")
                                    
                                    # Check SL (Strict > Entry + SL Points)
                                    sl_level = self.entry_price_combined + self.stop_loss_points
                                    if current_cp_ltp > sl_level:
                                        self.log(f"🛑 [Realtime] STOP LOSS TRIGGERED! CP: {current_cp_ltp:.2f} > {sl_level:.2f}")
                                        self.exit_all("Realtime SL Hit")
                                        sl_triggered = True
                                        break
                        except Exception as e:
                            self.log(f"⚠️ Realtime Poll Error: {e}")
                            pass
                
                # If SL triggered, skip logic for this incomplete candle and wait for next
                if sl_triggered:
                    self.log("⏳ Waiting for next candle after SL...")
                    continue

            
            # Wake up at XX:XX:02
            # Fetch Latest Completed Candle
            # get_latest_5min_candle fetches 1-min data and resamples. 
            # It will naturally include the just-completed candle if we fetch enough data.
            
            # Fetch Candles
            ce_candles = self.get_latest_candle(self.ce_instrument['key'])
            pe_candles = self.get_latest_candle(self.pe_instrument['key'])
            
            # Filter partial candles (if current forming candle is returned)
            # We only want COMPLETED candles.
            if ce_candles and pe_candles:
                latest_ts = ce_candles[-1]['timestamp'] # Str: YYYY-MM-DDTHH:MM:SS+05:30
                
                # CRITICAL: Use fresh time after sleep
                filter_now = datetime.now()
                
                # Calculate current incomplete interval start
                # We are at XX:XX:02. The current forming candle started at XX:XX:00.
                curr_start = filter_now.replace(second=0, microsecond=0, minute=(filter_now.minute // self.candle_interval_minutes) * self.candle_interval_minutes)
                curr_start_str = curr_start.strftime('%Y-%m-%dT%H:%M:%S+05:30')
                
                if latest_ts == curr_start_str:
                    self.log(f"ℹ️ Ignoring forming candle {latest_ts} (Waiting for close)")
                    ce_candles.pop()
                    if pe_candles and pe_candles[-1]['timestamp'] == curr_start_str:
                        pe_candles.pop()
            
            if ce_candles and pe_candles:
                vwap, cp, ts = self.calculate_synthetic_vwap(ce_candles, pe_candles)
                self.live_vwap = vwap
                self.current_cp = cp
                
                # Store latest close for PnL calc
                self.ce_instrument['last_close'] = ce_candles[-1]['close']
                self.pe_instrument['last_close'] = pe_candles[-1]['close']
                
                self.display_status()
                
                # Logic
                if not self.is_position_open:
                    # Check Exit Cooldown
                    if self.last_exit_time:
                        time_since_exit = (datetime.now() - self.last_exit_time).total_seconds() / 60
                        if time_since_exit < self.exit_cooldown_minutes:
                            self.log(f"⏳ Exit Cooldown Active: {time_since_exit:.1f}/{self.exit_cooldown_minutes} min")
                            continue
                    
                    # Check Data Validity
                    if self.prev_day_cp_low <= 0:
                        self.log("⚠️ Missing Prev Day Data. Retrying Fetch...")
                        self.prev_day_cp_low, self.prev_day_cp_close = self.get_prev_day_combined_low(self.ce_instrument['key'], self.pe_instrument['key'])
                        if self.prev_day_cp_low <= 0:
                            self.log("❌ Still missing Prev Day Data. Skipping Entry.")
                            continue

                    # ENTRY Logic
                    if cp < self.prev_day_cp_low and cp < vwap:
                        # Validate Combined Premium
                        if cp <= 0:
                            self.log(f"⚠️ Invalid Combined Premium: {cp:.2f} (≤0), skipping entry")
                        else:
                            # Check Straddle Width (Skew Check)
                            ce_price = self.ce_instrument['last_close']
                            pe_price = self.pe_instrument['last_close']
                            
                            # Validate Individual Leg Prices
                            if ce_price <= 0 or pe_price <= 0:
                                self.log(f"⚠️ Invalid leg prices: CE={ce_price:.2f}, PE={pe_price:.2f}, skipping entry")
                            else:
                                width_diff = abs(ce_price - pe_price)
                                width_pct = width_diff / cp
                                
                                if width_pct > self.max_straddle_width_pct:
                                    self.log(f"⚠️ Straddle Width Check FAILED: {width_pct*100:.1f}% > {self.max_straddle_width_pct*100:.0f}% | CE: {ce_price:.2f} | PE: {pe_price:.2f}")
                                else:
                                    self.log(f"✅ Entry Condition Met: CP ({cp:.2f}) < PrevLow ({self.prev_day_cp_low:.2f}) & CP < VWAP ({vwap:.2f}) | Width: {width_pct*100:.1f}%")
                                    self.execute_entry()
                    else:
                        self.log(f"⏳ Entry Conditions NOT Met: CP ({cp:.2f}) vs PrevLow ({self.prev_day_cp_low:.2f}) | VWAP ({vwap:.2f})")
                else:
                    # EXIT Logic
                    if cp > vwap:
                        self.log("⚠️ CP crossed above VWAP!")
                        self.exit_all("VWAP Crossover")
                    
                    # Stop Loss Check
                    if cp > (self.entry_price_combined + self.stop_loss_points):
                        self.log(f"🛑 Stop Loss Hit! CP: {cp:.2f} > {self.entry_price_combined + self.stop_loss_points:.2f}")
                        self.exit_all("SL Hit")
                    
                    # Runtime Skew Check (Exit if legs diverge too much - e.g., > 60%)
                    ce_p = self.ce_instrument['last_close']
                    pe_p = self.pe_instrument['last_close']
                    if ce_p > 0 and pe_p > 0 and cp > 0:
                        skew_diff = abs(ce_p - pe_p)
                        skew_pct = skew_diff / cp
                        
                        if skew_pct > self.max_skew_exit_pct:
                            self.log(f"⚠️ Skew Violation: {skew_pct*100:.1f}% > {self.max_skew_exit_pct*100:.0f}% (CE:{ce_p:.1f}, PE:{pe_p:.1f})")
                            self.exit_all(f"Skew Violation > {self.max_skew_exit_pct*100:.0f}%")
            else:
                self.log(f"⚠️ Live 5-Min Candles Not Found/Complete. CE: {len(ce_candles) if ce_candles else 0} | PE: {len(pe_candles) if pe_candles else 0}")

    def on_market_data(self, data):
        """Handle WebSocket Ticks"""
        inst_key = data.get('instrument_key')
        ltp = data.get('ltp')
        if not inst_key or not ltp: return
        
        ts = datetime.now()
        if self.ce_instrument and inst_key == self.ce_instrument['key']:
            self.ce_aggregator.add_tick(inst_key, ts, ltp)
        elif self.pe_instrument and inst_key == self.pe_instrument['key']:
            self.pe_aggregator.add_tick(inst_key, ts, ltp)

if __name__ == "__main__":
    from lib.core.authentication import check_existing_token, perform_authentication, save_access_token
    from lib.api.market_data import download_nse_market_data
    
    # Auth
    if not check_existing_token():
        try:
            token = perform_authentication()
            save_access_token(token)
        except: sys.exit(1)
            
    with open("lib/core/accessToken.txt", "r") as f: token = f.read().strip()
    nse_data = download_nse_market_data()
    
    # Run
    strategy = VWAPStraddleStrategy(
        token, nse_data, 
        lot_size=65, 
        stop_loss_points=30, 
        max_straddle_width_pct=0.20, 
        max_skew_exit_pct=0.55,      # Exit if skew > 60%
        candle_interval_minutes=3,   # Configurable Candle Interval (e.g., 5, 15)
        expiry_type="current_week",  # Options: "current_week", "next_week", "monthly"
        dry_run=True
    )
    strategy.run()

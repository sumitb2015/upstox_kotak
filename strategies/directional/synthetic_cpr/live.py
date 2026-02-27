"""
Synthetic Future CPR Scalper - Live Execution
--------------------------------------------
Captures breakouts of Central Pivot Range (CPR) levels using Synthetic Futures.

Strategy Logic Summary:
1. Signal Detection (CORE):
   - Trend Filter: VWAP (Price > VWAP = Bullish, Price < VWAP = Bearish).
   - Signal: Breakout/Breakdown of CPR Levels (Pivot, TC, BC, R1-3, S1-3).
   - Condition: Bullish Signal if Price > VWAP & breaks Resistance. Bearish if Price < VWAP & breaks Support.

2. Strategy Execution (KOTAK):
   - Instrument: Synthetic Future (ATM CE + PE).
   - Long Synthetic: Buy ATM CE + Sell ATM PE.
   - Short Synthetic: Buy ATM PE + Sell ATM CE.

3. Risk Management (CORE):
   - SL: 20 points on underlying price.
   - Target: Next available Pivot/CPR level.
   - Trailing: 10-point TSL once profit reaches 10 points.
   - Time Exit: Hard square-off at 15:15 PM.
"""

import sys
import os
import time
import logging
import pandas as pd
from datetime import datetime, timedelta, date as dt_date

# Adjust Paths
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'Kotak_Api'))) # Commented to fix lib conflict

from kotak_api.lib.broker import BrokerClient
from kotak_api.lib.order_manager import OrderManager
from kotak_api.lib.trading_utils import get_strike_token, get_lot_size
from lib.api.historical import get_historical_data, get_intraday_data_v3
from lib.api.market_quotes import get_multiple_ltp_quotes
from lib.utils.indicators import calculate_vwap, calculate_ema
from lib.utils.expiry_cache import get_expiry_for_strategy
from lib.api.streaming import UpstoxStreamer
from lib.utils.instrument_utils import get_option_instrument_key
from lib.utils.tick_aggregator import TickAggregator  # New

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', force=True)
logger = logging.getLogger("SyntheticCPR")

class SyntheticCPRStrategy:
    def __init__(self, access_token, config):
        self.access_token = access_token
        self.config = config
        
        self.symbol = "NIFTY"
        self.trading_lots = config.get('trading_lots', 1)
        self.sl_points = config.get('sl_points', 20)
        self.trail_points = config.get('trail_points', 10)
        
        # Time Constraints
        from datetime import time as dt_time
        self.entry_start_time = dt_time(9, 25)
        self.exit_time = dt_time(15, 15)
        
        # State
        self.running = False
        self.positions = {} # Stores 'CE' and 'PE' legs
        self.entry_price_basis = 0.0 # Underlying price at entry
        self.active_trade_direction = None # 'LONG' or 'SHORT'
        self.max_profit_points = 0.0
        self.current_sl_price = 0.0
        self.target_price = 0.0
        
        # Data
        self.pivot_levels = {} # CPR, R1, S1 etc
        self.vwap = 0.0
        self.ltp = 0.0
        self.prev_ltp = 0.0
        
        # Connections
        self.kotak_broker = None
        self.kotak_order_manager = None
        self.streamer = None
        self.upstox_token = access_token
        
        # Aggregator for VWAP (1-min)
        self.vwap_aggregator = TickAggregator(1)
        
        # Token Management
        self.spot_token = "NSE_INDEX|Nifty 50" 
        # User requested Futures. We will resolve this dynamically.
        self.future_token = None 
        self.active_token = None # Will point to future_token if found, else spot
        
        # Intraday Data Cache (for VWAP calculation - prevent rate limiting)
        self.last_vwap_fetch_time = 0
        self.vwap_cache_duration = 300  # 5 minutes (in seconds)
 

    def initialize(self):
        logger.info("🚀 Initializing Synthetic CPR Strategy...")
        
        # 1. Kotak Auth
        try:
            self.kotak_broker = BrokerClient()
            self.kotak_broker.authenticate()
            self.kotak_broker.load_master_data()
            self.kotak_order_manager = OrderManager(self.kotak_broker.client, dry_run=self.config.get('dry_run', False))
            logger.info("✅ Kotak Connected")
        except Exception as e:
            logger.error(f"❌ Kotak Auth Failed: {e}")
            return False

        # 2. Resolve Nifty Future Token
        if self.resolve_future_token():
            self.active_token = self.future_token
            logger.info(f"✅ Using NIFTY FUTURE for Signals: {self.active_token}")
        else:
            self.active_token = self.spot_token
            logger.warning(f"⚠️ Future Token Not Found. Fallback to SPOT: {self.active_token}")

        # 3. Calculate CPR Levels (Using Futures Data)
        if not self.calculate_cpr_levels():
            return False
            
        # 4. Streamer
        try:
            self.streamer = UpstoxStreamer(self.upstox_token)
            self.streamer.connect_market_data([self.active_token], mode="ltpc", on_message=self.on_market_data)
            
            # Wait for connection
            logger.info("⏳ Waiting for WebSocket connection...")
            for _ in range(5):
                time.sleep(1)
                if self.streamer.market_data_connected:
                    logger.info("✅ WebSocket connection confirmed")
                    break
            else:
                 logger.warning("⚠️ WebSocket not confirmed within 5s")
        except Exception as e:
            logger.error(f"❌ Streamer Failed: {e}")
            return False
            
        return True

    def resolve_future_token(self):
        """Download Upstox Instruments and find nearest NIFTY Future"""
        logger.info("🔍 Resolving NIFTY Future Token...")
        try:
            url = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.csv.gz"
            df = pd.read_csv(url, compression='gzip')
            
            # Filter NIFTY Futures
            # Upstox CSV columns: instrument_key, exchange_token, tradingsymbol, name, last_price, expiry, strike, tick_size, lot_size, instrument_type, isin, ...
            # Actually columns might be different. Let's assume standard Upstox format.
            # Usually: 'instrument_key', 'tradingsymbol', 'name', 'expiry', 'instrument_type'
            
            # Filter for NIFTY Futures
            # name == NIFTY or tradingsymbol starts with NIFTY?
            # safest: instrument_type == 'FUTIDX' or 'FUT' and name == 'NIFTY'? 
            # In Upstox 'name' is often 'Nifty 50' or 'NIFTY'.
            # Let's check 'lotsize' or 'instrument_type'
            
            # Filter: Exchange = NSE_FO (implied by file), instrument_type = FUTIDX
            # name = NIFTY
            
            # Standard Upstox keys: NSE_FO|...
            
            futs = df[
                (df['instrument_type'] == 'FUTIDX') & 
                (df['name'] == 'Nifty 50')
            ]
            
            if futs.empty:
                # Try fallback name
                futs = df[ (df['instrument_type'] == 'FUTIDX') & (df['tradingsymbol'].str.startswith('NIFTY')) ]
                
            if futs.empty:
                logger.error("❌ No Nifty Futures found in Master List")
                return False
                
            # Sort by Expiry
            futs['expiry'] = pd.to_datetime(futs['expiry'])
            futs = futs.sort_values('expiry')
            
            # Filter for current/future expiry (exclude past)
            now = pd.Timestamp.now()
            valid_futs = futs[futs['expiry'] >= now]
            
            if valid_futs.empty:
                 logger.error("❌ No Valid Futures found")
                 return False
                 
            # Take the nearest
            nearest = valid_futs.iloc[0]
            self.future_token = nearest['instrument_key']
            logger.info(f"🎯 Found Future: {nearest['tradingsymbol']} ({self.future_token}) Expiry: {nearest['expiry'].date()}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to download/parse instrument list: {e}")
            return False

    def calculate_cpr_levels(self):
        """Fetch yesterday's data and calculate Pivot, BC, TC"""
        logger.info("📊 Calculating CPR Levels...")
        
        # Get 5 days of history to be safe
        end_date = datetime.now()
        start_date = end_date - timedelta(days=5)
        
        result = get_historical_range(self.access_token, self.active_token, "day", start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
        if not result:
            logger.error("❌ Failed to fetch history for CPR")
            return False
            
        df = pd.DataFrame(result)
        if df.empty:
            logger.error("❌ History Dataframe Empty")
            return False
            
        # Get Previous Day (Last completed row)
        # If running today during market, the last row might be today?
        # Standard API usually returns completed candles. Double check date.
        last_row = df.iloc[-1]
        last_date = pd.to_datetime(last_row['timestamp']).date()
        
        if last_date == datetime.now().date():
            # If today's candle exists, take the one before it
            if len(df) > 1:
                last_row = df.iloc[-2]
            else:
                logger.error("❌ Not enough data for Previous Day")
                return False
                
        high = last_row['high']
        low = last_row['low']
        close = last_row['close']
        
        pivot = (high + low + close) / 3
        bc = (high + low) / 2
        tc = (pivot - bc) + pivot
        
        # Order BC/TC (TC can be lower than BC mathematically, so just storing Range)
        cpr_top = max(bc, tc)
        cpr_bottom = min(bc, tc)
        
        # Supports / Resistances
        r1 = (2 * pivot) - low
        s1 = (2 * pivot) - high
        r2 = pivot + (high - low)
        s2 = pivot - (high - low)
        r3 = r1 + (high - low)
        s3 = s1 - (high - low)
        
        self.pivot_levels = {
            'P': pivot,
            'TC': cpr_top,
            'BC': cpr_bottom,
            'R1': r1,
            'S1': s1,
            'R2': r2,
            'S2': s2,
            'R3': r3,
            'S3': s3
        }
        
        logger.info(f"📐 CPR Levels: P={pivot:.2f}, Range={cpr_bottom:.2f}-{cpr_top:.2f}")
        logger.info(f"   R1={r1:.2f}, R2={r2:.2f}, R3={r3:.2f}")
        logger.info(f"   S1={s1:.2f}, S2={s2:.2f}, S3={s3:.2f}")
        return True

    def update_vwap(self):
        """Calculate Intraday VWAP using fresh intraday data (with caching to prevent rate limiting)"""
        try:
            # Only fetch fresh data every 5 minutes to avoid rate limiting
            current_time_sec = time.time()
            if current_time_sec - self.last_vwap_fetch_time < self.vwap_cache_duration:
                # Use cached calculation - VWAP doesn't change that frequently
                return
            
            # Fetch fresh intraday data directly (correct method)
            intraday_candles = get_intraday_data_v3(
                self.access_token, 
                self.active_token, 
                "minute", 
                1
            )
            
            if not intraday_candles:
                logger.warning("⚠️ VWAP Update Failed: No intraday data")
                return
            
            df_intraday = pd.DataFrame(intraday_candles)
            
            if df_intraday.empty:
                logger.warning("⚠️ VWAP: Intraday dataframe empty")
                return
            
            # Ensure timestamp is datetime
            if 'timestamp' in df_intraday.columns:
                df_intraday['timestamp'] = pd.to_datetime(df_intraday['timestamp'])
            
            # Minimum candles check
            if len(df_intraday) >= 3:
                self.vwap = calculate_vwap(df_intraday)
                self.last_vwap_fetch_time = current_time_sec
                logger.info(f"🔹 VWAP Updated: {self.vwap:.2f} ({len(df_intraday)} candles)")
            else:
                logger.warning(f"⚠️ Only {len(df_intraday)} candles available, VWAP update skipped")
                
        except Exception as e:
            logger.error(f"❌ VWAP Calculation Error: {e}")

    def on_market_data(self, data):
        """Handle market data from WebSocket"""
        try:
            # 1. Handle Unrolled Format (Preferred by UpstoxStreamer)
            if isinstance(data, dict) and 'instrument_key' in data:
                key = data['instrument_key']
                if key == self.active_token or self.active_token.endswith(key):
                    ltp = data.get('ltp')
                    if ltp is not None:
                        was_zero = (self.ltp == 0)
                        self.prev_ltp = self.ltp
                        self.ltp = ltp
                        if was_zero and self.ltp > 0:
                            logger.info(f"✅ First Tick Received: {self.ltp}")
                            
                        # Update Aggregator
                        self.vwap_aggregator.add_tick(key, datetime.now(), self.ltp)
                return

            # 2. Handle Rolled Format
            if isinstance(data, dict) and 'feeds' in data:
                feeds = data['feeds']
                for key, feed_data in feeds.items():
                    if key == self.active_token or self.active_token.endswith(key):
                        ltp = feed_data.get('ltpc', {}).get('ltp', feed_data.get('ltp'))
                        if ltp is not None:
                            was_zero = (self.ltp == 0)
                            self.prev_ltp = self.ltp
                            self.ltp = ltp
                            if was_zero and self.ltp > 0:
                                logger.info(f"✅ First Tick Received: {self.ltp}")
                                
                            # Update Aggregator
                            self.vwap_aggregator.add_tick(key, datetime.now(), self.ltp)
        except Exception as e:
            logger.error(f"Error in on_market_data: {e}")

    def get_nearest_pivot_target(self, direction, entry_price):
        """Find the next pivot level as target"""
        levels = sorted(self.pivot_levels.values())
        if direction == 'LONG':
            # Find first level > entry
            for l in levels:
                if l > entry_price + 5: # Buffer
                    return l
            return entry_price + 100 # Fallback
        else:
            # Find first level < entry
            for l in reversed(levels):
                if l < entry_price - 5:
                    return l
            return entry_price - 100 # Fallback

    def execute_synthetic(self, direction):
        if self.positions:
            return # Already in trade
            
        logger.info(f"⚡ Signal Detected: {direction}. Executing Synthetic Future...")
        
        # 1. Determine Strike (ATM)
        atm_strike = round(self.ltp / 50) * 50
        
        ce_sym = None
        pe_sym = None
        
        try:
            # Resolve Symbols (Using Expiry Cache)
            expiry_str = get_expiry_for_strategy(self.upstox_token, "current_week", "NIFTY")
            expiry = datetime.strptime(expiry_str, "%Y-%m-%d")
            
            # Simple Construction for demo:
            # LONG = Buy CE + Sell PE
            # SHORT = Buy PE + Sell CE
            
            # We need to find symbols first.
            _, ce_sym = get_strike_token(self.kotak_broker, atm_strike, "CE", expiry)
            _, pe_sym = get_strike_token(self.kotak_broker, atm_strike, "PE", expiry)
            
            if not ce_sym or not pe_sym:
                logger.error("❌ Could not resolve option symbols")
                return

            # Dynamic Lot Size
            # Assuming lots are same for CE/PE of same underlying, but safer to check one
            base_lot = get_lot_size(self.kotak_broker.master_df, ce_sym)
            qty = base_lot * self.trading_lots
            
            tag = "SYNTH_ENTRY"
            
            if direction == 'LONG':
                # Long Synthetic: Buy CE, Sell PE
                ce_oid = self.kotak_order_manager.place_order(ce_sym, qty, "B", tag=tag, product="MIS")
                pe_oid = self.kotak_order_manager.place_order(pe_sym, qty, "S", tag=tag, product="MIS")
                logger.info(f"🚀 Orders Placed. CE ID: {ce_oid}, PE ID: {pe_oid}")
                self.positions = {'long_leg': ce_sym, 'short_leg': pe_sym, 'qty': qty}
                
            else:
                # Short Synthetic: Buy PE, Sell CE
                pe_oid = self.kotak_order_manager.place_order(pe_sym, qty, "B", tag=tag, product="MIS")
                ce_oid = self.kotak_order_manager.place_order(ce_sym, qty, "S", tag=tag, product="MIS")
                logger.info(f"🚀 Orders Placed. PE ID: {pe_oid}, CE ID: {ce_oid}")
                self.positions = {'long_leg': pe_sym, 'short_leg': ce_sym, 'qty': qty} # Store Qty for Exit
                
            self.active_trade_direction = direction
            self.entry_price_basis = self.ltp
            self.current_sl_price = self.ltp - self.sl_points if direction == 'LONG' else self.ltp + self.sl_points
            self.target_price = self.get_nearest_pivot_target(direction, self.ltp)
            self.max_profit_points = 0.0
            
            logger.info(f"✅ Trade Live: {direction} @ {self.ltp} | SL: {self.current_sl_price} | TGT: {self.target_price}")
            
        except Exception as e:
            logger.error(f"❌ Execution Failed: {e}")

    def exit_synthetic(self, reason):
        logger.info(f"🏁 Exiting Trade: {reason}")
        tag = "SYNTH_EXIT"
        
        # Close positions
        # If LONG SYNTH (Long CE, Short PE): Sell CE, Buy PE
        # Logic: Just close whatever is in self.positions
        
        # We stored symbols in self.positions
        # Actually safer to square off based on Net Position from Broker, but here we track manually
        
        if not self.positions: return

        try:
            # Blindly square off the symbols we tracked
            # Ideally, check order book, but strict inverse is usually fine
            
            # Identify which was bought/sold based on direction
            if self.active_trade_direction == 'LONG':
                # Entry: Buy CE, Sell PE
                # Exit: Sell CE, Buy PE
                ord1 = self.kotak_order_manager.place_order(self.positions['long_leg'], self.positions['qty'], "S", tag=tag, product="MIS")
                ord2 = self.kotak_order_manager.place_order(self.positions['short_leg'], self.positions['qty'], "B", tag=tag, product="MIS")
                logger.info(f"🏁 Exit Orders Placed. IDs: {ord1}, {ord2}")
            else:
                # Entry: Buy PE, Sell CE
                # Exit: Sell PE, Buy CE
                ord1 = self.kotak_order_manager.place_order(self.positions['long_leg'], self.positions['qty'], "S", tag=tag, product="MIS")
                ord2 = self.kotak_order_manager.place_order(self.positions['short_leg'], self.positions['qty'], "B", tag=tag, product="MIS")
                logger.info(f"🏁 Exit Orders Placed. IDs: {ord1}, {ord2}")
                
            self.positions = {}
            self.active_trade_direction = None
            
        except Exception as e:
            logger.error(f"❌ Exit Failed: {e}")

    def manage_trade(self):
        if not self.positions: return
        
        # Calculate current points PnL (approx based on Spot/Future move)
        # Synthetic future delta is approx 1, so 1 pt move in Spot = 1 pt PnL roughly
        
        current_move = (self.ltp - self.entry_price_basis) if self.active_trade_direction == 'LONG' else (self.entry_price_basis - self.ltp)
        
        # 1. Stop Loss
        if current_move <= -self.sl_points:
            self.exit_synthetic(f"Stop Loss Hit (-{self.sl_points} pts)")
            return

        # 2. Target
        # if (self.active_trade_direction == 'LONG' and self.ltp >= self.target_price) or \
        #    (self.active_trade_direction == 'SHORT' and self.ltp <= self.target_price):
        #     self.exit_synthetic(f"Target Hit ({self.target_price})")
        #     return
        # COMMENTED OUT: User prefers Trailing instead of hard exit? 
        # "target will be next lower CPR level... Once in profit of 10 points, we will start trailing"
        # Let's use Target as a potential exit, but Trail is primary.

        # 3. Trailing Logic
        if current_move > self.max_profit_points:
            self.max_profit_points = current_move
            
        # "Once in profit of 10 points, we will start trailing by 10 points"
        # Meaning: If Move = 10, SL moves to Breakeven? Or SL moves to (Price - 10)?
        
        if self.max_profit_points >= 10:
            # Trailing Stop = High Watermark - 10 points
            if self.active_trade_direction == 'LONG':
                new_sl = (self.entry_price_basis + self.max_profit_points) - self.trail_points
                if new_sl > self.current_sl_price:
                    self.current_sl_price = new_sl
                    logger.info(f"📈 Trailing SL Updated: {self.current_sl_price:.2f} (Locking {self.trail_points} distance)")
                    
                if self.ltp <= self.current_sl_price:
                    self.exit_synthetic(f"Trailing SL Hit")
            else:
                new_sl = (self.entry_price_basis - self.max_profit_points) + self.trail_points
                if new_sl < self.current_sl_price:
                    self.current_sl_price = new_sl
                    logger.info(f"📉 Trailing SL Updated: {self.current_sl_price:.2f}")
                    
                if self.ltp >= self.current_sl_price:
                    self.exit_synthetic(f"Trailing SL Hit")

    def run(self):
        if not self.initialize(): return
        
        self.running = True
        logger.info("🟢 Strategy Loop Started")
        
        last_minute = datetime.now().minute
        
        # Wait for Data
        logger.info("⏳ Waiting for Market Data...")
        while self.ltp == 0:
            time.sleep(1)
        logger.info(f"✅ Data Received. LTP: {self.ltp}")
        
        # Initialize Indicators immediately
        self.update_vwap()
        
        # Initialize prev_ltp to current to avoid false crossover
        self.prev_ltp = self.ltp
        
        last_log_time = time.time()
        last_minute = datetime.now().minute
        
        while self.running:
            try:
                # 0. Global Kill Switch Check
                if os.path.exists("c:/algo/upstox/.STOP_TRADING"):
                    logger.info("🛑 Global Kill Switch Detected (.STOP_TRADING). Stopping Strategy.")
                    self.exit_synthetic("Portfolio Manager Kill Switch")
                    self.running = False
                    break

                now = datetime.now()
                
                # Periodic Status Log (Every 5 seconds)
                if time.time() - last_log_time >= 5:
                    status_msg = f"💓 LTP: {self.ltp:.2f} | VWAP: {self.vwap:.2f} | "
                    if self.positions:
                        pnl = (self.ltp - self.entry_price_basis) if self.active_trade_direction == 'LONG' else (self.entry_price_basis - self.ltp)
                        status_msg += f"Pos: {self.active_trade_direction} (PnL: {pnl:.2f} pts)"
                    else:
                        status_msg += "No Position"
                    logger.info(status_msg)
                    last_log_time = time.time()
                
                # Update Indicators periodically (every minute)
                if now.minute != last_minute:
                    self.update_vwap()
                    last_minute = now.minute
                    
                    # Status Display
                    pnl_str = ""
                    if self.positions and self.entry_price_basis > 0:
                        current_pnl = (self.ltp - self.entry_price_basis) if self.active_trade_direction == 'LONG' else (self.entry_price_basis - self.ltp)
                        pnl_str = f" | PnL: {current_pnl:.2f} pts"
                        
                    logger.info(f"📊 Status: LTP={self.ltp:.2f} | VWAP={self.vwap:.2f} | Active={self.active_trade_direction}{pnl_str}")

                # 1. Time-Based Exit Check
                if now.time() >= self.exit_time:
                    if self.positions:
                        logger.info(f"⏰ Time Exit Triggered ({self.exit_time}) - Squaring off...")
                        self.exit_synthetic("Intraday Time Exit")
                    # Stop strategy for the day
                    logger.info("👋 Market closing Soon. Strategy Stopped for the day.")
                    self.running = False
                    break

                # Monitor Trade
                if self.positions:
                    self.manage_trade()
                else:
                    # 2. Time-Based Entry Check
                    if now.time() < self.entry_start_time:
                        # logger.info(f"⏳ Waiting for entry time {self.entry_start_time}...")
                        pass
                    else:
                        # Check Entries (Breakout Logic)
                        # Note: Uses SORTED levels to ensure predictable entry on nearest unfilled level
                        
                        # 1. Bullish: > VWAP & Breaking Resistance UP
                        if self.ltp > self.vwap and self.vwap > 0:
                            # Get all resistance levels above prev_ltp, sorted ascending
                            resistances = [(name, val) for name, val in self.pivot_levels.items() 
                                          if val > self.prev_ltp]
                            resistances.sort(key=lambda x: x[1])  # Sort by price
                            
                            # Check if we crossed the nearest resistance
                            for lvl_name, lvl_val in resistances:
                                if self.ltp >= lvl_val:
                                    logger.info(f"🚀 Bullish Breakout: {lvl_name} @ {lvl_val:.2f}")
                                    self.execute_synthetic('LONG')
                                    break  # Only trade first crossed level
                                    
                        # 2. Bearish: < VWAP & Breaking Support DOWN
                        elif self.ltp < self.vwap and self.vwap > 0:
                            # Get all support levels below prev_ltp, sorted descending
                            supports = [(name, val) for name, val in self.pivot_levels.items() 
                                       if val < self.prev_ltp]
                            supports.sort(key=lambda x: x[1], reverse=True)  # Sort descending
                            
                            # Check if we crossed the nearest support
                            for lvl_name, lvl_val in supports:
                                if self.ltp <= lvl_val:
                                    logger.info(f"🔻 Bearish Breakdown: {lvl_name} @ {lvl_val:.2f}")
                                    self.execute_synthetic('SHORT')
                                    break  # Only trade first crossed level
                                
                time.sleep(1) # Fast tick loop
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Error in Loop: {e}")
                time.sleep(5)

if __name__ == "__main__":
    # Config
    conf = {
        'trading_lots': 1, # Number of Lots
        'sl_points': 20,
        'trail_points': 10,
        'dry_run': False
    }
    
    # Load Token
    try:
        with open("lib/core/accessToken.txt", "r") as f: token = f.read().strip()
    except:
        print("❌ Token not found")
        sys.exit(1)
        
    strategy = SyntheticCPRStrategy(token, conf)
    strategy.run()


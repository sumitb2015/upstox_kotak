"""
ATM Short Straddle Strategy - Live Implementation

Sells ATM straddle at 9:20 AM and adjusts based on CE/PE ratio.
"""

import sys
import os
import time
import logging
import threading
from datetime import datetime, time as dt_time
from typing import Optional

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

# Import configuration
from strategies.non_directional.atm_straddle_ratio.config import *
from strategies.non_directional.atm_straddle_ratio.strategy_core import StraddleCore, Position

# Import library functions (following AGENT.md)
from lib.core.authentication import check_existing_token
from lib.api.market_data import download_nse_market_data
from lib.api.option_chain import get_option_chain_dataframe, get_atm_strike_from_chain
from lib.utils.expiry_cache import get_expiry_for_strategy
from lib.api.streaming import UpstoxStreamer
from lib.api.historical import get_historical_data
from lib.utils.indicators import calculate_supertrend
import pandas as pd

# Kotak API Imports
from kotak_api.lib.broker import BrokerClient
from kotak_api.lib.order_manager import OrderManager
from kotak_api.lib.trading_utils import get_strike_token, get_lot_size

# Setup logging with UTF-8 encoding for emojis
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
# Force UTF-8 encoding and line-buffering for console output on Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

logger = logging.getLogger(__name__)


class ATMStraddleStrategy:
    """ATM Short Straddle with Ratio-Based Adjustment"""
    
    def __init__(self, upstox_token: str):
        self.upstox_token = upstox_token
        self.nse_data = None
        self.expiry = None
        self.position: Optional[Position] = None
        self.upstox_streamer = None
        self.core = StraddleCore()
        
        # Kotak components
        self.kotak_broker = BrokerClient()
        self.kotak_client = None
        self.order_mgr = None
        
        # State tracking
        self.entry_done = False
        self.entry_retries = 0
        self.next_entry_attempt = 0
        self.last_atm_check = 0
        self.last_ratio_log = 0
        
        # Price tracking (Upstox)
        self.ce_price = 0.0
        self.pe_price = 0.0
        
        # Thread safety for WebSocket updates
        self.price_lock = threading.Lock()
        
    def initialize(self):
        """Initialize strategy - load data and setup"""
        logger.info("="*80)
        logger.info(f"🚀 [CORE] Initializing {STRATEGY_NAME} (Multi-Broker)")
        logger.info("="*80)
        
        # 0. Validate Config
        # validate_config() # Assuming function exists or implement manual check
        # Since config.py is star-imported, we check critical constants
        if LOT_SIZE <= 0 or PROFIT_TARGET <= 0 or abs(STOP_LOSS) <= 0:
             logger.error("❌ Invalid Configuration Parameters")
             sys.exit(1)
        
        # 1. Initialize Upstox Data
        logger.info("📊 [UPSTOX] Loading NSE market data...")
        self.nse_data = download_nse_market_data()
        logger.info(f"✅ [UPSTOX] Loaded {len(self.nse_data)} instruments")
        
        # Get Upstox expiry 
        self.expiry_dt = get_expiry_for_strategy(
            self.upstox_token,
            EXPIRY_TYPE,
            UNDERLYING
        )
        # Handle string vs datetime
        if isinstance(self.expiry_dt, str):
            self.expiry_obj = datetime.strptime(self.expiry_dt, '%Y-%m-%d')
        else:
            self.expiry_obj = self.expiry_dt
            self.expiry_dt = self.expiry_obj.strftime('%Y-%m-%d')
            
        logger.info(f"📅 [UPSTOX] Expiry identified: {self.expiry_dt}")
        
        # 2. Initialize Kotak Execution
        logger.info("🔐 [KOTAK] Authenticating with Neo API...")
        try:
            self.kotak_client = self.kotak_broker.authenticate()
            logger.info("📊 [KOTAK] Loading master data...")
            self.kotak_broker.load_master_data()
            self.order_mgr = OrderManager(self.kotak_client, dry_run=DRY_RUN)
            logger.info("✅ [KOTAK] Execution broker initialized")
        except Exception as e:
            logger.error(f"❌ [KOTAK] Initialization failed: {e}")
            raise
        
        # 3. Initialize Upstox Streaming
        logger.info("📡 [UPSTOX] Connecting to WebSocket...")
        self.upstox_streamer = UpstoxStreamer(self.upstox_token)
        logger.info("✅ [UPSTOX] Real-time data stream initialized")
        
        if DRY_RUN:
            logger.warning("⚠️  [CORE] DRY RUN MODE ENABLED - Orders will be simulated")

    
    def get_current_atm(self) -> int:
        """Get current ATM strike from option chain"""
        try:
            chain_df = get_option_chain_dataframe(
                self.upstox_token,
                f"NSE_INDEX|{UNDERLYING.capitalize()} 50",
                self.expiry_dt
            )
            
            if chain_df is None or chain_df.empty:
                logger.error("❌ Failed to fetch option chain")
                return None, None
            
            atm_strike = get_atm_strike_from_chain(chain_df)
            spot = chain_df['spot_price'].iloc[0]
            
            logger.info(f"📍 [UPSTOX] Spot: ₹{spot:.2f} | ATM Strike: {atm_strike}")
            return atm_strike, spot
            
        except Exception as e:
            logger.error(f"❌ [UPSTOX] Error getting ATM: {e}")
            return None, None

    def check_vix_condition(self):
        """
        Check if India VIX is Below Supertrend(10,3) and Falling (Red Candle).
        Returns True if condition met.
        """
        try:
            vix_key = "NSE_INDEX|India VIX"
            
            # Fetch Historical Data (for Supertrend warmup)
            hist_candles = get_historical_data(
                self.upstox_token,
                vix_key,
                "5minute",
                lookback_minutes=375 * 3 # 3 Days
            )
            
            # Fetch Intraday Data (for live candle)
            from lib.api.historical import get_intraday_data_v3
            intra_candles = get_intraday_data_v3(
                self.upstox_token,
                vix_key,
                "minute",
                5
            )
            
            if not hist_candles and not intra_candles:
                logger.warning("⚠️ [CORE] VIX Data Unavailable")
                return False
            
            # Process Historical
            df_hist = pd.DataFrame(hist_candles) if hist_candles else pd.DataFrame()
            if not df_hist.empty:
                df_hist['timestamp'] = pd.to_datetime(df_hist['timestamp'])
                if df_hist['timestamp'].dt.tz is None:
                    df_hist['timestamp'] = df_hist['timestamp'].dt.tz_localize('UTC').dt.tz_convert('Asia/Kolkata')
                else:
                    df_hist['timestamp'] = df_hist['timestamp'].dt.tz_convert('Asia/Kolkata')
            
            # Process Intraday
            df_intra = pd.DataFrame(intra_candles) if intra_candles else pd.DataFrame()
            if not df_intra.empty:
                df_intra['timestamp'] = pd.to_datetime(df_intra['timestamp'])
                if df_intra['timestamp'].dt.tz is None:
                    df_intra['timestamp'] = df_intra['timestamp'].dt.tz_localize('UTC').dt.tz_convert('Asia/Kolkata')
                else:
                    df_intra['timestamp'] = df_intra['timestamp'].dt.tz_convert('Asia/Kolkata')
            
            # Merge and Deduplicate
            if not df_hist.empty and not df_intra.empty:
                start_of_today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).astimezone(df_hist['timestamp'].dt.tz)
                df_hist = df_hist[df_hist['timestamp'] < start_of_today]
                df = pd.concat([df_hist, df_intra]).sort_values('timestamp').drop_duplicates('timestamp')
            else:
                df = df_intra if not df_intra.empty else df_hist
            
            if df.empty or len(df) < 20:
                logger.warning("⚠️ [CORE] VIX Data Insufficient")
                return False
            
            # Calculate Supertrend
            trend, st_value = calculate_supertrend(df, period=10, multiplier=3.0)
            
            current_close = df['close'].iloc[-1]
            current_open = df['open'].iloc[-1]
            last_candle_time = df['timestamp'].iloc[-1]
            
            # Conditions:
            # 1. Below Supertrend
            is_below_st = current_close < st_value
            
            # 2. Falling (Red Candle)
            is_falling = current_close < current_open
            
            logger.info(f"📊 [CORE] VIX Check [{last_candle_time.strftime('%H:%M')}]: Close={current_close:.2f} | ST={st_value:.2f} | Falling={is_falling}")
            
            if is_below_st and is_falling:
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"❌ [CORE] VIX Check Error: {e}")
            import traceback
            traceback.print_exc()
            return False # Fail safe
    
    def enter_straddle(self, strike: int):
        """Enter ATM straddle position"""
        logger.info("="*80)
        logger.info(f"🎯 [CORE] ENTERING ATM STRADDLE at {strike}")
        logger.info("="*80)
        
        try:
            # 1. Resolve Upstox Keys (for monitoring)
            from lib.utils.instrument_utils import get_option_instrument_key
            ce_upstox_key = get_option_instrument_key(UNDERLYING, strike, "CE", self.nse_data)
            pe_upstox_key = get_option_instrument_key(UNDERLYING, strike, "PE", self.nse_data)
            
            # 2. Resolve Kotak Symbols (for execution)
            ce_kotak_token, ce_trading_symbol = get_strike_token(self.kotak_broker, strike, "CE", self.expiry_obj)
            pe_kotak_token, pe_trading_symbol = get_strike_token(self.kotak_broker, strike, "PE", self.expiry_obj)
            
            if not ce_upstox_key or not pe_upstox_key or not ce_trading_symbol or not pe_trading_symbol:
                logger.error(f"❌ [CORE] Symbol resolution failed")
                return False
            
            logger.info(f"📝 [UPSTOX] Keys: CE={ce_upstox_key}, PE={pe_upstox_key}")
            logger.info(f"📝 [KOTAK] Symbols: CE={ce_trading_symbol}, PE={pe_trading_symbol}")
            
            # 3. Get Entry Prices (Upstox)
            chain_df = get_option_chain_dataframe(
                self.upstox_token,
                f"NSE_INDEX|{UNDERLYING.capitalize()} 50",
                self.expiry_dt
            )
            
            strike_data = chain_df[chain_df['strike_price'] == strike].iloc[0]
            ce_price = strike_data['ce_ltp']
            pe_price = strike_data['pe_ltp']
            
            logger.info(f"📊 [UPSTOX] CE Ltp: ₹{ce_price:.2f} | PE Ltp: ₹{pe_price:.2f}")
            
            # 4. Place Orders via Kotak
            lot_size = get_lot_size(self.kotak_broker.master_df, ce_trading_symbol)
            qty = LOT_SIZE * lot_size
            
            logger.info(f"🚀 [KOTAK] Placing SELL orders (Qty: {qty} total)...")
            
            # Atomic Execution Tracking
            executed_legs = []
            
            # Leg 1: CE
            ce_oid = self.order_mgr.place_order(ce_trading_symbol, qty, "S", tag="Straddle_Entry")
            if ce_oid:
                executed_legs.append({'symbol': ce_trading_symbol, 'qty': qty, 'type': 'S'})
            
            # Leg 2: PE
            pe_oid = None
            if ce_oid: # Only try PE if CE succeeded (or try parallel? Sequential safer for now)
                pe_oid = self.order_mgr.place_order(pe_trading_symbol, qty, "S", tag="Straddle_Entry")
                if pe_oid:
                    executed_legs.append({'symbol': pe_trading_symbol, 'qty': qty, 'type': 'S'})
            
            # Check Failure
            if len(executed_legs) < 2:
                logger.error("❌ [CORE] Partial Execution Detected! Rolling back...")
                
                # Rollback Logic
                for leg in executed_legs:
                    logger.warning(f"⏪ [CORE] Rolling back {leg['symbol']}...")
                    # Reverse Type: S -> B
                    exit_type = "B" if leg['type'] == "S" else "S"
                    self.order_mgr.place_order(leg['symbol'], leg['qty'], exit_type, tag="Rollback")
                
                return False
            
            # Create position object
            self.position = Position(
                strike=strike,
                ce_lots=LOT_SIZE,
                pe_lots=LOT_SIZE,
                ce_entry_price=ce_price,
                pe_entry_price=pe_price,
                ce_current_price=ce_price,
                pe_current_price=pe_price,
                ce_instrument_key=ce_upstox_key,
                pe_instrument_key=pe_upstox_key,
                ce_trading_symbol=ce_trading_symbol,
                pe_trading_symbol=pe_trading_symbol,
                entry_time=datetime.now().strftime("%H:%M:%S")
            )
            
            # Start Upstox WebSocket for price tracking
            self.start_websocket([ce_upstox_key, pe_upstox_key])
            
            logger.info("✅ Straddle entered successfully via Kotak")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error entering straddle: {e}")
            return False

    
    def start_websocket(self, instrument_keys: list):
        """Start Upstox WebSocket to track option prices"""
        def on_price_update(data):
            """Handle price updates from WebSocket"""
            try:
                instrument_key = data.get('instrument_key')
                ltp = data.get('last_price', 0)
                
                if not ltp:
                    return
                
                # Update prices with thread safety
                with self.price_lock:
                    if self.position:
                        if instrument_key == self.position.ce_instrument_key:
                            self.ce_price = ltp
                            self.position.ce_current_price = ltp
                        elif instrument_key == self.position.pe_instrument_key:
                            self.pe_price = ltp
                            self.position.pe_current_price = ltp
                
            except Exception as e:
                logger.error(f"Error in price update: {e}")
        
        try:
            self.upstox_streamer.connect_market_data(
                instrument_keys=instrument_keys,
                mode=WEBSOCKET_MODE,
                on_message=on_price_update
            )
            # Wait for connection
            logger.info("⏳ [UPSTOX] Waiting for WebSocket connection...")
            for _ in range(5):
                time.sleep(1)
                if self.upstox_streamer.market_data_connected:
                    logger.info("✅ [UPSTOX] WebSocket connection confirmed")
                    break
            else:
                 logger.warning("⚠️ [UPSTOX] WebSocket not confirmed within 5s")
        except Exception as e:
            logger.error(f"❌ [UPSTOX] WebSocket connection failed: {e}")
    
    def check_and_adjust(self):
        """Check ratio and adjust position if needed"""
        if not self.position:
            return
        
        # Read prices with thread safety
        with self.price_lock:
            ce_price = self.ce_price
            pe_price = self.pe_price
        
        if ce_price == 0 or pe_price == 0:
            return
        
        # Calculate ratio
        ratio = self.core.calculate_ratio(ce_price, pe_price)
        
        # Log ratio periodically (every 30 seconds)
        current_time = time.time()
        if current_time - self.last_ratio_log > 30:
            pnl = self.position.calculate_pnl()
            logger.info(f"📊 [CORE] Status: Ratio {ratio:.3f} | CE: ₹{self.ce_price:.2f} | PE: ₹{self.pe_price:.2f} | P&L: ₹{pnl:,.2f}")
            self.last_ratio_log = current_time
        
        # Check if adjustment needed
        if not self.core.check_adjustment_needed(ratio, RATIO_THRESHOLD):
            return
        
        logger.warning(f"⚠️  [CORE] Ratio {ratio:.3f} < threshold {RATIO_THRESHOLD} - Adjustment triggered")
        
        # Check for new ATM (rate limited)
        if current_time - self.last_atm_check < ATM_CHECK_INTERVAL:
            return
        
        self.last_atm_check = current_time
        
        # Get current ATM
        new_atm, spot = self.get_current_atm()
        if not new_atm:
            return
        
        # Decide action
        if self.core.should_switch_to_new_atm(self.position.strike, spot, new_atm):
            logger.info(f"🔄 [CORE] Switching to new ATM: {self.position.strike} → {new_atm}")
            self.switch_to_new_atm(new_atm)
        else:
            logger.info("⚖️  [CORE] Balancing position - selling profitable side")
            self.balance_position()
    
    def switch_to_new_atm(self, new_strike: int):
        """
        Exit current straddle to switch to new ATM.
        Note: We do NOT immediately enter the new position here.
        We reset 'entry_done' to False, allowing the main loop to pick it up.
        This ensures the VIX Filter is re-checked before the new entry.
        """
        logger.info(f"🔄 Switching Logic Triggered. Old Strike: {self.position.strike} -> Target: {new_strike}")
        
        # Exit current position
        self.exit_position("Switching to new ATM")
        
        # Reset entry flag to trigger re-evaluation in main loop
        logger.info("⏳ [CORE] Resetting entry flag. Main loop will validate VIX before re-entry.")
        self.entry_done = False
        self.entry_retries = 0 # Reset retries for the new entry attempt
    
    def balance_position(self):
        """Sell additional lot of profitable side via Kotak"""
        profitable_side = self.core.determine_profitable_side(
            self.ce_price, self.pe_price,
            self.position.ce_entry_price, self.position.pe_entry_price
        )
        
        logger.info(f"⚖️  Selling 1 more lot of {profitable_side} via Kotak")
        
        # Determine symbol and qty
        symbol = self.position.ce_trading_symbol if profitable_side == "CE" else self.position.pe_trading_symbol
        lot_size = get_lot_size(self.kotak_broker.master_df, symbol)
        qty = 1 * lot_size
        
        # Place order via Kotak
        order_id = self.order_mgr.place_order(
            symbol=symbol,
            qty=qty,
            transaction_type="S",
            tag="Straddle_Adjustment"
        )
        
        if order_id:
            if profitable_side == "CE":
                self.position.ce_lots += 1
            else:
                self.position.pe_lots += 1
            logger.info(f"✅ Additional {profitable_side} lot sold via Kotak")
        else:
            logger.error(f"❌ Failed to sell additional {profitable_side} via Kotak")

    
    def check_exit_conditions(self) -> bool:
        """Check if exit conditions are met"""
        if not self.position:
            return False
        
        pnl = self.position.calculate_pnl()
        
        should_exit, reason = self.core.check_exit_conditions(
            pnl, PROFIT_TARGET, STOP_LOSS
        )
        
        if should_exit:
            logger.info(f"🚪 EXIT TRIGGERED: {reason}")
            self.exit_position(reason)
            return True
        
        return False
    
    def exit_position(self, reason: str):
        """Exit all positions via Kotak"""
        if not self.position:
            return
        
        pnl = self.position.calculate_pnl()
        
        logger.info("="*80)
        logger.info(f"🚪 [CORE] EXITING POSITION: {reason}")
        logger.info(f"💰 [CORE] Final P&L: ₹{pnl:,.2f}")
        logger.info("="*80)
        
        # 1. Close CE Position via Kotak
        if self.position.ce_lots > 0:
            lot_size = get_lot_size(self.kotak_broker.master_df, self.position.ce_trading_symbol)
            qty = self.position.ce_lots * lot_size
            logger.info(f"📉 [KOTAK] Square-off CE ({self.position.ce_trading_symbol}, Qty: {qty})...")
            oid = self.order_mgr.place_order(
                symbol=self.position.ce_trading_symbol,
                qty=qty,
                transaction_type="B",
                tag="Straddle_Exit"
            )
            if oid: logger.info(f"   ✅ CE Exit Order: {oid}")
        
        # 2. Close PE Position via Kotak
        if self.position.pe_lots > 0:
            lot_size = get_lot_size(self.kotak_broker.master_df, self.position.pe_trading_symbol)
            qty = self.position.pe_lots * lot_size
            logger.info(f"📈 [KOTAK] Square-off PE ({self.position.pe_trading_symbol}, Qty: {qty})...")
            oid = self.order_mgr.place_order(
                symbol=self.position.pe_trading_symbol,
                qty=qty,
                transaction_type="B",
                tag="Straddle_Exit"
            )
            if oid: logger.info(f"   ✅ PE Exit Order: {oid}")
        
        # 3. Disconnect Upstox WebSocket
        if self.upstox_streamer:
            try:
                self.upstox_streamer.disconnect_all()
            except:
                pass
        
        self.position = None
        logger.info("✅ [CORE] Position exited successfully")
    
    def run(self):
        """Main strategy loop"""
        try:
            self.initialize()
            
            logger.info("⏰ Waiting for entry time...")
            
            while True:
                current_time = datetime.now().time()
                
                # Check market hours
                entry_time = dt_time(*map(int, ENTRY_TIME.split(':')))
                force_exit = dt_time(*map(int, FORCE_EXIT_TIME.split(':')))
                
                # Force exit before market close
                if current_time >= force_exit and self.position:
                    self.exit_position("Market closing")
                    break
                
                # Enter at specified time
                if not self.entry_done and current_time >= entry_time:
                    # Check retry limits
                    if self.entry_retries >= MAX_ENTRY_RETRIES:
                        logger.error(f"❌ [CORE] Max entry retries ({MAX_ENTRY_RETRIES}) reached. Stopping strategy.")
                        break
                    
                    # Check backoff timer
                    if time.time() < self.next_entry_attempt:
                        time.sleep(10)
                        continue

                    # 1. Check VIX Condition
                    if not self.check_vix_condition():
                        logger.info("⏳ [CORE] Waiting for VIX Condition (Below ST & Falling)...")
                        time.sleep(60) # Wait 1 min before next check
                        continue

                    atm_strike, _ = self.get_current_atm()
                    if atm_strike:
                        if self.enter_straddle(atm_strike):
                            self.entry_done = True
                        else:
                            self.entry_retries += 1
                            self.next_entry_attempt = time.time() + ENTRY_RETRY_BACKOFF
                            logger.warning(f"⚠️  [CORE] Entry failed. Retry {self.entry_retries}/{MAX_ENTRY_RETRIES} in {ENTRY_RETRY_BACKOFF}s")
                    else:
                        logger.error("❌ [UPSTOX] Failed to get ATM strike")
                        time.sleep(60)
                        continue
                
                # Monitor position
                if self.entry_done and self.position:
                    # Check adjustments
                    self.check_and_adjust()
                    
                    # Check exit conditions
                    if self.check_exit_conditions():
                        break
                
                time.sleep(PRICE_UPDATE_INTERVAL)
                
        except KeyboardInterrupt:
            logger.info("\n⚠️  Strategy stopped by user")
            if self.position:
                self.exit_position("User interrupt")
        except Exception as e:
            logger.error(f"❌ Strategy error: {e}")
            import traceback
            traceback.print_exc()
            if self.position:
                self.exit_position("Error occurred")
        finally:
            if self.upstox_streamer:
                try:
                    self.upstox_streamer.disconnect_all()
                except:
                    pass
            if self.kotak_broker:
                try:
                    self.kotak_broker.logout()
                except:
                    pass
            logger.info("👋 Strategy terminated")


if __name__ == "__main__":
    from lib.core.authentication import get_access_token
    token = get_access_token()
    if not token: sys.exit(1)
    
    # Run strategy
    strategy = ATMStraddleStrategy(token)
    strategy.run()


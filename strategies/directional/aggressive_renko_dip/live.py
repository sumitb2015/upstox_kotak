"""
Aggressive Renko Dip - Live Execution strategy.

Strategy Logic Summary:
-----------------------
1.  **Entry Conditions**:
    - **Bullish (SELL PE)**: 
     1.  **Entry Signal (Nifty Renko - Candle-Close Based)**:
    - Uses 1-minute candle close prices (not tick-level)
    - Waits for 2 consecutive same-color bricks (GREEN or RED).
    - RSI must align: Bullish (RSI > 50) or Bearish (RSI < 50).
    - Market regime filter: Max 40% reversals in last 20 bricks.

        - Brick Momentum: 1-6 bricks/minute (not too slow, not too fast).
        - Entry triggered on the closing of the 2nd brick.
    - **Bearish (SELL CE)**:
        - Nifty Renko (Brick 10) shows 2 consecutive RED bricks.
        - RSI < 50.
        - Market Regime: Trending (max 40% reversals in last 20 bricks).
        - Brick Momentum: 1-6 bricks/minute (not too slow, not too fast).
        - Entry triggered on the closing of the 2nd brick.

2.  **Pyramiding**:
    - Adds 1 lot if the trend continues for another 2 bricks (Configurable 'resumption_streak').
    - Maximum 3 pyramids allowed.

3.  **Exit Conditions**:
    - **Trend Reversal**: Nifty Renko shows bricks in opposite direction (requires 2x brick size for reversal).
    - **Option Reversal**: Option Renko (8% of Premium) shows 2 consecutive Green bricks (meaning option price is rising/reversing against our short).
    - **Time Exit**: 15:15 PM market close.

4.  **Stop Loss / TSL**:
    - **TSL**: Trailing Stop Loss calculated on the Option Renko.
    - Logic: Track the 'Best Low' of the option premium.
    - TSL Price = Best Low + (Option Brick Size * TSL Multiplier).
    - Multiplier tightens as we pyramid (1.0 -> 0.8 -> ... -> 0.5).

5.  **Strike Selection**:
    - ATM +/- Offset (Default 4 strikes OTM).
    - Dynamically selects based on 'expiry_type' (current/next week).

6.  **Whipsaw Protection**:
    - Market Regime Filter: Only trades in trending markets (< 40% brick reversals).
    - Brick Momentum Filter (Optional): Avoids too slow or too fast conditions.
    - Entry Time Filter: No trades before 09:20.
"""

import os
import sys
import threading
import logging
import time
from datetime import datetime, time as dt_time, timezone, timedelta
import pandas as pd
from typing import Optional, Dict, List, Any

# Adjust Paths
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from kotak_api.lib.broker import BrokerClient
from kotak_api.lib.order_manager import OrderManager
from kotak_api.lib.trading_utils import get_strike_token
from lib.api.historical import get_historical_data, get_intraday_data_v3
from lib.api.streaming import UpstoxStreamer
from lib.api.market_data import download_nse_market_data, get_option_chain_atm
from lib.api.market_quotes import get_multiple_ltp_quotes, get_ohlc_quote
from lib.utils.instrument_utils import get_future_instrument_key, get_option_instrument_key
from lib.utils.expiry_cache import get_expiry_for_strategy
from lib.utils.indicators import calculate_rsi

from strategies.directional.aggressive_renko_dip.core import AggressiveRenkoCore, RenkoCalculator
from strategies.directional.aggressive_renko_dip.config import CONFIG, validate_config

# Logger settings
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', force=True)
logger = logging.getLogger("AggressiveRenkoLive")

class AggressiveRenkoLive(AggressiveRenkoCore):
    """
    Live execution engine for the Aggressive Renko Dip strategy.
    Handles API connections, market data streaming, and order execution via Kotak API.
    """
    def __init__(self, access_token: str, config: dict):
        super().__init__(config)
        self.upstox_token = access_token
        self.nse_data = None
        self.nifty_token = "NSE_INDEX|Nifty 50"
        
        # Execution
        self.kotak_broker = BrokerClient()
        self.kotak_client = None
        self.order_mgr = None
        self.lock = threading.RLock() # CRITICAL: Re-entrant Lock to prevent deadlocks
        
        # Cache
        self.ltp_cache = {}
        self.last_sync_minute = -1
        self.last_nifty_brick_minute = -1  # Track last minute Nifty brick was updated
        self.last_option_brick_minute = -1 # Track last minute Option brick was updated
        self.is_warming_up = True
        
        # WebSocket Candle Cache
        self.ws_candles = {} # {token: {'close': price, 'timestamp': ts}}
        self.nifty_candles = [] # Buffer for accurate RSI indicator

    def initialize(self):
        """
        Validates config, connects to Broker/NSE, warms up indicators, and starts WebSocket.
        """
        try:
            validate_config(self.config)
        except ValueError as e:
            logger.error(f"❌ Configuration Error: {e}")
            return False

        self.log_box("AGGRESSIVE RENKO DIP - LIVE", [
            f"Config: Nifty Brick {self.config.get('nifty_brick_size')}",
            f"Expiry: {self.config.get('expiry_type')}",
            f"Lots:   {self.config.get('trading_lots')}"
        ], "🚀")
        
        # 1. NSE Data
        self.nse_data = download_nse_market_data()
        
        # 2. Kotak Auth
        self.kotak_client = self.kotak_broker.authenticate()
        self.kotak_broker.load_master_data()
        self.order_mgr = OrderManager(self.kotak_client, dry_run=self.config.get('dry_run', False))
        
        # 3. Load State or Warmup
        # Using config flag (Default: False)
        state_restored = False
        if self.config.get('restore_state', False):
             state_restored = self.load_state(self.config['state_file'])

        if state_restored:
            self.is_warming_up = False
            self.log(f"✅ [CORE] State loaded. Strategy is LIVE. (RSI: {self.rsi:.2f})")
        else:
            # 3a. Indicator Warmup (Mandatory Pattern)
            self.log("📊 [UPSTOX] Warming up RSI (fetching historical + intraday data)...")
            try:
                # Fetch ~2000 bars for RSI warmup (approx 3 days)
                hist = get_historical_data(self.upstox_token, self.nifty_token, "minute", 2000) or []
                intra = get_intraday_data_v3(self.upstox_token, self.nifty_token, "minute", 1) or []
                
                # Merge logic to ensure continuous stream
                candle_map = {c['timestamp']: c for c in hist}
                for c in intra: candle_map[c['timestamp']] = c
                
                merged = sorted(candle_map.values(), key=lambda x: x['timestamp'])
                self.nifty_candles = merged[-2000:] # Keep last 2000 for sliding window
                
                if self.nifty_candles:
                    df = pd.DataFrame(self.nifty_candles)
                    self.rsi = calculate_rsi(df, self.rsi_period)
                    self.log(f"✅ RSI Warmup Complete: {self.rsi:.2f} (Bars: {len(self.nifty_candles)})")
                else:
                    self.log("⚠️ No historical data found for RSI warmup. Starting at 50.")
            except Exception as e:
                self.log(f"⚠️ RSI Warmup Error: {e}")

            self.log("🚀 Initializing Renko from historical data...")
            try:
                # Use the merged candles from RSI warmup for Renko history
                if self.nifty_candles:
                    # 1. Initialize with first candle
                    start_price = float(self.nifty_candles[0]['close'])
                    self.nifty_renko.initialize(start_price)
                    self.log(f"🧱 Renko History Start @ {start_price}")
                    
                    # 2. Replay all candles to build bricks
                    # Temporarily suppress logs for replay to avoid spam
                    # We can do this by just calling update() without logging manually here
                    # The core update() logs at INFO level, so it might still spam. 
                    # Ideally we'd lower level, but let's just run it. 
                    # If it's too much, we can adjust core logging.
                    
                    self.log(f"🔄 Replaying {len(self.nifty_candles)} candles for Renko...")
                    bricks_formed = 0
                    for c in self.nifty_candles:
                        c_close = float(c['close'])
                        # Use candle timestamp
                        ts = c['timestamp']
                        if isinstance(ts, str):
                            try: ts = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                            except: pass
                        elif isinstance(ts, (int, float)):
                            ts = datetime.fromtimestamp(ts/1000, tz=timezone.utc)
                            
                        new = self.nifty_renko.update(c_close, ts)
                        bricks_formed += new
                        
                    self.ltp_cache[self.nifty_token] = float(self.nifty_candles[-1]['close'])
                    self.log(f"✅ Renko Replay Complete: {len(self.nifty_renko.bricks)} bricks formed.")
                    
                else:
                    # Fallback to LTP if no history
                    from lib.api.market_data import get_market_quote_for_instrument
                    quote = get_market_quote_for_instrument(self.upstox_token, self.nifty_token)
                    start_price = 0.0
                    if quote:
                        start_price = quote.get('last_price', 0.0)
                    
                    if start_price > 0:
                        self.nifty_renko.initialize(start_price)
                        self.ltp_cache[self.nifty_token] = start_price
                        self.log(f"🧱 Renko Started @ {start_price} (No History)")
                    else:
                        self.log("⚠️ Could not get current price for Renko initialization. Will wait for first tick.")
            except Exception as e:
                self.log(f"⚠️ Initialization error: {e}")
            
            self.is_warming_up = False
            logger.info(f"✅ Strategy is now LIVE. (RSI: {self.rsi:.2f})")
        
        # Also fetch latest candle for the ticker (so it's not 0.0 on startup)
        try:
            resp = get_ohlc_quote(self.upstox_token, self.nifty_token, interval="I1")
            if resp and resp.get('status') == 'success':
                data = resp.get('data', {}).get(self.nifty_token, {})
                prev = data.get('prev_ohlc')
                if prev:
                    self.ws_candles[self.nifty_token] = {
                        'close': float(prev.get('close', 0)),
                        'timestamp': prev.get('ts')
                    }
        except: pass
        
        # 4. WebSocket
        tokens = [self.nifty_token]
        if self.current_option_token:
            tokens.append(self.current_option_token)
            
        self.streamer = UpstoxStreamer(self.upstox_token)
        # Use mode="full" to get marketOHLC data for t-1 candles
        self.streamer.connect_market_data(tokens, mode="full", on_message=self.on_market_data)
        
        # Wait for connection
        logger.info("⏳ Waiting for WebSocket connection...")
        for _ in range(5):
            time.sleep(1)
            if self.streamer.market_data_connected:
                logger.info("✅ WebSocket connection confirmed")
                # Force subscribe to ensure keys are active (Robustness)
                self.streamer.subscribe_market_data(tokens, mode="full")
                break
        else:
             logger.warning("⚠️ WebSocket not confirmed within 5s")
        
        return True

    def calculate_total_pnl(self) -> float:
        """Calculates current P&L for short positions."""
        total_pnl = 0.0
        with self.lock:
            if self.total_qty > 0 and self.current_option_token:
                ltp = self.ltp_cache.get(self.current_option_token, 0.0)
                if ltp > 0:
                    # Short Position: Profit = (Entry - Current) * Qty
                    total_pnl = (self.avg_price - ltp) * self.total_qty
        return total_pnl

    def display_status(self):
        """Displays a clean real-time status ticker in the terminal."""
        now_str = datetime.now().strftime("%H:%M:%S")
        
        # 1. Fetch Nifty Data
        with self.lock:
            raw_nifty = self.ltp_cache.get(self.nifty_token, 0.0)
            nifty_ltp = float(raw_nifty.get('close', 0.0)) if isinstance(raw_nifty, dict) else float(raw_nifty)
            nifty_candle = self.ws_candles.get(self.nifty_token, {}).get('close', 0.0)
            
            # 2. Fetch Position / Option Data
            opt_ltp_str = "  --- "
            opt_candle_str = " --- "
            if self.current_option_token:
                raw_opt = self.ltp_cache.get(self.current_option_token, 0.0)
                opt_ltp = float(raw_opt.get('close', 0.0)) if isinstance(raw_opt, dict) else float(raw_opt)
                opt_candle = self.ws_candles.get(self.current_option_token, {}).get('close', 0.0)
                opt_ltp_str = f"{opt_ltp:6.2f}"
                opt_candle_str = f"{opt_candle:5.1f}"
                
            pnl_val = self.calculate_total_pnl()
            pnl_str = f"{pnl_val:7.2f}" if self.total_qty > 0 else "  ---  "
            rsi_str = f"{self.rsi:4.1f}"
            
            # [NEW] Show actual persistent Brick Index (not list count)
            brick_idx = 0
            if self.nifty_renko.bricks:
                brick_idx = self.nifty_renko.bricks[-1].index
        
        
        # Calculate Renko EMA for display
        renko_ema = None
        if len(self.nifty_renko.bricks) >= self.nifty_ema_period:
            from lib.utils.indicators import calculate_renko_ema
            try:
                brick_closes = [b.close for b in self.nifty_renko.bricks]
                renko_ema = calculate_renko_ema(brick_closes, self.nifty_ema_period)
            except Exception as e: 
                # print(f"EMA Error: {e}") # Optional debug
                pass
        
        ema_str = f"{renko_ema:.2f}" if renko_ema else "---"

        # Build main status prefix (Up to PnL)
        dry_run_badge = "[DRY RUN] " if self.config.get('dry_run') else ""
        status_line = (
            f"\r{dry_run_badge}{now_str} | "
            f"NIFTY: {nifty_ltp:8.2f} (C:{nifty_candle:7.1f}) | "
            f"OPT: {opt_ltp_str} (C:{opt_candle_str}) | "
            f"RSI: {rsi_str} | B:{brick_idx:4} | "
            f"EMA: {ema_str} | "
            f"PnL: {pnl_str} | [{self.entry_state}]"
        )
        
        # Add TSL/Avg price info if active
        details = ""
        with self.lock:
            if self.active_positions and self.total_qty > 0:
                tsl = 0
                opt_brick_size = 0
                if self.option_renko:
                    mult = self.get_tsl_multiplier()
                    tsl = self.best_option_low + (self.option_renko.brick_size * mult)
                    opt_brick_size = self.option_renko.brick_size
                
                symbol = "N/A"
                for p_type, token in self.active_positions.items():
                    symbol = self.active_symbols.get(p_type, "Unknown")
                    break
                    
                details = f" | {symbol} | Qty:{self.total_qty} | Avg:{self.avg_price:.1f} | OptBrick:{opt_brick_size:.1f} | TSL:{tsl:5.1f}"
            else:
                details = " | [WAITING]"

        # Calculate points gained for display
        pg_str = ""
        with self.lock:
             if self.avg_price > 0 and self.current_option_token:
                curr = self.ltp_cache.get(self.current_option_token, 0)
                if isinstance(curr, dict): curr = curr.get('close', 0)
                if float(curr) > 0:
                    pts = self.avg_price - float(curr)
                    pg_str = f" | Pts:{pts:.1f}"

        import sys
        sys.stdout.write(status_line + details.ljust(50) + pg_str)
        sys.stdout.flush()

    def log(self, message: str):
        """Prints a log message without disturbing the ticker."""
        print("\n" + message)
        logger.info(message)

    def on_market_data(self, data):
        """Standardized callback for WebSocket messages."""
        inst_key = data.get('instrument_key')
        ltp = data.get('ltp')
        ohlc_1m = data.get('ohlc_1m')
        
        # 1. Update Candle Cache & Process Renko (Instant)
        if inst_key and ohlc_1m:
            self.ws_candles[inst_key] = ohlc_1m
            # Finalized candle close triggers Renko brick check immediately
            # Passing FULL DICT as price for internal buffer handling
            self.process_tick(inst_key, ohlc_1m, datetime.now(), is_candle_close=True)
            
        # 2. Update LTP cache for ticker and non-candle logic
        if inst_key and ltp is not None:
             self.process_tick(inst_key, ltp)
             return

        # Fallback: Check if it's the raw format (sometimes 'feeds' wrapper exists)
        if 'feeds' in data:
            for key, feed in data['feeds'].items():
                ltp_val = feed.get('ltpc', {}).get('ltp')
                if ltp_val: 
                    self.process_tick(key, ltp_val)
                    return
        
        # Debug if we didn't process
        # logger.warning(f"⚠️ Unprocessed WS Data: {data.keys()}")

    def get_tsl_multiplier(self) -> float:
        """
        Calculates TSL multiplier based on pyramid count.
        Starts at 'tsl_brick_count' (e.g. 3.0), reduces by 0.2 per pyramid, floor at 1.0.
        Also applies dynamic tightening if profit exceeds threshold.
        """
        # 1. Base Multiplier (Start with configured brick count)
        base_bricks = self.config.get('tsl_brick_count', 2.0)
        base_mult = base_bricks - (self.pyramid_count * 0.2)
        final_mult = max(1.0, base_mult)
        
        # 2. Dynamic Tightening (Aggressive Trail)
        if self.config.get('dynamic_tightening', False):
            try:
                # Check current profit
                if self.avg_price > 0 and self.current_option_token and self.option_renko:
                    curr = self.ltp_cache.get(self.current_option_token, 0)
                    if isinstance(curr, dict): curr = curr.get('close', 0)
                    curr = float(curr)
                    
                    if curr > 0:
                        # Short Option: Profit = Avg - Current
                        points_gained = self.avg_price - curr
                        bricks_gained = points_gained / self.option_renko.brick_size
                        
                        tighten_after = self.config.get('tighten_after_bricks', 4)
                        if bricks_gained >= tighten_after:
                            tightened_mult = self.config.get('tightened_multiplier', 1.5)
                            if tightened_mult < final_mult:
                                final_mult = tightened_mult
                                # Optional: Log once to avoid spam (can rely on Status TSL display)
            except Exception as e:
                pass

        return final_mult

    def log_box(self, title: str, content_lines: list, emoji: str = "ℹ️"):
        """Prints a formatted box in the terminal, respecting the ticker."""
        self.log("-" * 60)
        self.log(f"{emoji} {title}")
        self.log("-" * 60)
        for line in content_lines:
            self.log(f"   {line}")
        self.log("-" * 60)

    def get_latest_minute_close(self, token: str) -> float:
        """Fetch the close price of the latest completed 1-minute candle from WebSocket cache."""
        try:
            # Retrieve from WS cache (No REST calls)
            with self.lock:
                candle = self.ws_candles.get(token)
            
            if candle and 'close' in candle:
                close_price = float(candle['close'])
                ts_ms = candle.get('timestamp')
                
                if ts_ms:
                    # Convert ms to datetime
                    candle_time = datetime.fromtimestamp(int(ts_ms) / 1000.0, tz=timezone.utc)
                    now = datetime.now(candle_time.tzinfo) if candle_time.tzinfo else datetime.now()
                    
                    # Expected: Previous minute (t-1)
                    expected_minute = now.replace(second=0, microsecond=0) - timedelta(minutes=1)
                    candle_minute = candle_time.replace(second=0, microsecond=0)
                    
                    if candle_minute == expected_minute:
                        logger.debug(f"✅ [UPSTOX] Latest WS candle (t-1) received for {token}: {close_price:.2f}")
                        return close_price
                    else:
                        logger.debug(f"⚠️ [UPSTOX] WS Candle stale for {token}")
                else:
                    return close_price
        except Exception as e:
            logger.warning(f"⚠️ [UPSTOX] Error reading WS candle for {token}: {e}")
        return 0.0

    def process_tick(self, instrument_key: str, price: float, timestamp: Optional[datetime] = None, is_candle_close: bool = False):
        """
        Core event loop triggered by every price update.
        Protected by lock to prevent concurrent state modification.
        """
        with self.lock:
            if timestamp is None:
                timestamp = datetime.now()
                
            # Robust Price Handling: Extract float for caching and Renko
            if isinstance(price, dict):
                price_val = float(price.get('close', 0.0))
            else:
                price_val = float(price)

            self.ltp_cache[instrument_key] = price_val
            
            now_min = timestamp.minute
            
            # 1. Update Indicators & Nifty Renko (Candle-Close Based)
            if instrument_key == self.nifty_token:
                # Update indicators on new candle
                if is_candle_close and isinstance(price, dict):
                     self.update_indicators(price) 
                
                if is_candle_close or now_min != self.last_nifty_brick_minute:
                    candle_close = price_val if is_candle_close else self.get_latest_minute_close(self.nifty_token)
                    
                    if candle_close > 0:
                        new_bricks = self.nifty_renko.update(candle_close, timestamp)
                        if new_bricks > 0:
                            self.log(f"🧱 [CORE] New Nifty Bricks: +{new_bricks} (Total: {len(self.nifty_renko.bricks)})")
                            self.on_signal_brick(timestamp)
                            self.save_state(self.config['state_file'])
                        self.last_nifty_brick_minute = now_min
            
            # 2. Update Option Renko & TSL
            elif instrument_key == self.current_option_token and self.option_renko:
                if self.config.get('tsl_type', 'fluid') == 'fluid':
                    if price_val < self.best_option_low:
                        self.best_option_low = price_val
                        self.save_state(self.config['state_file'])
                
                # 2.1 Hard Price TSL Check (Immediate or Candle-based)
                mult = self.get_tsl_multiplier()
                tsl_price = self.best_option_low + (self.option_renko.brick_size * mult)
                
                # Check for instant tick-based exit
                if not self.config.get('wait_for_candle_close', False):
                    if price_val >= tsl_price:
                        self.log(f"🛡️ [CORE] HARD TSL TRIGGERED (INSTANT): Price {price_val:.2f} >= TSL {tsl_price:.2f}")
                        for p_type, token in self.active_positions.items():
                            if token == instrument_key:
                                self.execute_exit(p_type, "Hard TSL Hit", timestamp)
                                break
                        return
                
                if is_candle_close or now_min != self.last_option_brick_minute:
                    opt_candle_close = price_val if is_candle_close else self.get_latest_minute_close(self.current_option_token)
                    if opt_candle_close > 0:
                        # Check for candle-based TSL exit
                        if self.config.get('wait_for_candle_close', False):
                            if opt_candle_close >= tsl_price:
                                self.log(f"🛡️ [CORE] HARD TSL TRIGGERED (CANDLE): Close {opt_candle_close:.2f} >= TSL {tsl_price:.2f}")
                                for p_type, token in self.active_positions.items():
                                    if token == instrument_key:
                                        self.execute_exit(p_type, "Hard TSL Hit (Candle)", timestamp)
                                        break
                                return

                        new_opt_bricks = self.option_renko.update(opt_candle_close, timestamp)
                        if new_opt_bricks > 0:
                            if self.config.get('tsl_type') == 'staircase':
                                last_brick = self.option_renko.bricks[-1]
                                if last_brick.color == 'RED':
                                    self.best_option_low = last_brick.close
                                    self.save_state(self.config['state_file'])
                                    # LOG THE TRAILING ACTION
                                    new_tsl = self.best_option_low + (self.option_renko.brick_size * self.get_tsl_multiplier())
                                    self.log(f"📉 [CORE] TSL Trailed Down: Low {self.best_option_low:.2f} | New TSL {new_tsl:.2f}")

                            # Check for TSL trigger
                            tsl_brick_count = self.config.get('tsl_brick_count', 2)
                            if len(self.option_renko.bricks) >= tsl_brick_count:
                                last_n = self.option_renko.bricks[-tsl_brick_count:]
                                if all(b.color == 'GREEN' for b in last_n):
                                    self.log(f"🛡️ [CORE] TSL TRIGGERED: {tsl_brick_count} GREEN Option bricks (Premium Rising)")
                                    for p_type, token in self.active_positions.items():
                                        if token == instrument_key:
                                            self.execute_exit(p_type, "TSL Triggered", timestamp)
                                            break
                                    return
                            
                            # Check for Profit Target Exit
                            profit_target = self.config.get('profit_target_bricks', 5)
                            if profit_target > 0 and self.option_renko and self.avg_price > 0:
                                # Calculate captured points
                                current_brick_price = self.option_renko.bricks[-1].close
                                points_gained = self.avg_price - current_brick_price
                                bricks_gained = points_gained / self.option_renko.brick_size
                                
                                if bricks_gained >= profit_target:
                                    self.log(f"🏆 [CORE] PROFIT TARGET REACHED: {bricks_gained:.1f} Bricks >= {profit_target} (Points: {points_gained:.1f})")
                                    for p_type, token in self.active_positions.items():
                                        if token == instrument_key:
                                            self.execute_exit(p_type, "Profit Target Hit", timestamp)
                                            break
                                    return

                            self.on_option_brick(timestamp)
                            self.save_state(self.config['state_file'])
                        self.last_option_brick_minute = now_min

    def update_indicators(self, candle: Optional[dict] = None):
        """Update indicators using the local nifty_candles buffer."""
        try:
            if candle:
                ts = candle['timestamp']
                exists = any(c['timestamp'] == ts for c in self.nifty_candles)
                if not exists:
                    self.nifty_candles.append(candle)
                
                if len(self.nifty_candles) > 2000:
                    self.nifty_candles = self.nifty_candles[-2000:]

            if len(self.nifty_candles) > self.rsi_period:
                df = pd.DataFrame(self.nifty_candles)
                self.rsi = calculate_rsi(df, self.rsi_period)
                self.save_state(self.config['state_file'])
        except Exception as e:
            logger.error(f"  ⚠️ [CORE] RSI Update Failed: {e}")

    def execute_entry(self, option_type: str, timestamp: datetime, is_pyramid: bool = False):
        if is_pyramid and not self.current_option_token:
            self.log("❌ Pyramid called but no active position found. Skipping.")
            return

        self.log(f"🚀 SIGNAL: Executing {option_type} {'Pyramid' if is_pyramid else 'Initial'} Entry")
        
        active_token = self.current_option_token
        active_symbol = self.active_symbols.get(option_type)
        
        if not is_pyramid:
            # 1. Selection for NEW position
            nifty_ltp = self.ltp_cache.get(self.nifty_token, 0)
            if nifty_ltp == 0:
                # Fallback to candle close if LTP hasn't arrived yet
                n_cndl = self.ws_candles.get(self.nifty_token, {}).get('close', 0)
                nifty_ltp = n_cndl
                
            if nifty_ltp == 0:
                quotes = get_multiple_ltp_quotes(self.upstox_token, [self.nifty_token])
                nifty_ltp = quotes.get('data', {}).get(self.nifty_token, {}).get('last_price', 0)

            expiry = str(get_expiry_for_strategy(self.upstox_token, self.config.get('expiry_type', 'current_week'), "NIFTY"))
            chain = get_option_chain_atm(self.upstox_token, self.nifty_token, expiry, strikes_above=5, strikes_below=5)
            
            strikes = sorted(chain['strike_price'].unique())
            atm_strike = min(strikes, key=lambda x: abs(x - nifty_ltp))
            
            offset = abs(self.config.get('strike_offset', 0))
            idx = strikes.index(atm_strike)
            offset_idx = idx + offset if option_type == "CE" else idx - offset
            
            # Safe index access
            if offset_idx < 0: offset_idx = 0
            if offset_idx >= len(strikes): offset_idx = len(strikes) - 1
            
            target_strike = int(strikes[offset_idx])
            
            expiry_dt = datetime.strptime(expiry, "%Y-%m-%d")
            k_token, opt_symbol = get_strike_token(self.kotak_broker, target_strike, option_type, expiry_dt)
            
            # MANDATORY: Get key with explicit expiry safety
            opt_key = get_option_instrument_key("NIFTY", target_strike, option_type, self.nse_data, expiry)
            
            # Fetch LTP for key manually to ensure accuracy
            quotes = get_multiple_ltp_quotes(self.upstox_token, [opt_key])
            opt_price = quotes.get('data', {}).get(opt_key, {}).get('last_price', 0)
        else:
            # 1. Use EXISTING info for pyramid
            opt_key = self.current_option_token
            opt_symbol = self.active_symbols.get(option_type)
            with self.lock:
                opt_price = self.ltp_cache.get(opt_key, 0)
            
        if not opt_symbol or not opt_key:
            logger.error(f"❌ Selection failed. Symbol: {opt_symbol}, Key: {opt_key}")
            return
            
        # 2. Place Order
        lots = self.config['trading_lots']
        from lib.utils.instrument_utils import get_lot_size
        lot_size = get_lot_size(opt_key, self.nse_data)
        
        self.log(f"📤 Sending Entry Order to [KOTAK] for {opt_symbol}...")
        order_id = self.order_mgr.place_order(
            symbol=opt_symbol, 
            qty=int(lots * lot_size), 
            transaction_type="S", 
            tag=f"AggRenko_{'Pyramid' if is_pyramid else 'Entry'}",
            product=self.config.get('product_type', 'MIS')
        )
        
        if order_id:
            # ✅ Get actual execution price (Wait 1s for exchange processing)
            time.sleep(1)
            exec_price = self.order_mgr.get_execution_price(order_id)
            if not exec_price or exec_price <= 0:
                exec_price = opt_price # Fallback
                self.log(f"⚠️ [KOTAK] Could not get actual fill price for {order_id}. Using LTP {exec_price}")
            
            self.log_box("ENTRY SIGNAL EXECUTED", [
                f"Symbol: {opt_symbol}",
                f"Fill:   ₹{exec_price:.2f}",
                f"Qty:    {int(lots * lot_size)}",
                f"Tag:    AggRenko_{'Pyramid' if is_pyramid else 'Entry'}"
            ], "🎯")
            
            # 3. Update State (Thread Safe)
            with self.lock:
                curr_qty = int(lots * lot_size)
                if self.total_qty == 0:
                    self.avg_price = exec_price
                    self.total_qty = curr_qty
                else:
                    total_val = (self.avg_price * self.total_qty) + (exec_price * curr_qty)
                    self.total_qty += curr_qty
                    self.avg_price = total_val / self.total_qty
                
                if not is_pyramid:
                    self.current_option_token = opt_key
                    self.active_positions[option_type] = opt_key
                    self.active_symbols[option_type] = opt_symbol
                    # Initialize Option Renko
                    b_size = self.calculate_option_brick_size(exec_price)
                    self.option_renko = RenkoCalculator(
                        brick_size=b_size,
                        reversal_brick_count=self.config.get('tsl_brick_count', 2)
                    )
                    self.option_renko.initialize(exec_price)
                    self.best_option_low = exec_price
                    # Subscribe streamer
                    self.streamer.subscribe_market_data([opt_key], mode="full")
                
                self.save_state(self.config['state_file'])

    def execute_exit(self, option_type: str, reason: str, timestamp: Optional[datetime] = None):
        opt_key = self.active_positions.get(option_type)
        if not opt_key: return
        
        opt_symbol = self.active_symbols.get(option_type, "Unknown")
        
        if opt_symbol:
            exit_qty = int(self.total_qty)
            if exit_qty <= 0:
                self.log(f"⚠️ execute_exit called but total_qty is {exit_qty}. Skipping.")
                return

            self.log(f"📤 Sending Exit Order to [KOTAK] for {opt_symbol}...")
            order_id = self.order_mgr.place_order(
                symbol=opt_symbol, 
                qty=exit_qty, 
                transaction_type="B", 
                tag=f"AggRenko_Exit_{reason}",
                product=self.config.get('product_type', 'MIS')
            )
            if order_id:
                # ✅ ROBUST EXIT: Wait for confirmation before clearing state
                time.sleep(1)
                
                # Fetch actual fill price
                exec_price = self.order_mgr.get_execution_price(order_id)
                if not exec_price or exec_price <= 0:
                    exec_price = self.ltp_cache.get(opt_key, 0.0) # Fallback to LTP
                    self.log(f"⚠️ [KOTAK] Could not get actual fill price for {order_id}. Using LTP {exec_price}")

                self.log_box("EXIT SIGNAL EXECUTED", [
                    f"Symbol: {opt_symbol}",
                    f"Reason: {reason}",
                    f"Fill:   ₹{exec_price:.2f}",
                    f"Qty:    {exit_qty}"
                ], "🚨")
                
                with self.lock:
                    self.active_positions.pop(option_type, None)
                    self.active_symbols.pop(option_type, None)
                    self.current_option_token = None
                    self.option_renko = None
                    self.avg_price = 0.0
                    self.total_qty = 0
                    self.pyramid_count = 0
                    self.bricks_since_last_lot = 0
                    self.entry_state = "WAITING"
                    
                    # [NEW] Record exit time (brick index) to prevent immediate re-entry
                    if self.nifty_renko.bricks:
                        self.last_exit_brick_index = self.nifty_renko.bricks[-1].index
                        self.log(f"🛑 [CORE] Exit Recorded @ Nifty Brick #{self.last_exit_brick_index}. Cooldown active.")
                    
                    # Unsubscribe
                    if self.streamer:
                        self.streamer.unsubscribe_market_data([opt_key])
                    
                    self.save_state(self.config['state_file'])

    def run(self):
        if not self.initialize(): return
        self.log("📡 Strategy Running... Press Ctrl+C to stop.")
        try:
            while True:
                # 0. Global Kill Switch Check
                if os.path.exists("c:/algo/upstox/.STOP_TRADING"):
                    self.log("🛑 Global Kill Switch Detected (.STOP_TRADING). Stopping Strategy.")
                    # Clear state to prevent further actions
                    with self.lock:
                        self.active_positions.clear()
                        self.active_symbols.clear()
                        self.total_qty = 0
                        self.entry_state = "STOPPED_BY_PORTFOLIO_MANAGER"
                    break

                current_dt = datetime.now()
                
                # Check for market close time
                exit_h, exit_m = map(int, self.config['exit_all_time'].split(':'))
                if current_dt.time() >= dt_time(exit_h, exit_m):
                    self.log(f"⏰ Market Close Time Reached ({self.config['exit_all_time']})")
                    # Force exit all positions
                    with self.lock:
                        tokens_to_exit = list(self.active_positions.keys())
                    
                    if not tokens_to_exit:
                        self.log("🛑 No active positions. Exiting strategy.")
                        break
                        
                    for p_type in tokens_to_exit:
                        self.execute_exit(p_type, "Market Close", current_dt)
                    
                    # Verify they are gone before breaking
                    with self.lock:
                        if not self.active_positions:
                            self.log("✅ All positions closed. Exiting strategy.")
                            break
                        else:
                            self.log(f"⚠️ {len(self.active_positions)} positions remaining. Retrying next tick...")
                
                self.display_status()
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("\n🛑 [CORE] Interrupted by user. Exiting...")
            # Emergency Square-off
            with self.lock:
                for p_type in list(self.active_positions.keys()):
                    self.execute_exit(p_type, "User Interrupt", datetime.now())
            
            if hasattr(self, 'streamer'):
                self.streamer.disconnect_all()
            
            import os
            self.log("👋 [CORE] Strategy stopped safely.")
            os._exit(0) # Force exit all threads

if __name__ == "__main__":
    from lib.core.authentication import get_access_token
    token = get_access_token()
    strat = AggressiveRenkoLive(token, CONFIG)
    strat.run()

"""
Futures VWAP EMA Strategy - Live Trading Implementation

[STRATEGY LOGIC]
1. CONCEPT:
   - Trend Following using Futures, VWAP, and EMA(20).
   - Follows the trend of the Underlying Futures to sell OTM Options.

2. TIMEFRAME:
   - Futures Data: 1-Minute Candle Data (Resampled to Configured Interval, Default 1m).
   - VWAP: Calculated on 1-Minute Data (Intraday Reset).
   - EMA(20): Calculated on Configured Interval.

3. ENTRY (Directional Short Option Selling):
   - CE Entry (Bearish View):
     - Futures Price < VWAP.
     - Futures Price < EMA(20) (Crossover or Continuation).
     - Filter: PCR < 0.9 (if enabled).
     - Selection: Sell CE (ATM + 150).
   - PE Entry (Bullish View):
     - Futures Price > VWAP.
     - Futures Price > EMA(20) (Crossover or Continuation).
     - Filter: PCR > 1.1 (if enabled).
     - Selection: Sell PE (ATM - 150).

4. EXIT Conditions:
   - VWAP Reversal:
     - Exit CE if Futures > VWAP.
     - Exit PE if Futures < VWAP.
   - Dynamic Trailing Stop Loss (TSL):
     - Base TSL: 20% from Lowest Premium seen.
     - TSL Tightening: Reduces by 5% for each pyramid level (20% -> 15% -> 10%).
   - Time Exit: Hard stop at 15:15.

5. PYRAMIDING:
   - Condition: Add 1 lot if position profit >= 10%.
   - Limit: Max 2 levels.
"""

import sys
import os
import logging
import pandas as pd
import time
from datetime import datetime, timedelta
from typing import Optional

# Add parent directory to path
# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

# Import core strategy logic
from strategies.directional.futures_vwap_ema.strategy_core import FuturesVWAPEMACore, Position
from strategies.directional.futures_vwap_ema.config import CONFIG

# Import helper functions (avoiding code duplication)
from lib.api.historical import get_intraday_data_v3, get_historical_data_v3
from lib.utils.tick_aggregator import TickAggregator  # New
from lib.utils.vwap_calculator import VWAPCalculator  # NEW: Tick-level VWAP
from lib.api.streaming import UpstoxStreamer
from lib.api.order_management import place_order
from lib.api.market_quotes import get_ltp_quote
from lib.utils.instrument_utils import get_future_instrument_key, get_option_instrument_key
from lib.utils.expiry_cache import get_expiry_for_strategy
from lib.api.market_data import download_nse_market_data, get_option_chain_atm, get_market_quote_for_instrument
from lib.oi_analysis.cumulative_oi_analysis import CumulativeOIAnalyzer

# Kotak Neo API Imports
from kotak_api.lib.broker import BrokerClient
from kotak_api.lib.order_manager import OrderManager
from kotak_api.lib.trading_utils import get_strike_token

# Logger setup
logger = logging.getLogger("FuturesVWAPEMALive")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class FuturesVWAPEMALive(FuturesVWAPEMACore):
    """Live trading implementation of Futures VWAP EMA Strategy."""
    
    def __init__(self, access_token: str, config: dict):
        # Initialize core logic
        super().__init__(config)
        
        self.access_token = access_token
        self.nse_data = None
        self.futures_instrument_key = None
        self.streamer = None
        
        # Tracking
        self.last_candle_check = None
        self.candle_check_interval = config['candle_interval_minutes'] * 60  # Convert to seconds
        
        # Aggregator
        self.futures_aggregator = TickAggregator(config['candle_interval_minutes'])
        
        # ATM tracking
        self.current_atm = None
        self.pnl_multiplier = 50.0 # Default
        self.strike_step = 50 # Default
        
        # OI Analyzer
        self.oi_analyzer = CumulativeOIAnalyzer(access_token)
        self.last_pcr = 0.0
        self.last_change_pcr = 0.0
        
        # Historical Data for Warmup
        self.historical_data = None
        
        # Tick-level VWAP Calculator (WebSocket-based, zero API calls)
        self.vwap_calculator = VWAPCalculator()
        
        # Kotak Execution components
        self.kotak_broker = BrokerClient()
        self.kotak_client = None
        self.order_mgr = None
        
        # Fixed OI strikes for the day
        self.fixed_oi_strikes = []
        
    def initialize(self):
        """Initialize connections and strategy state."""
        # Download NSE Data (silent)
        self.nse_data = download_nse_market_data()
        if self.nse_data is None or self.nse_data.empty:
            print("❌ Failed to download NSE data")
            return False
        
        # Get Nifty Futures Instrument Key (silent)
        self.futures_instrument_key = get_future_instrument_key(
            underlying_symbol=self.config['underlying'],
            nse_data=self.nse_data
        )
        if not self.futures_instrument_key:
            print("❌ Failed to find Nifty Futures instrument")
            return False
            
        # Get lot size/multiplier and strike step from instrument metadata
        try:
            underlying_info = self.nse_data[self.nse_data['name'] == self.config['underlying']].iloc[0]
            self.pnl_multiplier = float(underlying_info.get('lot_size', 50.0))
            
            # Better, fetch from one of the options
            expiry = get_expiry_for_strategy(self.access_token, self.config.get('expiry_type', 'current_week'), self.config['underlying'])
            
            # Robust Index Key resolution
            index_key = "NSE_INDEX|Nifty 50" if self.config['underlying'] == "NIFTY" else self.futures_instrument_key.replace("NSE_FO", "NSE_INDEX")
            
            chain = get_option_chain_atm(self.access_token, index_key, expiry, strikes_above=2, strikes_below=2)
            if not chain.empty and len(chain['strike_price'].unique()) >= 2:
                strikes = sorted(chain['strike_price'].unique())
                self.strike_step = int(strikes[1] - strikes[0])
            
            self.log(f"📋 Multiplier: {self.pnl_multiplier}, Strike Step: {self.strike_step}")
        except Exception as e:
            self.log(f"⚠️ Error getting instrument metadata: {e}")
        
        # Initialize WebSocket (silent)
        if self.config.get('use_websockets', True):
            self.streamer = UpstoxStreamer(self.access_token)
            self.streamer.add_market_callback(self.on_market_data)
            self.streamer.connect_market_data(
                instrument_keys=[self.futures_instrument_key],
                mode='full'
            )
            
            # Wait for connection
            self.log("⏳ Waiting for WebSocket connection...")
            for _ in range(5):
                time.sleep(1)
                if self.streamer.market_data_connected:
                    self.log("✅ WebSocket connection confirmed")
                    break
            else:
                 self.log("⚠️ WebSocket not confirmed within 5s")
            
        # Initialize Kotak for Execution
        self.log("🔗 Connecting to Kotak Neo for execution...")
        self.kotak_client = self.kotak_broker.authenticate()
        if self.kotak_client:
            self.order_mgr = OrderManager(self.kotak_client, dry_run=self.config.get('dry_run', False))
            self.log("📂 Loading Kotak Master Data...")
            self.kotak_broker.load_master_data()
            self.log("✅ Kotak Neo authenticated and Master Data loaded")
        else:
            self.log("❌ Failed to authenticate with Kotak Neo")
            return False
            
        # 🔗 Determine Fixed OI strikes for the entire session
        self.log("🎯 Initializing fixed OI strikes for the session...")
        try:
            quote = get_market_quote_for_instrument(self.access_token, self.oi_analyzer.underlying_key)
            if quote:
                initial_spot = quote.get('last_price', 0)
                if initial_spot > 0:
                    atm = self.get_atm_strike(initial_spot)
                    radius = self.config.get('oi_strikes_radius', 4)
                    self.fixed_oi_strikes = [atm + (i * self.strike_step) for i in range(-radius, radius + 1)]
                    self.log(f"🎯 Strikes Fixed Around {initial_spot}: {self.fixed_oi_strikes}")
                else:
                    self.log("⚠️ Could not get valid spot price, strikes will be calculated dynamically.")
            else:
                self.log("⚠️ Quote failed, strikes will be calculated dynamically.")
        except Exception as e:
            self.log(f"⚠️ Error initializing fixed strikes: {e}")
        
        # Pre-load historical data for indicator warmup
        self.log(f"📉 Pre-loading historical data for indicators (5 days)...")
        
        # 1. Fetch History (Last 5 days)
        to_date = datetime.now()
        from_date = to_date - timedelta(days=5)
        
        hist_candles = get_historical_data_v3(
            access_token=self.access_token,
            instrument_key=self.futures_instrument_key,
            interval_unit='minute',
            interval_value=1,
            from_date=from_date.strftime('%Y-%m-%d'),
            to_date=to_date.strftime('%Y-%m-%d')
        )
        
        # 2. Fetch Intraday (Today)
        intra_candles = get_intraday_data_v3(
            self.access_token,
            self.futures_instrument_key,
            'minute',
            1
        )
        
        # 3. Merge
        hist_df = pd.DataFrame(hist_candles) if hist_candles else pd.DataFrame()
        intra_df = pd.DataFrame(intra_candles) if intra_candles else pd.DataFrame()
        
        full_df = pd.DataFrame()
        if not hist_df.empty:
            full_df = hist_df
        
        if not intra_df.empty:
            if full_df.empty:
                full_df = intra_df
            else:
                full_df = pd.concat([full_df, intra_df]).drop_duplicates(subset=['timestamp']).sort_values('timestamp')
                
        if not full_df.empty:
            if 'timestamp' in full_df.columns:
                 full_df['timestamp'] = pd.to_datetime(full_df['timestamp'])
                 
            self.historical_data = full_df
            self.log(f"✅ Loaded {len(self.historical_data)} merged candles for warmup")
            
            # Seed Aggregator
            self.futures_aggregator.update_historical(self.futures_instrument_key, self.historical_data)
        else:
            self.log("⚠️ Failed to load historical data - indicators will need warmup time")
            self.historical_data = pd.DataFrame()
        
        print("✅ Ready\n")
        return True
    
    def log(self, message: str):
        """Log message with timestamp."""
        if self.config.get('verbose', True):
            logger.info(message)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
    
    # ========== DATA FETCHING ==========
    
    def fetch_futures_data(self) -> Optional[pd.DataFrame]:
        """
        Fetch intraday futures candle data (1-minute resolution).
        
        We fetch 1-minute data to calculate accurate VWAP, then resample 
        for the strategy timeframe (e.g. 3-min) for EMA and signals.
        
        Returns:
            DataFrame with 1-minute candles
        """
        try:
            # Fetch 1-minute data for accurate VWAP
            candles = get_intraday_data_v3(
                access_token=self.access_token,
                instrument_key=self.futures_instrument_key,
                interval_unit='minute',
                interval_value=1
            )
            
            if not candles:
                self.log("⚠️ No candle data received")
                return None
            
            # Convert to DataFrame
            df_intraday = pd.DataFrame(candles)
            
            # Convert timestamp to datetime
            if 'timestamp' in df_intraday.columns:
                df_intraday['timestamp'] = pd.to_datetime(df_intraday['timestamp'])
                
                # Filter for today's data only (Intraday VWAP)
                # Note: For VWAP we usually want only today, but for EMA we want history
                # Strategy logic separates calculation:
                # 1. VWAP -> Needs 1-min data (passed directly)
                # 2. EMA -> Needs history
                
                # We will return the MERGED dataframe (History + Today)
                # But we need to handle duplicates
                
                if self.historical_data is not None and not self.historical_data.empty:
                    # Combine history + intraday
                    # Exclude today from history to avoid overlap if history fetched includes today
                    today_date = datetime.now().date()
                    history_clean = self.historical_data[self.historical_data['timestamp'].dt.date < today_date]
                    
                    # Merge
                    df_merged = pd.concat([history_clean, df_intraday])
                    df_merged = df_merged.drop_duplicates(subset=['timestamp']).sort_values('timestamp')
                    return df_merged
            
            return df_intraday.sort_values('timestamp')
            
        except Exception as e:
            self.log(f"❌ Error fetching futures data: {e}")
            return None
    
    def resample_candles(self, df_1min: pd.DataFrame, timeframe_min: int) -> pd.DataFrame:
        """Resample 1-minute candles to target timeframe."""
        if df_1min.empty:
            return df_1min
            
        # Set index to timestamp for resampling
        df = df_1min.set_index('timestamp')
        
        # Define aggregation logic
        agg_dict = {
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }
        
        # Resample
        # Origin 'start_day' ensures 09:15:00 aligns correctly (9:15-9:18, etc.)
        resampled = df.resample(f'{timeframe_min}min', origin='start_day').agg(agg_dict).dropna()
        
        # Reset index
        resampled = resampled.reset_index()
        return resampled

    def update_indicators(self, df_full: pd.DataFrame):
        """
        Update indicators using mixed timeframes.
        
        VWAP -> Calculated from tick-level WebSocket data (zero API calls!)
        EMA  -> Calculated from Resampled df_full (User timeframe, includes HISTORY)
        """
        if df_full is None or df_full.empty:
            return


        # 1. Calculate VWAP from tick-level data (WebSocket-based, zero API calls!)
        self.current_vwap = self.vwap_calculator.get_vwap(self.futures_instrument_key)
        
        
        # 2. Resample to strategy timeframe (e.g. 3 min) - Use FULL data for EMA
        strategy_tf = self.config['candle_interval_minutes']
        df_resampled = self.resample_candles(df_full, strategy_tf)
        
        # 3. Calculate EMA on resampled data using library function
        from lib.utils.indicators import calculate_ema_series
        ema_series = calculate_ema_series(df_resampled, self.config['ema_period'])
        self.current_ema = ema_series.iloc[-1]
        
        
        # 4. Update Previous Values for Crossover Check
        if not df_resampled.empty:
            # Update futures price from candles as fallback (WebSocket will override between loops)
            # This ensures the price is never stale if WebSocket fails
            self.futures_price = df_resampled['close'].iloc[-1]
            
            if len(df_resampled) >= 2:
                self.prev_close = df_resampled['close'].iloc[-2]
                self.prev_ema = ema_series.iloc[-2]
            else:
                self.prev_close = None
                self.prev_ema = None
    
    def fetch_option_price(self, instrument_key: str) -> Optional[float]:
        """
        Fetch current option price via quote API.
        
        Args:
            instrument_key: Option instrument key
            
        Returns:
            Current LTP or None
        """
        try:
            quote_response = get_ltp_quote(self.access_token, instrument_key)
            
            if quote_response and 'data' in quote_response:
                quote_data = quote_response['data']
                
                # The data is keyed by instrument_key or 'NSE_FO:...' 
                # Upstox sometimes returns "NSE_FO:123" even if we asked for "NSE_FO|123"
                # But usually keys match what we requested
                
                if instrument_key in quote_data:
                    return quote_data[instrument_key].get('last_price')
                
                # Fallback: check values if key mismatch
                for key, data in quote_data.items():
                   if 'last_price' in data:
                       return data['last_price']
                       
            return None
        except Exception as e:
            self.log(f"⚠️ Error fetching option price: {e}")
            return None
    
    def on_market_data(self, data):
        """
        WebSocket callback for market data updates.
        """
        try:
            # Handle Upstox 'full' mode structure wrapper
            if 'marketInfo' in data:
                data = data['marketInfo'] # Unwrap
            
            # Update futures price
            instrument_key = data.get('instrument_key')
            
            if instrument_key == self.futures_instrument_key:
                # Update futures price
                ltp = data.get('last_price', 0)
                if not ltp:
                    # Try accessing nested structures from fullFeed
                    full_feed = data.get('fullFeed', {})
                    market_ff = full_feed.get('marketFF', {})
                    ltp = market_ff.get('ltpc', {}).get('ltp', 0)
                    
                    if not ltp:
                        # Fallback for other structures
                        ltp = data.get('ltpc', {}).get('ltp', 0)
                
                if ltp > 0:
                    self.futures_price = ltp
                    # Update Aggregator
                    self.futures_aggregator.add_tick(instrument_key, datetime.now(), ltp)
                
                # Update VWAP from Average Price (ATP)
                atp = data.get('average_price', 0)
                
                # Check nested paths for ATP
                if not atp:
                    # structure: fullFeed -> marketFF -> atp
                    full_feed = data.get('fullFeed', {})
                    market_ff = full_feed.get('marketFF', {})
                    atp = market_ff.get('atp', 0)
                    
                    if not atp:
                         # Fallback for other structures
                         atp = data.get('market_full', {}).get('average_price', 0)

                
                # NOTE: We now calculate VWAP from 1-minute candles to match charts better.
                # Disabling WebSocket 'atp' update to avoid mismatch flickering.
                # if atp > 0:
                #    self.current_vwap = atp 
            
            # If we have positions, update option prices
            
            # If we have positions, update option prices
            elif len(self.positions) > 0:
                for pos in self.positions:
                    if pos.instrument_key == instrument_key:
                        ltp = data.get('last_price', 0)
                        if not ltp:
                            ltp = data.get('ltpc', {}).get('ltp', 0)
                            
                        if ltp > 0:
                            with self.lock:
                                pos.update_price(ltp)
                            
                            # Check exit conditions on every update
                            should_exit, exit_type, reason = self.check_exit_signal(
                                self.futures_price,
                                self.current_vwap
                            )
                            
                            if should_exit:
                                self.log(f"🚨 EXIT SIGNAL: {reason}")
                                self.execute_exit(exit_type)
        
        except Exception as e:
            self.log(f"⚠️ Error in market data callback: {e}")
    
    # ========== STRIKE & INSTRUMENT SELECTION ==========
    
    def get_atm_strike(self, spot_price: float) -> int:
        """Calculate ATM strike from spot price using dynamic step."""
        return round(spot_price / self.strike_step) * self.strike_step
    
    def get_option_strike(self, direction: str) -> int:
        """
        Get option strike based on direction.
        
        Args:
            direction: 'CE' or 'PE'
            
        Returns:
            Strike price
        """
        # Get ATM from futures price
        atm = self.get_atm_strike(self.futures_price)
        self.current_atm = atm
        
        if direction == 'CE':
            # CE: ATM + 150
            return atm + self.config['atm_offset_ce']
        else:
            # PE: ATM - 150 (offset is negative)
            return atm + self.config['atm_offset_pe']
    
    def get_option_instrument_key(self, strike: int, option_type: str) -> Optional[str]:
        """
        Get option instrument key for given strike and type.
        
        Args:
            strike: Strike price
            option_type: 'CE' or 'PE'
            
        Returns:
            Instrument key or None
        """
        try:
            # Get expiry
            expiry = get_expiry_for_strategy(
                self.access_token,
                self.config.get('expiry_type', 'current_week'),
                self.config['underlying']
            )
            
            # Get instrument key
            instrument_key = get_option_instrument_key(
                underlying_symbol=self.config['underlying'],
                strike_price=strike,
                option_type=option_type,
                nse_data=self.nse_data
            )
            
            return instrument_key
            
        except Exception as e:
            self.log(f"❌ Error getting option instrument key: {e}")
            return None
    
    # ========== ORDER EXECUTION ==========
    
    def execute_trade(self, action: str, direction: str, strike: int, 
                     instrument_key: str, price: float, pyramid_level: int = 0):
        """
        Execute trade order.
        
        Args:
            action: 'ENTRY' or 'EXIT'
            direction: 'CE' or 'PE'
            strike: Strike price
            instrument_key: Option instrument key
            price: Current option price
            pyramid_level: Pyramid level (0 for initial entry)
        """
        try:
            lot_size = self.config['lot_size']
            transaction_type = "SELL" if action == "ENTRY" else "BUY"
            
            self.log(f"\n{'='*60}")
            self.log(f"📝 {action} Order: {transaction_type} {lot_size} lot {direction} {strike}")
            self.log(f"   Price: {price:.2f} | Level: {pyramid_level}")
            
            if self.config.get('dry_run', False):
                self.log("   [DRY RUN - No actual order placed]")
                
                # Simulate order for tracking
                if action == "ENTRY":
                    pos = Position(
                        direction=direction,
                        strike=strike,
                        entry_price=price,
                        lot_size=lot_size,
                        pyramid_level=pyramid_level,
                        instrument_key=instrument_key,
                        pnl_multiplier=self.pnl_multiplier
                    )
                    with self.lock:
                        self.positions.append(pos)
                    self.current_direction = direction
                    
                    # Subscribe to option updates
                    if self.streamer:
                        self.streamer.subscribe_market_data([instrument_key], mode='ltpc')
                    
                    self.log(f"✅ Position added: {len(self.positions)} total")
                
                elif action == "EXIT":
                    total_pnl = self.get_total_pnl()
                    self.log(f"💰 Total P&L: ₹{total_pnl:.2f}")
                    with self.lock:
                        self.clear_positions()
                    
            else:
                # Real order execution using Kotak Neo
                expiry_str = get_expiry_for_strategy(self.access_token, self.config.get('expiry_type', 'current_week'), self.config['underlying'])
                expiry_dt = datetime.strptime(expiry_str, "%Y-%m-%d")
                
                # Kotak uses 'B'/'S' for transaction_type
                kotak_trans_type = 'S' if transaction_type == "SELL" else 'B'
                
                # Resolve Kotak Symbol
                _, trading_symbol = get_strike_token(self.kotak_broker, strike, direction, expiry_dt)
                
                if not trading_symbol:
                    self.log(f"❌ Could not resolve Kotak symbol for {direction} {strike}")
                    return
                
                # Calculate Quantity using Kotak's lot size
                from kotak_api.lib.trading_utils import get_lot_size as get_kotak_lot_size
                klot_size = get_kotak_lot_size(self.kotak_broker.master_df, trading_symbol)
                quantity = lot_size * klot_size
                
                # Place Order via Kotak OrderManager
                order_id = self.order_mgr.place_order(
                    symbol=trading_symbol,
                    qty=quantity,
                    transaction_type=kotak_trans_type,
                    tag=f"VWAP_{action}_{direction}",
                    order_type="MKT",
                    product="MIS" if self.config['product_type'] == 'D' else 'NRML'
                )
                
                if order_id:
                    self.log(f"✅ Kotak Order Placed for {trading_symbol}. ID: {order_id}")
                    
                    if action == "ENTRY":
                        pos = Position(
                            direction=direction,
                            strike=strike,
                            entry_price=price,
                            lot_size=lot_size,
                            pyramid_level=pyramid_level,
                            instrument_key=instrument_key,
                            pnl_multiplier=self.pnl_multiplier
                        )
                        with self.lock:
                            self.positions.append(pos)
                        self.current_direction = direction
                        
                        # Subscribe to option updates (via Upstox Websocket for live tracking)
                        if self.streamer:
                            self.streamer.subscribe_market_data([instrument_key], mode='ltpc')
                            
                    elif action == "EXIT":
                        total_pnl = self.get_total_pnl()
                        self.log(f"💰 Total P&L: ₹{total_pnl:.2f}")
                        with self.lock:
                            self.clear_positions()
                else:
                    self.log(f"❌ Failed to place Kotak order for {trading_symbol}")
            
            self.log(f"{'='*60}\n")
            
        except Exception as e:
            self.log(f"❌ Error executing trade: {e}")
            import traceback
            traceback.print_exc()
    
    def execute_entry(self, direction: str):
        """Execute entry order."""
        strike = self.get_option_strike(direction)
        instrument_key = self.get_option_instrument_key(strike, direction)
        
        if not instrument_key:
            self.log(f"❌ Could not find instrument for {direction} {strike}")
            return
        
        # Get current option price
        price = self.fetch_option_price(instrument_key)
        if not price:
            self.log(f"❌ Could not fetch price for {direction} {strike}")
            return
        
        pyramid_level = len(self.positions)
        self.execute_trade("ENTRY", direction, strike, instrument_key, price, pyramid_level)
    
    def execute_exit(self, exit_type: str):
        """Execute exit for all positions."""
        if len(self.positions) == 0:
            return
        
        # Use first position's details (all should be same strike/direction)
        first_pos = self.positions[0]
        
        # Get current price
        price = self.fetch_option_price(first_pos.instrument_key)
        if not price:
            price = first_pos.current_price
        
        # Exit all positions (sum up lots)
        total_lots = sum(pos.lot_size for pos in self.positions)
        
        self.execute_trade(
            "EXIT",
            first_pos.direction,
            first_pos.strike,
            first_pos.instrument_key,
            price,
            0
        )
    
    # ========== MAIN STRATEGY LOOP ==========
    
    def display_status(self):
        """Silent - status shown in live ticker only."""
        pass
    
    def run(self):
        """Main strategy execution loop."""
        print("▶️  Live Monitoring Started\n")
        
        # Initialize previous values
        self.prev_close = None
        self.prev_ema = None
        
        # Warmup counter to prevent trading on historical signals
        self.candles_processed = 0
        self.last_pcr = 0.0
        
        try:
            while True:
                current_time = datetime.now()
                
                # Check if within trading hours
                entry_start = datetime.strptime(self.config['entry_start_time'], '%H:%M').time()
                exit_time = datetime.strptime(self.config['exit_time'], '%H:%M').time()
                
                if current_time.time() < entry_start:
                    self.log(f"⏰ Waiting for market opening at {self.config['entry_start_time']}...")
                    time.sleep(60)
                    continue
                
                if current_time.time() > exit_time:
                    if len(self.positions) > 0:
                        self.log("🔔 Market closing - Exiting all positions")
                        self.execute_exit("TIME_EXIT")
                    self.log("✅ Strategy stopped - Market closed")
                    break
                
                # Fetch latest candle data (WebSocket Aggregated)
                candles_df = self.futures_aggregator.get_dataframe(self.futures_instrument_key)
                
                # Check if we have enough data (at least 1 candle)
                if candles_df.empty:
                    # Fallback to REST only if completely empty (start of day panic)
                    candles_df = self.fetch_futures_data()
                
                if candles_df is None or candles_df.empty:
                    self.log("⚠️ No candle data - retrying...")
                    time.sleep(30)
                    continue
                
                
                # Update indicators (VWAP from ticks, EMA from stitched)
                self.update_indicators(candles_df)
                
                # Increment candles processed (warmup tracker)
                self.candles_processed += 1
                
                # Display status
                self.display_status()
                
                # Safety check: Ensure valid price before trading
                if self.futures_price == 0:
                    self.log("⚠️ Futures price is 0, waiting for data...")
                    time.sleep(1)
                    continue
                
                # Warmup period: Skip trading on first candle to avoid historical signals
                if self.candles_processed < 2:
                    pass  # Silent warmup
                else:
                    # Check entry conditions (if no position)
                    # Check entry conditions (if no position)
                    if len(self.positions) == 0:
                        # Fetch PCR for OI entry filter
                        pcr = None
                        change_pcr = None
                        if self.config.get('oi_check_enabled', False):
                            try:
                                # Use fixed strikes determined at startup
                                strikes = self.fixed_oi_strikes
                                
                                # If for some reason they weren't initialized, calculate them now (fallback)
                                if not strikes:
                                    quote = get_market_quote_for_instrument(self.access_token, self.oi_analyzer.underlying_key)
                                    current_spot = quote.get('last_price', self.futures_price) if quote else self.futures_price
                                    atm = self.get_atm_strike(current_spot)
                                    radius = self.config.get('oi_strikes_radius', 4)
                                    strikes = [atm + (i * self.strike_step) for i in range(-radius, radius + 1)]
                                
                                # Use current week expiry
                                from lib.utils.expiry_cache import get_expiry_for_strategy
                                expiry = get_expiry_for_strategy(self.access_token, self.config.get('expiry_type', 'current_week'), self.config['underlying'])
                                
                                # Get option chain - center based on radius
                                option_chain_df = get_option_chain_atm(
                                    self.access_token, self.oi_analyzer.underlying_key, expiry,
                                    strikes_above=self.config.get('oi_strikes_radius', 4) + 2, 
                                    strikes_below=self.config.get('oi_strikes_radius', 4) + 2
                                )
                                
                                if not option_chain_df.empty:
                                    oi_data = self.oi_analyzer.calculate_cumulative_oi(strikes, option_chain_df)
                                    if "error" not in oi_data:
                                        pcr = oi_data.get('pcr')
                                        change_pcr = oi_data.get('change_pcr', 0)
                                        self.last_pcr = pcr
                                        self.last_change_pcr = change_pcr
                                        self.log(f"📊 Cumulative OI PCR (Total): {pcr:.2f} | 🔥 Change PCR: {change_pcr:.2f}")
                            except Exception as e:
                                self.log(f"⚠️ Error in OI analysis: {e}")

                        should_enter, direction, reason = self.check_entry_signal(
                            self.futures_price,
                            self.current_vwap,
                            self.current_ema,
                            self.prev_close,
                            self.prev_ema,
                            pcr=change_pcr
                        )
                        
                        if should_enter:
                            self.log(f"🎯 {reason}")
                            self.execute_entry(direction)
                        else:
                            # Log reason for no signal (in verbose mode)
                            if self.config.get('verbose', True):
                                # Only log every 3 minutes to avoid cluttering, or if reason changes
                                if getattr(self, '_last_reason', '') != reason:
                                    self.log(f"🔍 No Entry Signal: {reason}")
                                    self._last_reason = reason
                    
                    # Check pyramid conditions (if has position)
                    elif len(self.positions) > 0:
                        can_pyramid, pyramid_reason = self.can_add_pyramid()
                        
                        if can_pyramid:
                            self.log(f"📈 PYRAMID: {pyramid_reason}")
                            self.execute_entry(self.current_direction)
                
                # Live monitoring - update every second
                next_candle_check = datetime.now() + timedelta(seconds=self.candle_check_interval)
                
                while datetime.now() < next_candle_check:
                    remaining = int((next_candle_check - datetime.now()).total_seconds())
                    
                    # Display current values every second
                    prev_ema_str = f"{self.prev_ema:.2f}" if self.prev_ema else "N/A"
                    prev_close_str = f"{self.prev_close:.2f}" if self.prev_close else "N/A"
                    pcr_str = f"{self.last_pcr:.2f}" if self.last_pcr > 0 else "N/A"
                    chg_pcr_str = f"{self.last_change_pcr:.2f}" if self.last_change_pcr > 0 else "N/A"
                    
                    # Calculate P&L if in position
                    pnl_str = ""
                    if len(self.positions) > 0:
                        total_pnl = self.get_total_pnl()
                        direction = self.current_direction
                        lots = sum(p.lot_size for p in self.positions)
                        pnl_str = f" | {direction} P&L: {total_pnl:8.2f} ({lots}L)"

                    status = (
                        f"\r[{remaining:3d}s] FUT: {self.futures_price:8.2f} | "
                        f"VWAP: {self.current_vwap:8.2f} | "
                        f"PC: {prev_close_str:>8} | "
                        f"PCR(T/C): {pcr_str}/{chg_pcr_str}{pnl_str}"
                    )
                    
                    sys.stdout.write(status)
                    sys.stdout.flush()
                    time.sleep(1)
                
                sys.stdout.write("\r" + " "*120 + "\r")  # Clear line
                
        except KeyboardInterrupt:
            self.log("\n⚠️ Strategy interrupted by user")
            if len(self.positions) > 0:
                self.log("Exiting all positions...")
                self.execute_exit("MANUAL_EXIT")
        
        except Exception as e:
            self.log(f"❌ Error in main loop: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            # Cleanup
            if self.streamer:
                self.streamer.disconnect_all()
            self.log("👋 Strategy execution completed")


if __name__ == "__main__":
    from lib.core.authentication import check_existing_token, perform_authentication, save_access_token
    
    # Authentication
    if not check_existing_token():
        try:
            access_token = perform_authentication()
            save_access_token(access_token)
        except Exception as e:
            print(f"❌ Authentication failed: {e}")
            sys.exit(1)
    
    # Load token
    token_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'lib', 'core', 'accessToken.txt')
    with open(token_path, 'r') as f:
        access_token = f.read().strip()
    
    # Create and run strategy
    strategy = FuturesVWAPEMALive(access_token, CONFIG)
    
    if strategy.initialize():
        strategy.run()

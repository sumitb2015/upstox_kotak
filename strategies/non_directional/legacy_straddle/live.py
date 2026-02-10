"""
Intraday Short Straddle Strategy Implementation
Strategy: Short ATM CE and PE, manage positions based on ratio thresholds
"""

import sys
import os
import time

# Add the project root to sys.path to allow direct execution and module imports
current_dir = os.path.dirname(os.path.abspath(__file__))
# current is strategies/upstox_only/
# parent is strategies/
# root is ../
root_dir = os.path.abspath(os.path.join(current_dir, '..', '..', '..'))
if root_dir not in sys.path:
    sys.path.append(root_dir)
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Tuple
from lib.api.market_quotes import get_ltp_quote, get_multiple_ltp_quotes
from lib.utils.instrument_utils import get_nifty_option_instrument_keys
from lib.api.order_management import place_order, get_order_book, place_multi_order
from lib.oi_analysis.oi_analysis import OIAnalyzer
from lib.oi_analysis.oi_monitoring import OIMonitor
from lib.oi_analysis.cumulative_oi_analysis import CumulativeOIAnalyzer
from lib.oi_analysis.oi_strangle_analyzer import OIStrangleAnalyzer
from lib.utils.funds_margin import get_funds_and_margin, check_margin_availability_for_order
from lib.utils.margin_calculator import get_margin_details, check_margin_availability
from lib.api.streaming import UpstoxStreamer
from lib.core.config import Config


class ShortStraddleStrategy:
    """
    Intraday Short Straddle Strategy Implementation
    """
    
    def __init__(self, access_token, nse_data, underlying_symbol="NIFTY", lot_size=1, profit_target=3000, max_loss_limit=3000, ratio_threshold=0.6, straddle_width_threshold=0.2, max_deviation_points=200, enable_oi_analysis=True, expiry_day_mode=False, verbose=False, streamer=None):
        """
        Initialize the short straddle strategy.
        
        Args:
            access_token (str): Upstox access token
            nse_data (DataFrame): NSE market data
            underlying_symbol (str): Underlying symbol (default: NIFTY)
            lot_size (int): Lot size for trading (default: 1)
            profit_target (float): Total profit target (default: 3000)
            max_loss_limit (float): Maximum loss limit (default: 3000)
            ratio_threshold (float): Ratio threshold for position management (default: 0.6)
            straddle_width_threshold (float): Straddle width threshold for entry (default: 0.2 = 20%)
            max_deviation_points (int): Maximum deviation from original ATM in points (default: 200)
            enable_oi_analysis (bool): Enable OI analysis integration (default: True)
            expiry_day_mode (bool): Enable expiry day mode with dynamic ratio thresholds (default: False)
            verbose (bool): Enable verbose logging (default: False)
        """
        self.access_token = access_token
        self.nse_data = nse_data
        self.underlying_symbol = underlying_symbol
        self.lot_size = lot_size
        self.profit_target = profit_target
        self.max_loss_limit = max_loss_limit
        self.ratio_threshold = ratio_threshold
        self.straddle_width_threshold = straddle_width_threshold
        self.max_deviation_points = max_deviation_points
        self.enable_oi_analysis = enable_oi_analysis
        self.expiry_day_mode = expiry_day_mode
        self.verbose = verbose
        
        # Dynamically determine market lot size
        self.market_lot = 75  # Default fallback
        try:
            if self.nse_data is not None:
                # Filter for underlying and select an option to get its lot size
                target_underlying = self.underlying_symbol if self.underlying_symbol else "NIFTY"
                nifty_df = self.nse_data[
                    (self.nse_data['underlying_symbol'] == target_underlying) & 
                    (self.nse_data['instrument_type'].isin(['CE', 'PE', 'FUTIDX', 'FUTSTK', 'OPTSTK']))
                ]
                if not nifty_df.empty:
                    self.market_lot = int(nifty_df.iloc[0]['lot_size'])
                    print(f"📊 Detected Market Lot for {target_underlying}: {self.market_lot}")
        except Exception as e:
            print(f"⚠️ Error determining market lot: {e}, using fallback 75")
        
        # Strategy state
        self.current_strike = None
        self.original_atm_strike = None  # Track original ATM for deviation calculation
        self.active_positions = {}  # Track all active positions by strike
        self.entry_prices = {}  # Track entry prices for each position
        self.entry_straddle_prices = {}  # Track entry straddle prices for each position
        self.realized_pnl = 0  # Track realized P&L from closed positions
        self.unrealized_pnl = 0  # Track unrealized P&L from open positions
        self.total_profit = 0
        self.is_strategy_active = False
        self.is_strategy_stopped = False  # Flag to prevent re-entry after max loss
        self.trades_log = []
        self.api_call_count = 0  # Track API calls to monitor rate limits
        self.last_api_reset = datetime.now()  # Track when to reset API counter
        
        # Historical data and pivot calculations
        self.previous_day_ohlc = None
        self.pdh = None  # Previous Day High
        self.pdl = None  # Previous Day Low
        self.pdc = None  # Previous Day Close
        self.pdo = None  # Previous Day Open
        self.cpr_levels = {}
        self.camarilla_pivots = {}
        self._initialize_historical_data_and_pivots()
        
        # OI Analysis components
        if self.enable_oi_analysis:
            # Initialize with custom thresholds for better analysis
            self.oi_analyzer = OIAnalyzer(
                access_token, 
                "NSE_INDEX|Nifty 50",
                min_oi_threshold=5.0,      # Minimum 5% OI change to consider significant
                significant_oi_threshold=10.0  # 10% OI change for high significance
            )
            self.oi_monitor = OIMonitor(access_token, "NSE_INDEX|Nifty 50")
            self.cumulative_oi_analyzer = CumulativeOIAnalyzer(access_token, "NSE_INDEX|Nifty 50")
            self.oi_strangle_analyzer = OIStrangleAnalyzer(access_token, "NSE_INDEX|Nifty 50")
            self.oi_sentiment_history = []
            self.oi_alerts = []
            self.cumulative_oi_history = []
            self.strangle_positions = {}  # Track strangle positions separately
            self.strangle_history = []  # Track strangle analysis history
            
            # Enhanced risk adjustment factors (with OI analysis)
            self.risk_adjustment_factors = {
                'oi_bullish_multiplier': 1.5,  # Increase targets when OI is bullish for sellers
                'oi_bearish_multiplier': 0.7,  # Decrease targets when OI is bearish for sellers
                'volatility_multiplier': 1.2,  # Adjust for high volatility
                'time_decay_multiplier': 1.3,  # Increase targets as time decay accelerates
                'profit_momentum_multiplier': 1.4  # Increase targets when in strong profit
            }
        else:
            self.oi_analyzer = None
            self.oi_monitor = None
            self.cumulative_oi_analyzer = None
            self.oi_strangle_analyzer = None
            self.strangle_positions = {}  # Initialize even when OI analysis is disabled
            self.strangle_history = []  # Initialize even when OI analysis is disabled
            
            # Safe OTM Options Strategy (disabled when OI analysis is off)
            self.safe_otm_enabled = False  # Disable safe OTM strategy without OI analysis
            self.max_safe_otm_positions = 3
            self.safe_otm_positions = {}  # Track safe OTM positions
            self.safe_otm_history = []  # Track safe OTM analysis history
            
            # Position scaling system (disabled when OI analysis is off)
            self.position_scaling_enabled = False  # Disable position scaling without OI analysis
            self.max_scaling_level = 3
            self.scaling_profit_threshold = 0.3
            self.scaling_oi_confidence_threshold = 70

        # --- WebSocket Streaming & Price Cache ---
        self.price_cache = {}  # {instrument_key: {'price': 123.4, 'time': datetime}}
        self.detailed_market_cache = {} # {instrument_key: {'greeks': {}, 'ohlc': {}, 'depth': {}}}
        self.streamer = streamer
        self.subscribed_keys = set()
        
        # Order status tracking (WebSocket-updated)
        self.order_status_cache = {}  # {order_id: {status, filled_qty, avg_price, timestamp}}
        self.order_update_events = {}  # {order_id: threading.Event()} for synchronization
        
        # Initial subscription to NIFTY Index
        self.nifty_key = "NSE_INDEX|Nifty 50"
        self.vix_key = "NSE_INDEX|India VIX"
        self.subscribed_keys.add(self.nifty_key)
        self.subscribed_keys.add(self.vix_key)
        
        # Position scaling system (common for both OI enabled/disabled)
        self.position_scaling_enabled = True if self.enable_oi_analysis else False  # Enable only with OI analysis
        self.max_scaling_level = 3  # Maximum 3x position size (original + 2 additions)
        self.scaling_profit_threshold = 0.3  # Minimum 30% profit to consider scaling
        self.scaling_oi_confidence_threshold = 70  # Minimum OI confidence for scaling
        self.scaled_positions = {}  # Track scaled positions
        
        # Dynamic Risk Management System (common for both modes)
        self.dynamic_risk_enabled = True  # Enable dynamic risk management
        self.base_profit_target = profit_target  # Base profit target (₹3000)
        self.base_stop_loss = max_loss_limit  # Base stop loss (₹3000)
        self.current_profit_target = profit_target  # Current dynamic profit target
        self.current_stop_loss = -max_loss_limit  # Current dynamic stop loss (negative value)
        
        # Trailing Stop Loss System
        self.trailing_stop_enabled = True
        self.trailing_stop_distance = 1000
        self.trailing_stop_triggered = False
        self.highest_profit = 0
        self.trailing_stop_level = 0
        
        # Risk adjustment factors
        if self.enable_oi_analysis:
            # Enhanced risk adjustment factors (with OI analysis)
            self.risk_adjustment_factors = {
                'oi_bullish_multiplier': 1.5,
                'oi_bearish_multiplier': 0.7,
                'volatility_multiplier': 1.2,
                'time_decay_multiplier': 1.3,
                'profit_momentum_multiplier': 1.4
            }
        else:
            # Basic risk adjustment factors (without OI analysis)
            self.risk_adjustment_factors = {
                'volatility_multiplier': 1.2,
                'time_decay_multiplier': 1.3,
                'profit_momentum_multiplier': 1.4
            }
        
        # Strangle Position Management
        self.max_strangle_positions = 2  # Maximum number of concurrent strangle positions
        
        # Safe OTM Options Strategy (Expiry Day)
        self.safe_otm_enabled = True  # Enable safe OTM options strategy
        self.max_safe_otm_positions = 3  # Maximum number of concurrent safe OTM positions
        self.safe_otm_positions = {}  # Track safe OTM positions
        self.safe_otm_history = []  # Track safe OTM analysis history
        
        # Safe OTM Criteria
        self.safe_otm_criteria = {
            'min_distance_from_atm': 2,  # Minimum 2 strikes (100 points) from ATM
            'max_distance_from_atm': 6,  # Maximum 6 strikes (300 points) from ATM
            'min_premium': 5.0,  # Minimum ₹5 premium
            'max_premium': 25.0,  # Maximum ₹25 premium (easy money)
            'min_oi_change': 10.0,  # Minimum 10% OI change for significance
            'min_selling_score': 70,  # Minimum 70% selling score
            'max_risk_per_position': 1000,  # Maximum ₹1000 risk per position
            'profit_target_per_position': 500  # Target ₹500 profit per position
        }
        
        # Trailing Stop Loss System
        self.trailing_stop_enabled = True  # Enable trailing stop loss
        self.trailing_stop_distance = 1000  # Initial trailing distance (₹1000)
        self.trailing_stop_triggered = False  # Track if trailing stop is active
        self.highest_profit = 0  # Track highest profit for trailing stop
        self.trailing_stop_level = 0  # Current trailing stop level
        
        # Tiered Trailing SL Definition
        # Format: {profit_milestone: locked_profit}
        self.trailing_tiers = {
            0.3: 0.1,   # At 30% of profit target, lock 10%
            0.5: 0.25,  # At 50% of profit target, lock 25%
            0.8: 0.6,   # At 80% of profit target, lock 60%
            1.0: 0.85   # At 100% of profit target, lock 85%
        }
        
        # Get current ATM strike
        self.current_strike = self.get_atm_strike()
        self.original_atm_strike = self.current_strike  # Store original ATM for deviation calculation
        

        if not self.verbose:
            print(f"Strategy: {underlying_symbol} | ATM: {self.current_strike} | Target: ₹{self.profit_target} | Stop: ₹{self.max_loss_limit}")
        else:
            # Detailed output for verbose mode
            print(f"Strategy initialized for {underlying_symbol} with ATM strike: {self.current_strike}")
            print(f"Profit target: ₹{self.profit_target}")
            print(f"Max loss limit: ₹{self.max_loss_limit}")
            print(f"Straddle width threshold: {self.straddle_width_threshold*100:.0f}%")
            print(f"Maximum deviation limit: {self.max_deviation_points} points from ATM")
            if self.enable_oi_analysis:
                print(f"📊 OI Analysis: ENABLED")
            else:
                print(f"📊 OI Analysis: DISABLED")
            
            if self.expiry_day_mode:
                print(f"📅 Expiry Day Mode: ENABLED (Dynamic ratio thresholds)")
            else:
                print(f"📅 Expiry Day Mode: DISABLED")
            
            if self.position_scaling_enabled:
                print(f"📈 Position Scaling: ENABLED (Max {self.max_scaling_level}x, Min {self.scaling_profit_threshold*100:.0f}% profit)")
            else:
                print(f"📈 Position Scaling: DISABLED")
            
            if self.dynamic_risk_enabled:
                print(f"🎯 Dynamic Risk Management: ENABLED")
                print(f"   Base Profit Target: ₹{self.base_profit_target}")
                print(f"   Base Stop Loss: ₹{self.base_stop_loss}")
                print(f"   Trailing Stop: {'ENABLED' if self.trailing_stop_enabled else 'DISABLED'}")
            else:
                print(f"🎯 Dynamic Risk Management: DISABLED")
            
            if self.enable_oi_analysis:
                print(f"🎯 Continuous Strangle Entry: ENABLED (Max {self.max_strangle_positions} positions)")
            else:
                print(f"🎯 Continuous Strangle Entry: DISABLED")
            
            if self.safe_otm_enabled:
                expiry_status = "ENABLED" if self._is_nifty_expiry_day() else "DISABLED (Not NIFTY expiry day)"
                print(f"💰 Safe OTM Options: {expiry_status} (Max {self.max_safe_otm_positions} positions)")
                if self._is_nifty_expiry_day():
                    print(f"   Min Distance: {self.safe_otm_criteria['min_distance_from_atm']} strikes")
                    print(f"   Max Distance: {self.safe_otm_criteria['max_distance_from_atm']} strikes")
                    print(f"   Premium Range: ₹{self.safe_otm_criteria['min_premium']}-₹{self.safe_otm_criteria['max_premium']}")
                    print(f"   Min Selling Score: {self.safe_otm_criteria['min_selling_score']}%")
            else:
                print(f"💰 Safe OTM Options: DISABLED")
        
        # Initialize Portfolio WebSocket for real-time order updates
        if self.verbose:
            print("📡 Initializing Portfolio WebSocket for order updates...")
        
        # Import here to avoid circular dependency
        from lib.api.streaming import UpstoxStreamer
        
        # Create streamer if not already exists
        if self.streamer is None:
            self.streamer = UpstoxStreamer(access_token)
        
        # Connect to portfolio stream with order callback
        try:
            self.streamer.connect_portfolio(
                order_update=True,
                position_update=True,
                holding_update=False,
                gtt_update=False,
                on_order=self._handle_order_update,
                on_position=self._handle_position_update
            )
            if self.verbose:
                print("✅ Portfolio WebSocket initialized (orders + positions)")
        except Exception as e:
            if self.verbose:
                print(f"⚠️ Failed to initialize Portfolio WebSocket: {e}")
            print("⚠️ Will use REST API polling for order status")
    
    def _initialize_historical_data_and_pivots(self):
        """
        Initialize historical data and calculate CPR and Camarilla pivot levels
        """
        try:
            if self.verbose:
                print("📊 Fetching historical data and calculating pivot levels...")
            
            # Fetch previous day's OHLC data
            self.previous_day_ohlc = self._fetch_previous_day_ohlc()
            
            if self.previous_day_ohlc:
                # Store PDH, PDL, PDC for easy access
                self.pdh = self.previous_day_ohlc['high']  # Previous Day High
                self.pdl = self.previous_day_ohlc['low']   # Previous Day Low
                self.pdc = self.previous_day_ohlc['close'] # Previous Day Close
                self.pdo = self.previous_day_ohlc['open']  # Previous Day Open
                
                # Calculate CPR levels
                self.cpr_levels = self._calculate_cpr_levels(self.previous_day_ohlc)
                
                # Calculate Camarilla pivots
                self.camarilla_pivots = self._calculate_camarilla_pivots(self.previous_day_ohlc)
                
                # Display the calculated levels only in verbose mode
                if self.verbose:
                    self._display_pivot_levels()
            else:
                if self.verbose:
                    print("⚠️ Could not fetch historical data. Pivot levels not calculated.")
                
        except Exception as e:
            if self.verbose:
                print(f"❌ Error initializing historical data and pivots: {e}")
            self.previous_day_ohlc = None
            self.cpr_levels = {}
            self.camarilla_pivots = {}
    
    def _fetch_previous_day_ohlc(self):
        """
        Fetch previous day's OHLC data for NIFTY using existing fetch_historical_data function
        
        Returns:
            dict: Previous day's OHLC data or None if failed
        """
        try:
            from datetime import datetime, timedelta
            from lib.api.market_data import fetch_historical_data
            
            # Calculate previous trading day
            today = datetime.now()
            if today.weekday() == 0:  # Monday
                # Previous trading day is Friday
                previous_day = today - timedelta(days=3)
            elif today.weekday() == 6:  # Sunday
                # Previous trading day is Friday
                previous_day = today - timedelta(days=2)
            else:
                # Previous trading day is yesterday
                previous_day = today - timedelta(days=1)
            
            # Format date for API
            date_str = previous_day.strftime('%Y-%m-%d')
            
            # Use existing fetch_historical_data function
            # For daily data, use "days" with interval 1 (as per official Upstox API docs)
            df = fetch_historical_data(
                access_token=self.access_token,
                symbol="NSE_INDEX|Nifty 50",
                interval_type="days",
                interval=1,  # 1 day interval
                start_date=date_str,
                end_date=date_str
            )
            
            if not df.empty:
                # Get the last row (previous day's data)
                last_row = df.iloc[-1]
                ohlc = {
                    'date': last_row['timestamp'].strftime('%Y-%m-%d'),
                    'open': float(last_row['open']),
                    'high': float(last_row['high']),
                    'low': float(last_row['low']),
                    'close': float(last_row['close']),
                    'volume': int(last_row['volume'])
                }
                
                if self.verbose:
                    print(f"✅ Fetched previous day OHLC for {date_str}:")
                    print(f"   Open: ₹{ohlc['open']:.2f}")
                    print(f"   High: ₹{ohlc['high']:.2f}")
                    print(f"   Low: ₹{ohlc['low']:.2f}")
                    print(f"   Close: ₹{ohlc['close']:.2f}")
                    print(f"   Volume: {ohlc['volume']:,}")
                
                return ohlc
            else:
                print(f"⚠️ No historical data found for {date_str}")
                return None
                
        except Exception as e:
            print(f"❌ Error fetching historical data: {e}")
            return None
    
    def _calculate_cpr_levels(self, ohlc):
        """
        Calculate Central Pivot Range (CPR) levels
        
        Args:
            ohlc (dict): Previous day's OHLC data
            
        Returns:
            dict: CPR levels
        """
        try:
            high = ohlc['high']
            low = ohlc['low']
            close = ohlc['close']
            
            # Calculate pivot point
            pivot = (high + low + close) / 3
            
            # Calculate bottom central pivot (BC)
            bc = (high + low) / 2
            
            # Calculate top central pivot (TC)
            tc = (pivot - bc) + pivot
            
            # Calculate central pivot range
            cpr = tc - bc
            
            # Calculate additional levels
            r1 = 2 * pivot - low
            r2 = pivot + (high - low)
            r3 = high + 2 * (pivot - low)
            r4 = r3 + (high - low)
            
            s1 = 2 * pivot - high
            s2 = pivot - (high - low)
            s3 = low - 2 * (high - pivot)
            s4 = s3 - (high - low)
            
            cpr_levels = {
                'pivot': round(pivot, 2),
                'tc': round(tc, 2),
                'bc': round(bc, 2),
                'cpr': round(cpr, 2),
                'r1': round(r1, 2),
                'r2': round(r2, 2),
                'r3': round(r3, 2),
                'r4': round(r4, 2),
                's1': round(s1, 2),
                's2': round(s2, 2),
                's3': round(s3, 2),
                's4': round(s4, 2)
            }
            
            return cpr_levels
            
        except Exception as e:
            print(f"❌ Error calculating CPR levels: {e}")
            return {}
    
    def _calculate_camarilla_pivots(self, ohlc):
        """
        Calculate Camarilla pivot levels
        
        Args:
            ohlc (dict): Previous day's OHLC data
            
        Returns:
            dict: Camarilla pivot levels
        """
        try:
            high = ohlc['high']
            low = ohlc['low']
            close = ohlc['close']
            
            # Calculate pivot point
            pivot = (high + low + close) / 3
            
            # Calculate range
            range_val = high - low
            
            # Camarilla pivot levels
            r1 = close + (range_val * 1.1 / 12)
            r2 = close + (range_val * 1.1 / 6)
            r3 = close + (range_val * 1.1 / 4)
            r4 = close + (range_val * 1.1 / 2)
            r5 = close + (range_val * 1.1)
            r6 = close + (range_val * 1.1 * 2)
            
            s1 = close - (range_val * 1.1 / 12)
            s2 = close - (range_val * 1.1 / 6)
            s3 = close - (range_val * 1.1 / 4)
            s4 = close - (range_val * 1.1 / 2)
            s5 = close - (range_val * 1.1)
            s6 = close - (range_val * 1.1 * 2)
            
            camarilla_pivots = {
                'pivot': round(pivot, 2),
                'r1': round(r1, 2),
                'r2': round(r2, 2),
                'r3': round(r3, 2),
                'r4': round(r4, 2),
                'r5': round(r5, 2),
                'r6': round(r6, 2),
                's1': round(s1, 2),
                's2': round(s2, 2),
                's3': round(s3, 2),
                's4': round(s4, 2),
                's5': round(s5, 2),
                's6': round(s6, 2)
            }
            
            return camarilla_pivots
            
        except Exception as e:
            print(f"❌ Error calculating Camarilla pivots: {e}")
            return {}
    
    def _display_pivot_levels(self):
        """
        Display calculated pivot levels
        """
        try:
            print("\n" + "="*60)
            print("📊 PIVOT LEVELS CALCULATION")
            print("="*60)
            
            # Display Previous Day OHLC
            if self.previous_day_ohlc:
                print(f"\n📅 PREVIOUS DAY OHLC ({self.previous_day_ohlc['date']}):")
                print(f"   Open:  ₹{self.pdo:.2f}")
                print(f"   High:  ₹{self.pdh:.2f} (PDH)")
                print(f"   Low:   ₹{self.pdl:.2f} (PDL)")
                print(f"   Close: ₹{self.pdc:.2f} (PDC)")
                print(f"   Range: ₹{self.pdh - self.pdl:.2f}")
            
            if self.cpr_levels:
                print("\n🎯 CENTRAL PIVOT RANGE (CPR) LEVELS:")
                print(f"   Pivot Point: ₹{self.cpr_levels['pivot']:.2f}")
                print(f"   Top Central (TC): ₹{self.cpr_levels['tc']:.2f}")
                print(f"   Bottom Central (BC): ₹{self.cpr_levels['bc']:.2f}")
                print(f"   CPR Range: ₹{self.cpr_levels['cpr']:.2f}")
                print(f"   R1: ₹{self.cpr_levels['r1']:.2f}")
                print(f"   R2: ₹{self.cpr_levels['r2']:.2f}")
                print(f"   R3: ₹{self.cpr_levels['r3']:.2f}")
                print(f"   R4: ₹{self.cpr_levels['r4']:.2f}")
                print(f"   S1: ₹{self.cpr_levels['s1']:.2f}")
                print(f"   S2: ₹{self.cpr_levels['s2']:.2f}")
                print(f"   S3: ₹{self.cpr_levels['s3']:.2f}")
                print(f"   S4: ₹{self.cpr_levels['s4']:.2f}")
            
            if self.camarilla_pivots:
                print("\n🎯 CAMARILLA PIVOT LEVELS:")
                print(f"   Pivot Point: ₹{self.camarilla_pivots['pivot']:.2f}")
                print(f"   R1: ₹{self.camarilla_pivots['r1']:.2f}")
                print(f"   R2: ₹{self.camarilla_pivots['r2']:.2f}")
                print(f"   R3: ₹{self.camarilla_pivots['r3']:.2f}")
                print(f"   R4: ₹{self.camarilla_pivots['r4']:.2f}")
                print(f"   R5: ₹{self.camarilla_pivots['r5']:.2f}")
                print(f"   R6: ₹{self.camarilla_pivots['r6']:.2f}")
                print(f"   S1: ₹{self.camarilla_pivots['s1']:.2f}")
                print(f"   S2: ₹{self.camarilla_pivots['s2']:.2f}")
                print(f"   S3: ₹{self.camarilla_pivots['s3']:.2f}")
                print(f"   S4: ₹{self.camarilla_pivots['s4']:.2f}")
                print(f"   S5: ₹{self.camarilla_pivots['s5']:.2f}")
                print(f"   S6: ₹{self.camarilla_pivots['s6']:.2f}")
            
            print("="*60)
            
        except Exception as e:
            print(f"❌ Error displaying pivot levels: {e}")
    
    def get_cpr_levels(self):
        """
        Get CPR levels for external use
        
        Returns:
            dict: CPR levels or empty dict if not available
        """
        return self.cpr_levels if self.cpr_levels else {}
    
    def get_camarilla_pivots(self):
        """
        Get Camarilla pivot levels for external use
        
        Returns:
            dict: Camarilla pivot levels or empty dict if not available
        """
        return self.camarilla_pivots if self.camarilla_pivots else {}
    
    def get_previous_day_ohlc(self):
        """
        Get previous day's OHLC data for external use
        
        Returns:
            dict: Previous day's OHLC data or None if not available
        """
        return self.previous_day_ohlc
    
    def get_pdh(self):
        """Get Previous Day High"""
        return self.pdh
    
    def get_pdl(self):
        """Get Previous Day Low"""
        return self.pdl
    
    def get_pdc(self):
        """Get Previous Day Close"""
        return self.pdc
    
    def get_pdo(self):
        """Get Previous Day Open"""
        return self.pdo
    
    def check_margin_availability(self, required_margin, segment="equity"):
        """
        Check if sufficient margin is available for trading.
        
        Args:
            required_margin (float): Required margin amount
            segment (str): Trading segment ("equity" or "commodity")
        
        Returns:
            dict: Margin availability check results
        """
        try:
            if self.verbose:
                print(f"🔍 Checking margin availability for ₹{required_margin:,.2f} in {segment} segment...")
            
            result = check_margin_availability_for_order(
                self.access_token, 
                required_margin, 
                segment
            )
            
            if result:
                if result['margin_available']:
                    if self.verbose:
                        print(f"✅ Sufficient margin available: ₹{result['available_margin']:,.2f}")
                    return True, result
                else:
                    if self.verbose:
                        print(f"❌ Insufficient margin: Shortfall ₹{result['shortfall']:,.2f}")
                    return False, result
            else:
                if self.verbose:
                    print("❌ Failed to check margin availability")
                return False, None
                
        except Exception as e:
            if self.verbose:
                print(f"❌ Error checking margin availability: {e}")
            return False, None
    
    def get_available_funds(self, segment="equity"):
        """
        Get available funds for the specified segment.
        
        Args:
            segment (str): Trading segment ("equity" or "commodity")
        
        Returns:
            float: Available margin amount
        """
        try:
            funds_data = get_funds_and_margin(self.access_token)
            if funds_data and funds_data.get('status') == 'success':
                data = funds_data.get('data', {})
                if segment == "equity":
                    return data.get('equity', {}).get('available_margin', 0)
                elif segment == "commodity":
                    return data.get('commodity', {}).get('available_margin', 0)
                else:
                    # Return total available margin
                    equity_available = data.get('equity', {}).get('available_margin', 0)
                    commodity_available = data.get('commodity', {}).get('available_margin', 0)
                    return equity_available + commodity_available
            return 0
        except Exception as e:
            if self.verbose:
                print(f"❌ Error getting available funds: {e}")
            return 0
    
    def calculate_straddle_margin_requirement(self, ce_instrument_key, pe_instrument_key, quantity):
        """
        Calculate margin requirement for a straddle position.
        
        Args:
            ce_instrument_key (str): CE instrument key
            pe_instrument_key (str): PE instrument key
            quantity (int): Quantity for each leg
        
        Returns:
            float: Total margin requirement
        """
        try:
            if self.verbose:
                print(f"🧮 Calculating margin requirement for straddle...")
            
            # Prepare instruments for margin calculation
            instruments = [
                {
                    "instrument_key": ce_instrument_key,
                    "quantity": quantity,
                    "transaction_type": "SELL",  # Short straddle
                    "product": "D"  # Delivery
                },
                {
                    "instrument_key": pe_instrument_key,
                    "quantity": quantity,
                    "transaction_type": "SELL",  # Short straddle
                    "product": "D"  # Delivery
                }
            ]
            
            # Get margin details
            margin_data = get_margin_details(self.access_token, instruments)
            if margin_data and margin_data.get('status') == 'success':
                data = margin_data.get('data', {})
                final_margin = data.get('final_margin', 0)
                
                if self.verbose:
                    print(f"💰 Straddle margin requirement: ₹{final_margin:,.2f}")
                
                return final_margin
            else:
                if self.verbose:
                    print("❌ Failed to calculate margin requirement")
                return 0
                
        except Exception as e:
            if self.verbose:
                print(f"❌ Error calculating margin requirement: {e}")
            return 0
    
    def validate_trade_margin(self, ce_instrument_key, pe_instrument_key, quantity, segment="equity"):
        """
        Validate if there's sufficient margin for a straddle trade.
        
        Args:
            ce_instrument_key (str): CE instrument key
            pe_instrument_key (str): PE instrument key
            quantity (int): Quantity for each leg
            segment (str): Trading segment
        
        Returns:
            tuple: (is_valid, margin_info)
        """
        try:
            if self.verbose:
                print(f"🔍 Validating trade margin for straddle...")
            
            # Calculate required margin
            required_margin = self.calculate_straddle_margin_requirement(
                ce_instrument_key, pe_instrument_key, quantity
            )
            
            if required_margin <= 0:
                if self.verbose:
                    print("❌ Could not calculate margin requirement")
                return False, None
            
            # Check margin availability
            margin_available, margin_info = self.check_margin_availability(required_margin, segment)
            
            if margin_available:
                if self.verbose:
                    print(f"✅ Trade margin validation passed: ₹{required_margin:,.2f} required, ₹{margin_info['available_margin']:,.2f} available")
                return True, {
                    'required_margin': required_margin,
                    'available_margin': margin_info['available_margin'],
                    'remaining_margin': margin_info['remaining_margin'],
                    'utilization_percent': margin_info['utilization_percent']
                }
            else:
                if self.verbose:
                    print(f"❌ Trade margin validation failed: ₹{required_margin:,.2f} required, ₹{margin_info['available_margin']:,.2f} available")
                return False, {
                    'required_margin': required_margin,
                    'available_margin': margin_info['available_margin'],
                    'shortfall': margin_info['shortfall'],
                    'utilization_percent': margin_info['utilization_percent']
                }
                
        except Exception as e:
            if self.verbose:
                print(f"❌ Error validating trade margin: {e}")
            return False, None
    
    def get_atm_strike(self):
        """
        Get the current ATM (At The Money) strike price using real market data.
        
        Returns:
            int: ATM strike price
        """
        try:
            # Get current NIFTY spot price
            nifty_spot = self.get_current_spot_price()
            if nifty_spot and nifty_spot > 0:
                # Round to nearest 50 (NIFTY strike interval)
                division_result = nifty_spot / 50
                rounded_result = round(division_result)
                atm_strike = rounded_result * 50
                
                # Debug prints to identify the issue
                return atm_strike
            else:
                return 25300
        except Exception as e:
            print(f"Error calculating ATM strike: {e}")
            return 25300

    def get_india_vix(self):
        """
        Fetch India VIX last price for dynamic volatility adjustment.
        Uses WebSocket cache if available (with 5-second expiry).
        
        Returns:
            float: India VIX value or 15.0 as default
        """
        # Try cache first (with expiry check)
        if self.vix_key in self.price_cache:
            cached = self.price_cache[self.vix_key]
            age = (datetime.now() - cached['time']).total_seconds()
            if age < 30:  # 30-second cache expiry
                return cached.get('price', 15.0)
            
        try:
            vix_quote = get_ltp_quote(self.access_token, self.vix_key)
            if vix_quote and vix_quote.get('status') == 'success':
                data = vix_quote.get('data', {})
                if data:
                    vix_key_res = list(data.keys())[0]
                    vix_price = data[vix_key_res].get('last_price', 15.0)
                    # Update cache
                    self.price_cache[self.vix_key] = {'price': vix_price, 'time': datetime.now()}
                    return vix_price
            return 15.0
        except Exception as e:
            print(f"Error fetching India VIX: {e}")
            return 15.0

    def get_vix_width_threshold(self):
        """
        Calculate dynamic straddle width threshold based on India VIX.
        
        Returns:
            float: Dynamic width threshold (0.25 to 0.45)
        """
        vix = self.get_india_vix()
        
        # Base threshold is 0.25 (25%)
        # If VIX > 15, we add 1% for every 1 point of VIX above 15
        if vix > 15:
            dynamic_threshold = 0.25 + (vix - 15) * 0.01
        else:
            dynamic_threshold = 0.25
            
        # Cap at 45% to avoid entering extremely skewed straddles
        return min(dynamic_threshold, 0.45)
    
    # --- WebSocket Order Update Handlers ---
    
    def _handle_order_update(self, order_info):
        """
        Callback for real-time order status updates via Portfolio WebSocket.
        
        Args:
            order_info (dict): Order update with status, filled_qty, average_price, etc.
        """
        try:
            # Debug: Always print to confirm WebSocket is receiving data
            print(f"🔔 [DEBUG] Portfolio WebSocket - Order Update Received")
            
            order_id = order_info.get('order_id')
            status = order_info.get('status')
            filled_qty = order_info.get('filled_quantity', 0)
            avg_price = order_info.get('average_price', 0)
            symbol = order_info.get('trading_symbol', 'N/A')
            
            # Always show order updates for debugging
            print(f"📡 Order: {order_id[:8] if order_id else 'N/A'}... | {symbol} | {status} | {filled_qty}@₹{avg_price:.2f}")
            
            if not order_id:
                return
            
            # Update cache
            self.order_status_cache[order_id] = {
                'status': status,
                'filled_quantity': filled_qty,
                'average_price': avg_price,
                'timestamp': datetime.now(),
                'raw_data': order_info
            }
            
            # Trigger any waiting threads
            if order_id in self.order_update_events:
                self.order_update_events[order_id].set()
                print(f"✅ [DEBUG] Event triggered for order {order_id[:8]}...")
                
        except Exception as e:
            print(f"❌ [DEBUG] Error handling order update: {e}")
    
    def _handle_position_update(self, position_info):
        """
        Callback for real-time position updates via Portfolio WebSocket.
        
        Args:
            position_info (dict): Position update with instrument, quantity, P&L, etc.
        """
        try:
            # Debug: Always print to confirm WebSocket is receiving data
            print(f"🔔 [DEBUG] Portfolio WebSocket - Position Update Received")
            
            symbol = position_info.get('trading_symbol', 'N/A')
            quantity = position_info.get('quantity', 0)
            pnl = position_info.get('pnl', 0)
            
            # Always show position updates for debugging
            print(f"📈 Position: {symbol} | Qty: {quantity} | P&L: ₹{pnl:.2f}")
                
        except Exception as e:
            print(f"❌ [DEBUG] Error handling position update: {e}")
    
    def wait_for_order_fill(self, order_id, timeout=30):
        """
        Wait for order to be filled using WebSocket updates.
        
        Args:
            order_id (str): Order ID to wait for
            timeout (int): Maximum seconds to wait
            
        Returns:
            dict: Order status info or None if timeout
        """
        import threading
        
        try:
            # Create event for this order if not exists
            if order_id not in self.order_update_events:
                self.order_update_events[order_id] = threading.Event()
            
            # Wait for update or timeout
            if self.order_update_events[order_id].wait(timeout):
                # Got update - return cached status
                return self.order_status_cache.get(order_id)
            else:
                # Timeout - will fallback to REST in calling code
                if self.verbose:
                    print(f"⚠️ WebSocket timeout for order {order_id[:8]}...")
                return None
                
        except Exception as e:
            if self.verbose:
                print(f"Error waiting for order fill: {e}")
            return None
    
    def get_option_instrument_keys(self, strike, option_type):
        """
        Get instrument keys for CE or PE options at a specific strike using helper function.
        
        Args:
            strike (int): Strike price
            option_type (str): "CE" or "PE"
        
        Returns:
            str: Instrument key
        """
        try:
            # Use the helper function from market_quotes
            instrument_keys = get_nifty_option_instrument_keys(self.nse_data, [strike], option_type)
            if instrument_keys and strike in instrument_keys:
                return instrument_keys[strike]
            else:
                print(f"No {option_type} options found for {self.underlying_symbol} {strike}")
                return None
                
        except Exception as e:
            print(f"Error getting {option_type} instrument key: {e}")
            return None
    
    def get_current_prices(self, ce_instrument_key, pe_instrument_key):
        """
        Get current LTP prices for CE and PE options.
        Uses WebSocket price cache when possible.
        
        Args:
            ce_instrument_key (str): CE instrument key
            pe_instrument_key (str): PE instrument key
            
        Returns:
            tuple: (ce_price, pe_price) or (None, None) if error
        """
        ce_price = None
        pe_price = None
        
        # Ensure we are subscribed
        self._subscribe_to_instruments([ce_instrument_key, pe_instrument_key])
        
        # Give WebSocket a moment to receive first tick (200ms)
        # This prevents immediate fallback to REST API for newly subscribed instruments
        import time
        if ce_instrument_key not in self.price_cache or pe_instrument_key not in self.price_cache:
            time.sleep(0.2)  # 200ms delay for first tick

        # Try to get from cache first (with expiry check)
        now = datetime.now()
        
        if ce_instrument_key in self.price_cache:
            cached = self.price_cache[ce_instrument_key]
            age = (now - cached['time']).total_seconds()
            if age < 30:  # 30-second cache expiry (increased for OTM options with low liquidity)
                ce_price = cached['price']
        
        if pe_instrument_key in self.price_cache:
            cached = self.price_cache[pe_instrument_key]
            age = (now - cached['time']).total_seconds()
            if age < 30:  # 30-second cache expiry (increased for OTM options with low liquidity)
                pe_price = cached['price']
            
        # If any missing, fall back to API
        if ce_price is None or pe_price is None:
            try:
                keys = [ce_instrument_key, pe_instrument_key]
                quotes = get_multiple_ltp_quotes(self.access_token, keys)
                
                if quotes and quotes.get('status') == 'success':
                    data = quotes.get('data', {})
                    if ce_instrument_key in data:
                        ce_price = data[ce_instrument_key].get('last_price')
                        self.price_cache[ce_instrument_key] = {'price': ce_price, 'time': datetime.now()}
                    if pe_instrument_key in data:
                        pe_price = data[pe_instrument_key].get('last_price')
                        self.price_cache[pe_instrument_key] = {'price': pe_price, 'time': datetime.now()}
                else:
                    # API call succeeded but returned error status
                    if self.verbose:
                        print(f"⚠️ API returned non-success status: {quotes}")
            except Exception as e:
                if self.verbose:
                    print(f"Error fetching current prices via API: {e}")
                
        return ce_price, pe_price
    
    def calculate_ratio(self, ce_price, pe_price):
        """
        Calculate the ratio of min(CE, PE) / max(CE, PE).
        
        Args:
            ce_price (float): CE option price
            pe_price (float): PE option price
        
        Returns:
            float: Ratio value
        """
        if ce_price <= 0 or pe_price <= 0:
            return 1.0
        
        min_price = min(ce_price, pe_price)
        max_price = max(ce_price, pe_price)
        
        return min_price / max_price
    
    def get_dynamic_ratio_threshold(self, ce_price, pe_price):
        """
        Get dynamic ratio threshold based on market conditions and expiry day mode
        
        Args:
            ce_price (float): Call option price
            pe_price (float): Put option price
        
        Returns:
            float: Dynamic ratio threshold
        """
        base_threshold = self.ratio_threshold  # 0.8
        
        # Handle edge cases
        if ce_price <= 0 or pe_price <= 0:
            return base_threshold
        
        if self._is_nifty_expiry_day():
            # On NIFTY expiry day, be more lenient due to low premiums
            combined_premium = ce_price + pe_price
            
            if combined_premium < 30:  # Very low premiums
                return 0.3  # Much more lenient for entry
            elif combined_premium < 50:  # Low premiums
                return 0.4  # More lenient for entry
            else:
                return 0.45  # Slightly more lenient for entry
        else:
            # Normal trading day - use base threshold
            return base_threshold
    
    def _get_single_current_price(self, instrument_key):
        """
        Get current price for a single instrument.
        Uses WebSocket price cache.
        """
        # Ensure subscribed
        self._subscribe_to_instruments([instrument_key])
        
        # Try cache (with expiry check)
        if instrument_key in self.price_cache:
            cached = self.price_cache[instrument_key]
            age = (datetime.now() - cached['time']).total_seconds()
            if age < 30:  # 30-second cache expiry
                return cached['price']
            
        try:
            quote = get_ltp_quote(self.access_token, instrument_key)
            if quote and quote.get('status') == 'success':
                data = quote.get('data', {})
                if data:
                    # Upstox V2 LTP API sometimes returns normalized keys
                    key = list(data.keys())[0]
                    price = data[key].get('last_price')
                    # Update cache
                    self.price_cache[instrument_key] = {'price': price, 'time': datetime.now()}
                    return price
            return None
        except Exception as e:
            print(f"Error fetching single price: {e}")
            return None
    
    def is_market_close_time(self):
        """
        Check if current time is market close time (3:15 PM)
        
        Returns:
            bool: True if market close time
        """
        try:
            current_time = datetime.now()
            market_close_time = current_time.replace(hour=15, minute=15, second=0, microsecond=0)
            return current_time >= market_close_time
        except Exception as e:
            print(f"Error checking market close time: {e}")
            return False
    
    def get_current_spot_price(self):
        """
        Get current NIFTY spot price.
        Uses WebSocket price cache.
        
        Returns:
            float: Current spot price or None if error
        """
        # Try cache first (with expiry check)
        if self.nifty_key in self.price_cache:
            cached = self.price_cache[self.nifty_key]
            age = (datetime.now() - cached['time']).total_seconds()
            if age < 30:  # 30-second cache expiry
                return cached.get('price')
            
        try:
            nifty_spot = get_ltp_quote(self.access_token, self.nifty_key)
            if nifty_spot and nifty_spot.get('status') == 'success':
                data = nifty_spot.get('data', {})
                if data:
                    # Flexible key check for index
                    spot_key = list(data.keys())[0]
                    price = data[spot_key].get('last_price')
                    # Update cache
                    self.price_cache[self.nifty_key] = {'price': price, 'time': datetime.now()}
                    return price
            return None
        except Exception as e:
            print(f"Error fetching NIFTY spot price: {e}")
            return None
    
    def get_option_chain_atm(self):
        """
        Get option chain data for ATM strikes
        
        Returns:
            DataFrame: Option chain data or None if error
        """
        try:
            from lib.api.market_data import get_filtered_option_chain
            # Get current expiry date
            expiry = self._get_current_expiry()
            # Use the correct underlying key format
            underlying_key = "NSE_INDEX|Nifty 50"
            return get_filtered_option_chain(self.access_token, underlying_key, expiry)
        except Exception as e:
            print(f"Error getting option chain data: {e}")
            return None
    
    def check_straddle_width(self, strike, dynamic_threshold=None):
        """
        Check if the straddle width is within the threshold and NIFTY is near ATM before entering.
        
        Args:
            strike (int): Strike price to check
            dynamic_threshold (float): Dynamic threshold to use (if None, uses base threshold)
            
        Returns:
            tuple: (is_valid, ce_price, pe_price, width_percentage, nifty_price, nifty_deviation, ratio)
        """
        import uuid
        call_id = str(uuid.uuid4())[:8]  # Unique identifier for this call
        if self.verbose:
            print(f"🔍 [CALL-{call_id}] Starting check_straddle_width for strike {strike}")
        try:
            # Get instrument keys
            ce_instrument_key = self.get_option_instrument_keys(strike, "CE")
            pe_instrument_key = self.get_option_instrument_keys(strike, "PE")
            
            if not ce_instrument_key or not pe_instrument_key:
                if self.verbose:
                    print(f"Failed to get instrument keys for strike {strike}")
                return False, 0, 0, 0, 0, 0, 0
            
            # Get current prices
            ce_price, pe_price = self.get_current_prices(ce_instrument_key, pe_instrument_key)
            
            if ce_price is None or pe_price is None or ce_price <= 0 or pe_price <= 0:
                if self.verbose:
                    print(f"Invalid prices for strike {strike}: CE={ce_price}, PE={pe_price}")
                return False, ce_price or 0, pe_price or 0, 0, 0, 0, 0
            
            # Get current NIFTY index price
            nifty_price = self.get_current_spot_price()
            if nifty_price is None:
                if "429" in str(e) or "Too Many Requests" in str(e):
                    print(f"⚠️  API rate limit hit. Using cached NIFTY price or skipping check.")
                    # Use a reasonable default or skip NIFTY check temporarily
                    nifty_price = strike  # Assume NIFTY is at ATM for this check
                else:
                    print(f"Error fetching NIFTY price: {e}")
                    return False, ce_price, pe_price, 0, 0, 0, 0
            
            # Calculate straddle width percentage
            max_price = max(ce_price, pe_price)
            min_price = min(ce_price, pe_price)
            width_percentage = (max_price - min_price) / max_price
            
            # Calculate NIFTY deviation from ATM strike
            nifty_deviation = abs(nifty_price - strike)
            
            # Use dynamic threshold if provided, otherwise use base threshold
            threshold_to_use = dynamic_threshold if dynamic_threshold is not None else self.straddle_width_threshold
            
            if self.verbose:
                print(f"🔍 [CALL-{call_id}] Straddle width check for strike {strike}:")
                print(f"🔍 [CALL-{call_id}]   CE: ₹{ce_price:.2f}, PE: ₹{pe_price:.2f}")
                print(f"🔍 [CALL-{call_id}]   Width: {width_percentage*100:.1f}% (Threshold: {threshold_to_use*100:.0f}%)")
                print(f"🔍 [CALL-{call_id}]   NIFTY: ₹{nifty_price:.1f}, ATM: {strike}, Deviation: {nifty_deviation:.1f} points (Max: 50)")
            
            # Calculate ratio for entry check
            ratio = self.calculate_ratio(ce_price, pe_price)
            
            # Check all three conditions
            width_valid = width_percentage <= threshold_to_use
            nifty_valid = nifty_deviation <= 50  # Within 50 points of ATM (more reasonable)
            ratio_valid = ratio >= self.ratio_threshold  # Ratio must be >= 0.8 for entry
            
            # Debug output to track all checks
            if self.verbose:
                print(f"🔍 [CALL-{call_id}]   Ratio: {ratio:.3f} (Threshold: {self.ratio_threshold:.1f}) - {'✅ PASS' if ratio_valid else '❌ FAIL'}")
                print(f"🔍 [CALL-{call_id}]   Final Result: Width={width_valid}, NIFTY={nifty_valid}, Ratio={ratio_valid} → {'✅ VALID' if (width_valid and nifty_valid and ratio_valid) else '❌ INVALID'}")
            
            is_valid = width_valid and nifty_valid and ratio_valid
            
            if self.verbose:
                if is_valid:
                    print(f"🔍 [CALL-{call_id}] ✅ All conditions met: Straddle width within threshold, NIFTY near ATM, and ratio >= {self.ratio_threshold:.1f}. Proceeding with entry.")
                else:
                    if not width_valid:
                        print(f"🔍 [CALL-{call_id}] ❌ Straddle width exceeds threshold. Skipping entry.")
                    if not nifty_valid:
                        print(f"🔍 [CALL-{call_id}] ❌ NIFTY too far from ATM ({nifty_deviation:.1f} > 50 points). Skipping entry.")
                    if not ratio_valid:
                        print(f"🔍 [CALL-{call_id}] ❌ Ratio {ratio:.3f} below entry threshold {self.ratio_threshold:.1f}. Skipping entry.")
            
            return is_valid, ce_price, pe_price, width_percentage, nifty_price, nifty_deviation, ratio
            
        except Exception as e:
            print(f"🔍 [CALL-{call_id}] Error checking straddle width: {e}")
            return False, 0, 0, 0, 0, 0, 0
    
    def check_max_deviation(self, new_strike):
        """
        Check if the new strike exceeds maximum deviation from original ATM.
        
        Args:
            new_strike (int): New strike price to check
            
        Returns:
            bool: True if within deviation limit, False if exceeds
        """
        try:
            deviation = abs(new_strike - self.original_atm_strike)
            
            if deviation > self.max_deviation_points:
                print(f"🚨 MAXIMUM DEVIATION EXCEEDED!")
                print(f"   Original ATM: {self.original_atm_strike}")
                print(f"   New Strike: {new_strike}")
                print(f"   Deviation: {deviation} points (Limit: {self.max_deviation_points})")
                print(f"   ❌ Cannot move to this strike - exceeds risk limit")
                return False
            else:
                print(f"✅ Deviation check passed: {deviation} points ≤ {self.max_deviation_points} points")
                return True
                
        except Exception as e:
            print(f"Error checking maximum deviation: {e}")
            return False
    
    def get_oi_optimal_strike(self, strikes_to_analyze=None):
        """
        Get the best strike based on OI analysis
        
        Args:
            strikes_to_analyze (List[int]): Strikes to analyze (default: ATM ± 2)
        
        Returns:
            tuple: (best_strike, best_score, oi_recommendation)
        """
        if not self.enable_oi_analysis or not self.oi_analyzer:
            return self.current_strike, 50, {"error": "OI analysis not enabled"}
        
        try:
            if strikes_to_analyze is None:
                # Analyze strikes around current ATM
                current_atm = self.get_atm_strike()
                strikes_to_analyze = [
                    current_atm - 100, current_atm - 50, current_atm,
                    current_atm + 50, current_atm + 100
                ]
            
            best_strike = self.current_strike
            best_score = 50  # Default neutral score
            best_recommendation = None
            
            if self.verbose:
                print(f"🔍 Analyzing OI for strikes: {strikes_to_analyze}")
            
            for strike in strikes_to_analyze:
                # Get OI recommendation for this strike
                oi_rec = self.get_oi_selling_recommendation(strike)
                if "error" not in oi_rec:
                    score = oi_rec.get('selling_score', 50)
                    if self.verbose:
                        print(f"   Strike {strike}: Score {score:.1f} - {oi_rec.get('recommendation', 'neutral')}")
                    
                    if score > best_score:
                        best_score = score
                        best_strike = strike
                        best_recommendation = oi_rec
            
            if self.verbose:
                print(f"🎯 Best strike based on OI: {best_strike} (Score: {best_score:.1f})")
            return best_strike, best_score, best_recommendation
            
        except Exception as e:
            print(f"Error getting OI optimal strike: {e}")
            return self.current_strike, 50, {"error": str(e)}
    
    def should_enter_based_on_oi(self, strike):
        """
        Determine if we should enter based on OI conditions
        
        Args:
            strike (int): Strike price to analyze
        
        Returns:
            tuple: (should_enter, reason)
        """
        if not self.enable_oi_analysis or not self.oi_analyzer:
            return True, "OI analysis not enabled - using default logic"
        
        try:
            oi_sentiment = self.analyze_oi_sentiment(strike)
            
            if "error" in oi_sentiment:
                return True, "OI analysis failed - proceeding with caution"
            
            # Check if OI conditions are favorable
            sentiment = oi_sentiment.get('strike_sentiment', 'neutral')
            call_activity = oi_sentiment.get('call_oi_activity', '')
            put_activity = oi_sentiment.get('put_oi_activity', '')
            
            # Favorable conditions for option sellers
            favorable_conditions = [
                sentiment == 'bullish_for_sellers',
                call_activity == 'long_unwinding',  # Call buyers exiting (good for call sellers)
                put_activity == 'long_unwinding',   # Put buyers exiting (good for put sellers)
                call_activity == 'short_build',     # Call sellers accumulating (good for call sellers)
                put_activity == 'short_build',      # Put sellers accumulating (good for put sellers)
            ]
            
            if any(favorable_conditions):
                return True, f"OI conditions favorable: {sentiment} (Call: {call_activity}, Put: {put_activity})"
            
            # Check if conditions are very unfavorable
            unfavorable_conditions = [
                sentiment == 'bearish_for_sellers',
                call_activity == 'long_build',      # Call buyers accumulating (bad for call sellers)
                put_activity == 'long_build',       # Put buyers accumulating (bad for put sellers)
                call_activity == 'short_unwinding', # Call sellers exiting (bad for call sellers)
                put_activity == 'short_unwinding',  # Put sellers exiting (bad for put sellers)
            ]
            
            if any(unfavorable_conditions):
                return False, f"OI conditions unfavorable: {sentiment} (Call: {call_activity}, Put: {put_activity})"
            
            return True, f"OI conditions neutral: {sentiment} - proceeding"
            
        except Exception as e:
            return True, f"OI analysis error: {e} - proceeding with caution"
    
    def get_oi_width_threshold(self, strike):
        """
        Get dynamic width threshold based on OI conditions
        
        Args:
            strike (int): Strike price to analyze
        
        Returns:
            float: Dynamic width threshold
        """
        base_threshold = self.straddle_width_threshold  # 20%
        
        if not self.enable_oi_analysis or not self.oi_analyzer:
            return base_threshold
        
        try:
            oi_sentiment = self.analyze_oi_sentiment(strike)
            if "error" in oi_sentiment:
                return base_threshold
            
            sentiment = oi_sentiment.get('strike_sentiment', 'neutral')
            
            # Adjust threshold based on OI sentiment
            if sentiment == 'bullish_for_sellers':
                # More lenient for very favorable OI conditions (take advantage of good conditions)
                dynamic_threshold = base_threshold * 1.4  # 35% instead of 25% (25% * 1.4 = 35%)
                print(f"📊 OI very favorable - using relaxed width threshold: {dynamic_threshold*100:.0f}% (take advantage)")
                return dynamic_threshold
            elif sentiment == 'bearish_for_sellers':
                # More strict for unfavorable OI conditions (be cautious)
                dynamic_threshold = base_threshold * 0.8  # 20% instead of 25% (25% * 0.8 = 20%)
                print(f"📊 OI unfavorable - using strict width threshold: {dynamic_threshold*100:.0f}% (be cautious)")
                return dynamic_threshold
            
            return base_threshold
            
        except Exception as e:
            print(f"Error getting dynamic width threshold: {e}")
            return base_threshold
    
    def wait_for_valid_straddle_width(self, strike, max_wait_minutes=30):
        """
        Check straddle width ONCE. If valid, return True.
        If invalid, return False (non-blocking).
        
        Args:
            strike (int): Strike price to monitor
            max_wait_minutes (int): Unused in non-blocking version (kept for compatibility)
            
        Returns:
            bool: True if conditions are met immediately
        """
        try:
            # Check OI conditions first (single strike)
            should_enter, oi_reason = self.should_enter_based_on_oi(strike)
            
            # Check cumulative OI conditions
            cumulative_should_enter, cumulative_reason, cumulative_score = self.get_cumulative_sentiment_for_entry()
            
            # Combine both analyses
            if not should_enter and not cumulative_should_enter:
                if self.verbose:
                    print(f"❌ OI conditions not favorable. {oi_reason}")
                return False
            
            # Get dynamic width threshold based on OI
            dynamic_threshold = self.get_oi_width_threshold(strike)
            
            # Check conditions once
            is_valid, ce_price, pe_price, width_percentage, nifty_price, nifty_deviation, ratio = self.check_straddle_width(strike, dynamic_threshold)
            
            if is_valid:
                print(f"✅ Valid conditions found! Proceeding with entry.")
                return True
            
            return False
            
        except Exception as e:
            print(f"Error checking valid straddle width: {e}")
            return False
    
    def display_current_positions(self):

        """
        Display current positions with strikes, prices, and running profit.
        Shows straddle, strangle, and safe OTM positions.
        """
        try:
            timestamp = datetime.now().strftime('%H:%M:%S')
            
            # Check if we have any active positions
            has_straddle = bool(self.active_positions)
            has_strangle = bool(self.strangle_positions)
            has_safe_otm = bool(self.safe_otm_positions)
            
            if not has_straddle and not has_strangle and not has_safe_otm:
                if self.verbose:
                    print(f"[{timestamp}] No active positions")
                return
            
            # === NORMAL MODE: Single-line compact status ===
            if not self.verbose:
                nifty_price = self.get_current_spot_price() or 0
                pnl_emoji = "🟢" if self.total_profit >= 0 else "🔴"
                
                status_parts = []
                if has_straddle:
                    status_parts.append(f"STR:{len(self.active_positions)}")
                if has_strangle:
                    status_parts.append(f"STG:{len(self.strangle_positions)}")
                if has_safe_otm:
                    status_parts.append(f"OTM:{len(self.safe_otm_positions)}")
                
                positions_str = " ".join(status_parts)
                target = self.current_profit_target if self.dynamic_risk_enabled else self.profit_target
                
                print(f"[{timestamp}] {pnl_emoji} P&L:₹{self.total_profit:.0f}/₹{target:.0f} | {positions_str} | NIFTY:₹{nifty_price:.1f}")
                
                # Show critical alerts even in normal mode
                if self.total_profit < -self.max_loss_limit * 0.8:
                    print(f"[{timestamp}] ⚠️ ALERT: Approaching max loss limit!")
                
                return
            
            # === DEBUG MODE: Detailed multi-line display (below) ===
            
            # Find current active CE and PE strikes
            ce_strike = None
            ce_price = 0
            pe_strike = None
            pe_price = 0
            
            # Find active CE position
            for strike, position in self.active_positions.items():
                if position.get('ce_order_id') and position.get('ce_instrument_key'):
                    ce_strike = strike
                    # Get CE price
                    ce_price = self._get_single_current_price(position['ce_instrument_key'])
                    break
            
            # Find active PE position
            for strike, position in self.active_positions.items():
                if position.get('pe_order_id') and position.get('pe_instrument_key'):
                    pe_strike = strike
                    # Get PE price
                    pe_price = self._get_single_current_price(position['pe_instrument_key'])
                    break
            
            # Only display if we have both CE and PE active
            if ce_strike is not None and pe_strike is not None and ce_price is not None and pe_price is not None and ce_price > 0 and pe_price > 0:
                # Calculate ratio and combined price
                ratio = self.calculate_ratio(ce_price, pe_price)
                combined_price = ce_price + pe_price
                
                # Calculate combined entry premium based on current active positions
                ce_entry_price = 0
                pe_entry_price = 0
                
                # Get CE entry price from current active CE position
                if ce_strike in self.entry_prices:
                    ce_entry_price = self.entry_prices[ce_strike]['ce_entry_price']
                
                # Get PE entry price from current active PE position
                if pe_strike in self.entry_prices:
                    pe_entry_price = self.entry_prices[pe_strike]['pe_entry_price']
                
                # Calculate combined entry premium
                combined_entry_premium = ce_entry_price + pe_entry_price if ce_entry_price > 0 and pe_entry_price > 0 else 0
                
                # Get NIFTY index price
                nifty_price = self.get_current_spot_price()
                
                # Format display
                ce_display = f"₹{ce_price:.2f}"
                pe_display = f"₹{pe_price:.2f}"
                entry_premium_display = f"₹{combined_entry_premium:.2f}" if combined_entry_premium > 0 else "--"
                combined_display = f"₹{combined_price:.2f}"
                ratio_display = f"{ratio:.3f}"
                realized_display = f"₹{self.realized_pnl:.0f}"
                unrealized_display = f"₹{self.unrealized_pnl:.0f}"
                total_display = f"₹{self.total_profit:.0f}"
                # Show dynamic or static profit target
                if self.dynamic_risk_enabled:
                    target_display = f"₹{self.current_profit_target:.0f}(D)"
                else:
                    target_display = f"₹{self.profit_target:.0f}"
                nifty_display = f"₹{nifty_price:.1f}" if nifty_price is not None and nifty_price > 0 else "--"
                
                # Check for scaling information
                scaling_info = ""
                if strike in self.scaled_positions:
                    scaling_level = self.scaled_positions[strike]['scaling_level']
                    if scaling_level > 0:
                        scaling_info = f" S{scaling_level}x"  # S1x, S2x, etc.
                
                # Add trailing stop information
                trailing_info = ""
                if self.trailing_stop_enabled and self.trailing_stop_level > 0:
                    trailing_info = f" TS:₹{self.trailing_stop_level:.0f}"
                
                # Clean single line output: Time, CE Strike/Price, PE Strike/Price, Ratio, P&L, Target, NIFTY
                print(f"[{timestamp}] {ce_strike}₹{ce_price:.1f} {pe_strike}₹{pe_price:.1f} R:{ratio:.2f} P&L:₹{self.total_profit:.0f} T:₹{self.current_profit_target if self.dynamic_risk_enabled else self.profit_target:.0f} N:₹{nifty_price:.0f}")
                
                # Show Greeks if available (on separate line for readability)
                if ce_strike in self.active_positions:
                    ce_key = self.active_positions[ce_strike].get('ce_instrument_key')
                    pe_key = self.active_positions[pe_strike].get('pe_instrument_key')
                    
                    ce_greeks = self.get_greeks_display(ce_key) if ce_key else ""
                    pe_greeks = self.get_greeks_display(pe_key) if pe_key else ""
                    
                    if ce_greeks or pe_greeks:
                        print(f"   📊 Greeks: CE[{ce_greeks}] PE[{pe_greeks}]")
                
                # Show alert if ratio is below exit threshold (0.5) for active positions
                exit_threshold = 0.5
                if ratio < exit_threshold:
                    print(f"⚠️  ALERT: Ratio {ratio:.3f} below exit threshold {exit_threshold:.2f}")
            else:
                # Show no active positions if we don't have both CE and PE
                if has_straddle:
                    print(f"[{timestamp}] No active straddle positions")
                    
                    # Show entry alert if ratio is below entry threshold (0.8) when no positions
                    # Get current ATM prices for entry alert
                    try:
                        current_atm = self.get_atm_strike()
                        if current_atm:
                            ce_instrument_key = self.get_option_instrument_keys(current_atm, "CE")
                            pe_instrument_key = self.get_option_instrument_keys(current_atm, "PE")
                            if ce_instrument_key and pe_instrument_key:
                                ce_price, pe_price = self.get_current_prices(ce_instrument_key, pe_instrument_key)
                                if ce_price is not None and pe_price is not None and ce_price > 0 and pe_price > 0:
                                    ratio = self.calculate_ratio(ce_price, pe_price)
                                    entry_threshold = 0.8
                                    if ratio < entry_threshold:
                                        print(f"⚠️  ALERT: Ratio {ratio:.3f} below entry threshold {entry_threshold:.2f}")
                    except Exception as e:
                        pass  # Silently ignore errors in entry alert
            
            # Display strangle positions
            if has_strangle:
                self._display_strangle_positions(timestamp)
            
            # Display safe OTM positions
            if has_safe_otm:
                self._display_safe_otm_positions(timestamp)
            
            # Show loss warning if approaching max loss
            if self.total_profit < 0:
                loss_percentage = (abs(self.total_profit) / self.max_loss_limit) * 100
                if loss_percentage >= 80:
                    print(f"🚨 LOSS WARNING: ₹{abs(self.total_profit):.0f} loss ({loss_percentage:.0f}% of limit)")
                elif loss_percentage >= 50:
                    print(f"⚠️  Loss Alert: ₹{abs(self.total_profit):.0f} loss ({loss_percentage:.0f}% of limit)")
            
            # Show deviation status
            self.show_deviation_status()
            
        except Exception as e:
            print(f"Error displaying positions: {e}")
    
    def _display_strangle_positions(self, timestamp):
        """
        Display strangle positions in monitoring format
        
        Args:
            timestamp (str): Current timestamp for display
        """
        try:
            for strangle_id, position in self.strangle_positions.items():
                ce_strike = position['ce_strike']
                pe_strike = position['pe_strike']
                ce_instrument_key = position['ce_instrument_key']
                pe_instrument_key = position['pe_instrument_key']
                ce_entry_price = position['ce_entry_price']
                pe_entry_price = position['pe_entry_price']
                combined_entry_premium = position['combined_entry_premium']
                
                # Get current prices
                ce_current_price, pe_current_price = self.get_current_prices(ce_instrument_key, pe_instrument_key)
                
                if ce_current_price is None or pe_current_price is None:
                    print(f"[{timestamp}] STRANGLE {strangle_id}: Price data unavailable")
                    continue
                
                # Calculate current P&L
                ce_pnl = (ce_entry_price - ce_current_price) * self.lot_size * self.market_lot
                pe_pnl = (pe_entry_price - pe_current_price) * self.lot_size * self.market_lot
                combined_pnl = ce_pnl + pe_pnl
                
                # Calculate current premium
                current_combined_premium = ce_current_price + pe_current_price
                
                # Format display
                ce_display = f"₹{ce_current_price:.2f}"
                pe_display = f"₹{pe_current_price:.2f}"
                entry_premium_display = f"₹{combined_entry_premium:.2f}"
                current_premium_display = f"₹{current_combined_premium:.2f}"
                pnl_display = f"₹{combined_pnl:.0f}"
                
                # Get NIFTY price for context
                nifty_price = self.get_current_spot_price()
                
                nifty_display = f"₹{nifty_price:.1f}" if nifty_price is not None and nifty_price > 0 else "--"
                
                # Display strangle position: ID, CE strike, CE price, PE strike, PE price, Entry premium, Current premium, P&L, NIFTY
                print(f"[{timestamp}] STRANGLE {strangle_id}: {ce_strike} {ce_display} {pe_strike} {pe_display} {entry_premium_display} {current_premium_display} P&L:{pnl_display} {nifty_display}")
                
                # Show profit/loss alerts
                if combined_pnl >= 1000:  # 50% of entry premium (assuming ~2000 entry)
                    print(f"🎯 STRANGLE {strangle_id}: Profit target reached! P&L: ₹{combined_pnl:.0f}")
                elif combined_pnl <= -3000:  # 150% of entry premium
                    print(f"🚨 STRANGLE {strangle_id}: Stop loss triggered! P&L: ₹{combined_pnl:.0f}")
                
        except Exception as e:
            print(f"Error displaying strangle positions: {e}")
    
    def _display_safe_otm_positions(self, timestamp):
        """
        Display safe OTM positions in monitoring format
        
        Args:
            timestamp (str): Current timestamp for display
        """
        try:
            for position_id, position in self.safe_otm_positions.items():
                strike = position['strike']
                option_type = position['option_type']
                instrument_key = position['instrument_key']
                entry_price = position['entry_price']
                quantity = position['quantity']
                selling_score = position['selling_score']
                
                # Get current price
                current_price = self._get_single_current_price(instrument_key)
                
                if current_price is None:
                    print(f"[{timestamp}] SAFE_OTM {position_id}: Price data unavailable")
                    continue
                
                # Calculate current P&L
                pnl = (entry_price - current_price) * quantity
                
                # Format display
                entry_display = f"₹{entry_price:.2f}"
                current_display = f"₹{current_price:.2f}"
                pnl_display = f"₹{pnl:.0f}"
                score_display = f"{selling_score:.0f}%"
                
                # Get NIFTY price for context
                nifty_price = self.get_current_spot_price()
                
                nifty_display = f"₹{nifty_price:.1f}" if nifty_price is not None and nifty_price > 0 else "--"
                
                # Display safe OTM position: ID, Strike, Type, Entry, Current, P&L, Score, NIFTY
                print(f"[{timestamp}] SAFE_OTM {position_id}: {strike} {option_type} {entry_display} {current_display} P&L:{pnl_display} Score:{score_display} {nifty_display}")
                
                # Show profit/loss alerts
                if pnl >= position['profit_target']:
                    print(f"🎯 SAFE_OTM {position_id}: Profit target reached! P&L: ₹{pnl:.0f}")
                elif pnl <= position['stop_loss']:
                    print(f"🚨 SAFE_OTM {position_id}: Stop loss triggered! P&L: ₹{pnl:.0f}")
                
        except Exception as e:
            print(f"Error displaying safe OTM positions: {e}")
    
    def show_deviation_status(self):
        """
        Show current deviation from original ATM strike.
        """
        try:
            if not self.active_positions:
                return
            
            # Calculate maximum deviation from original ATM
            max_deviation = 0
            for strike in self.active_positions.keys():
                deviation = abs(strike - self.original_atm_strike)
                max_deviation = max(max_deviation, deviation)
            
            # Show deviation status
            if max_deviation > 0:
                deviation_percentage = (max_deviation / self.max_deviation_points) * 100
                if deviation_percentage >= 80:
                    print(f"🚨 DEVIATION WARNING: {max_deviation} points from ATM ({deviation_percentage:.0f}% of limit)")
                elif deviation_percentage >= 50:
                    print(f"⚠️  Deviation: {max_deviation} points from ATM ({deviation_percentage:.0f}% of limit)")
                else:
                    print(f"📊 Deviation: {max_deviation} points from ATM ({deviation_percentage:.0f}% of limit)")
            
        except Exception as e:
            print(f"Error showing deviation status: {e}")
    
    def analyze_oi_sentiment(self, strike=None):
        """
        Analyze OI sentiment for current strike or specified strike
        
        Args:
            strike (int): Strike price to analyze (default: current strike)
        
        Returns:
            Dict: OI sentiment analysis
        """
        if not self.enable_oi_analysis or not self.oi_analyzer:
            return {"error": "OI analysis not enabled"}
        
        try:
            if strike is None:
                strike = self.current_strike
            
            if strike is None:
                return {"error": "No strike price available for analysis"}
            
            # Check if option chain API is available
            if not self.oi_analyzer.check_option_chain_availability():
                print("📊 Using fallback OI analysis - option chain API not available")
                return self.oi_analyzer.fallback_analyzer.get_simplified_selling_recommendation(strike)
            
            # Get option chain data
            from lib.api.market_data import get_option_chain_atm
            expiry = self._get_current_expiry()
            option_chain_df = get_option_chain_atm(
                self.access_token, "NSE_INDEX|Nifty 50", expiry,
                strikes_above=5, strikes_below=5
            )
            
            if option_chain_df.empty:
                print("📊 No option chain data - using fallback analysis")
                return self.oi_analyzer.fallback_analyzer.get_simplified_selling_recommendation(strike)
            
            # Analyze sentiment
            sentiment = self.oi_analyzer.analyze_strike_sentiment(option_chain_df, strike)
            
            # Store in history
            if "error" not in sentiment:
                self.oi_sentiment_history.append(sentiment)
                # Keep only last 50 entries
                if len(self.oi_sentiment_history) > 50:
                    self.oi_sentiment_history = self.oi_sentiment_history[-50:]
            
            return sentiment
            
        except Exception as e:
            return {"error": f"Error analyzing OI sentiment: {str(e)}"}
    
    def get_oi_selling_recommendation(self, strike=None):
        """
        Get OI-based selling recommendation for a strike
        
        Args:
            strike (int): Strike price to analyze (default: current strike)
        
        Returns:
            Dict: Selling recommendation based on OI analysis
        """
        if not self.enable_oi_analysis or not self.oi_analyzer:
            return {"error": "OI analysis not enabled"}
        
        try:
            if strike is None:
                strike = self.current_strike
            
            if strike is None:
                return {"error": "No strike price available for analysis"}
            
            # Get option chain data
            from lib.api.market_data import get_option_chain_atm
            expiry = self._get_current_expiry()
            option_chain_df = get_option_chain_atm(
                self.access_token, "NSE_INDEX|Nifty 50", expiry,
                strikes_above=5, strikes_below=5
            )
            
            if option_chain_df.empty:
                return {"error": "No option chain data available"}
            
            # Get optimal selling strikes
            spot_price = option_chain_df['underlying_spot'].iloc[0]
            optimal_strikes = self.oi_analyzer.get_optimal_selling_strikes(
                option_chain_df, spot_price, num_strikes=5
            )
            
            # Find recommendation for the specified strike
            for strike_data in optimal_strikes:
                if strike_data.get('strike_price') == strike:
                    return {
                        "strike": strike,
                        "recommendation": self._get_oi_recommendation(strike_data),
                        "selling_score": strike_data.get('selling_score', 0),
                        "sentiment": strike_data.get('strike_sentiment', 'neutral'),
                        "reasoning": self._get_oi_reasoning(strike_data)
                    }
            
            return {"error": f"No recommendation found for strike {strike}"}
            
        except Exception as e:
            return {"error": f"Error getting OI selling recommendation: {str(e)}"}
    
    def _get_oi_recommendation(self, strike_data):
        """Get recommendation based on selling score"""
        score = strike_data.get('selling_score', 50)
        if score >= 70:
            return "strong_sell"
        elif score >= 60:
            return "sell"
        elif score >= 50:
            return "neutral"
        elif score >= 40:
            return "avoid"
        else:
            return "strong_avoid"
    
    def get_greeks_display(self, instrument_key):
        """
        Get formatted Greeks display for an instrument.
        
        Args:
            instrument_key (str): Instrument key
            
        Returns:
            str: Formatted Greeks string or empty if not available
        """
        try:
            greeks = self.detailed_market_cache.get(instrument_key, {}).get('greeks', {})
            if greeks:
                delta = greeks.get('delta', 0)
                theta = greeks.get('theta', 0)
                gamma = greeks.get('gamma', 0)
                vega = greeks.get('vega', 0)
                iv = self.detailed_market_cache.get(instrument_key, {}).get('iv', greeks.get('iv', 0))
                
                return f"Δ:{delta:.3f} Θ:{theta:.2f} Γ:{gamma:.4f} V:{vega:.2f} IV:{iv:.2%}" if iv else f"Δ:{delta:.3f} Θ:{theta:.2f} Γ:{gamma:.4f} V:{vega:.2f}"
            return ""
        except:
            return ""
    
    def _get_oi_reasoning(self, strike_data):
        """Get reasoning for OI recommendation"""
        reasons = []
        
        sentiment = strike_data.get('strike_sentiment', 'neutral')
        if sentiment == "bullish_for_sellers":
            reasons.append("Bullish sentiment for option sellers")
        elif sentiment == "bearish_for_sellers":
            reasons.append("Bearish sentiment for option sellers")
        
        call_activity = strike_data.get('call_oi_activity', '')
        put_activity = strike_data.get('put_oi_activity', '')
        
        if call_activity == "long_unwinding":
            reasons.append("Call buyers exiting (favorable for call sellers)")
        elif call_activity == "long_build":
            reasons.append("Call buyers accumulating (unfavorable for call sellers)")
        
        if put_activity == "long_build":
            reasons.append("Put buyers accumulating (favorable for put sellers)")
        elif put_activity == "long_unwinding":
            reasons.append("Put buyers exiting (unfavorable for put sellers)")
        
        return "; ".join(reasons) if reasons else "Neutral OI conditions"
    
    def start_oi_monitoring(self, strikes_to_monitor=None):
        """
        Start OI monitoring for specified strikes
        
        Args:
            strikes_to_monitor (List[int]): Strikes to monitor (default: current strike ± 2)
        
        Returns:
            bool: True if monitoring started successfully
        """
        if not self.enable_oi_analysis or not self.oi_monitor:
            print("❌ OI analysis not enabled")
            return False
        
        try:
            if strikes_to_monitor is None:
                # Default: monitor current strike ± 2 strikes
                if self.current_strike:
                    strikes_to_monitor = [
                        self.current_strike - 100,
                        self.current_strike - 50,
                        self.current_strike,
                        self.current_strike + 50,
                        self.current_strike + 100
                    ]
                else:
                    print("❌ No current strike available for monitoring")
                    return False
            
            return self.oi_monitor.start_monitoring(strikes_to_monitor, monitoring_interval=30)
            
        except Exception as e:
            print(f"❌ Error starting OI monitoring: {e}")
            return False
    
    def get_oi_monitoring_update(self):
        """
        Get current OI monitoring update
        
        Returns:
            Dict: Current OI monitoring data
        """
        if not self.enable_oi_analysis or not self.oi_monitor:
            return {"error": "OI monitoring not enabled"}
        
        try:
            # Get current snapshot
            snapshot = self.oi_monitor.get_current_oi_snapshot()
            
            # Check for alerts
            alerts = self.oi_monitor.check_oi_alerts(snapshot)
            
            # Get recommendations
            recommendations = self.oi_monitor.get_selling_recommendations(snapshot)
            
            # Store alerts
            if alerts:
                self.oi_alerts.extend(alerts)
                # Keep only last 20 alerts
                if len(self.oi_alerts) > 20:
                    self.oi_alerts = self.oi_alerts[-20:]
            
            return {
                "snapshot": snapshot,
                "alerts": alerts,
                "recommendations": recommendations,
                "timestamp": datetime.now()
            }
            
        except Exception as e:
            return {"error": f"Error getting OI monitoring update: {str(e)}"}
    
    def get_cumulative_oi_analysis(self):
        """
        Get comprehensive cumulative OI analysis
        
        Returns:
            Dict: Cumulative OI analysis data
        """
        if not self.enable_oi_analysis or not self.cumulative_oi_analyzer:
            return {"error": "Cumulative OI analysis not enabled"}
        
        try:
            # Get cumulative OI data
            cumulative_data = self.cumulative_oi_analyzer.calculate_cumulative_oi()
            
            if "error" in cumulative_data:
                return cumulative_data
            
            # Get overall sentiment
            sentiment_data = self.cumulative_oi_analyzer.get_overall_sentiment(cumulative_data)
            
            # Get trend analysis
            trend_data = self.cumulative_oi_analyzer.analyze_oi_trends(cumulative_data)
            
            # Store in history
            analysis_result = {
                "cumulative_data": cumulative_data,
                "sentiment_data": sentiment_data,
                "trend_data": trend_data,
                "timestamp": datetime.now()
            }
            
            self.cumulative_oi_history.append(analysis_result)
            # Keep only last 50 entries
            if len(self.cumulative_oi_history) > 50:
                self.cumulative_oi_history = self.cumulative_oi_history[-50:]
            
            return analysis_result
            
        except Exception as e:
            return {"error": f"Error getting cumulative OI analysis: {str(e)}"}
    
    def get_cumulative_sentiment_for_entry(self):
        """
        Get cumulative sentiment specifically for entry decisions
        
        Returns:
            tuple: (should_enter, reason, sentiment_score)
        """
        if not self.enable_oi_analysis or not self.cumulative_oi_analyzer:
            return True, "Cumulative OI analysis not enabled", 50
        
        try:
            # Get cumulative analysis
            analysis = self.get_cumulative_oi_analysis()
            
            if "error" in analysis:
                return True, f"Cumulative OI analysis failed: {analysis['error']}", 50
            
            sentiment_data = analysis['sentiment_data']
            cumulative_data = analysis['cumulative_data']
            
            overall_sentiment = sentiment_data.get('overall_sentiment', 'neutral')
            sentiment_score = sentiment_data.get('sentiment_score', 50)
            sentiment_strength = sentiment_data.get('sentiment_strength', 'balanced')
            
            # Determine entry decision based on cumulative sentiment
            if overall_sentiment == 'bullish_for_sellers' and sentiment_score > 65:
                return True, f"Cumulative OI very favorable: {overall_sentiment} ({sentiment_strength})", sentiment_score
            elif overall_sentiment == 'bearish_for_sellers' and sentiment_score < 35:
                return False, f"Cumulative OI unfavorable: {overall_sentiment} ({sentiment_strength})", sentiment_score
            elif overall_sentiment == 'neutral' and 40 <= sentiment_score <= 60:
                return True, f"Cumulative OI neutral: {overall_sentiment} ({sentiment_strength})", sentiment_score
            else:
                return True, f"Cumulative OI mixed signals: {overall_sentiment} (Score: {sentiment_score})", sentiment_score
            
        except Exception as e:
            return True, f"Cumulative OI analysis error: {e}", 50
    
    def get_strangle_analysis(self):
        """
        Get OI-guided strangle analysis
        
        Returns:
            Dict: Strangle analysis data
        """
        if not self.enable_oi_analysis or not self.oi_strangle_analyzer:
            return {"error": "OI strangle analysis not enabled"}
        
        try:
            # Get strangle analysis
            strangle_analysis = self.oi_strangle_analyzer.analyze_strikes_for_strangle()
            
            if "error" in strangle_analysis:
                return strangle_analysis
            
            # Store in history
            self.strangle_history.append(strangle_analysis)
            # Keep only last 20 entries
            if len(self.strangle_history) > 20:
                self.strangle_history = self.strangle_history[-20:]
            
            return strangle_analysis
            
        except Exception as e:
            return {"error": f"Error getting strangle analysis: {str(e)}"}
    
    def should_enter_strangle(self, strangle_analysis: Dict = None):
        """
        Determine if we should enter a strangle based on OI analysis
        
        Args:
            strangle_analysis (Dict): Strangle analysis data (optional)
        
        Returns:
            tuple: (should_enter, reason, confidence)
        """
        if not self.enable_oi_analysis or not self.oi_strangle_analyzer:
            return False, "OI strangle analysis not enabled", 0
        
        try:
            if strangle_analysis is None:
                strangle_analysis = self.get_strangle_analysis()
            
            if "error" in strangle_analysis:
                return False, f"Strangle analysis failed: {strangle_analysis['error']}", 0
            
            recommendation = strangle_analysis['recommendation']
            strangle_metrics = strangle_analysis['strangle_analysis']
            
            # Check if we already have a strangle position
            if self.strangle_positions:
                return False, "Already have active strangle position", 0
            
            # Determine entry decision
            if recommendation['recommendation'] == "strong_strangle":
                return True, f"Strong strangle opportunity: {recommendation['reasoning']}", 90
            elif recommendation['recommendation'] == "strangle":
                return True, f"Good strangle opportunity: {recommendation['reasoning']}", 70
            elif recommendation['recommendation'] == "weak_strangle":
                return True, f"Weak strangle opportunity: {recommendation['reasoning']}", 50
            else:
                return False, f"Poor strangle conditions: {recommendation['reasoning']}", 20
            
        except Exception as e:
            return False, f"Strangle analysis error: {e}", 0
    
    def place_oi_guided_strangle(self, strangle_analysis: Dict = None):
        """
        Place OI-guided strangle based on analysis
        
        Args:
            strangle_analysis (Dict): Strangle analysis data (optional)
        
        Returns:
            bool: True if strangle placed successfully
        """
        if not self.enable_oi_analysis or not self.oi_strangle_analyzer:
            print("❌ OI strangle analysis not enabled")
            return False
        
        try:
            if strangle_analysis is None:
                strangle_analysis = self.get_strangle_analysis()
            
            if "error" in strangle_analysis:
                print(f"❌ Strangle analysis error: {strangle_analysis['error']}")
                return False
            
            # Get optimal strikes
            ce_strike_data = strangle_analysis['optimal_ce_strike']
            pe_strike_data = strangle_analysis['optimal_pe_strike']
            
            ce_strike = ce_strike_data['strike']
            pe_strike = pe_strike_data['strike']
            
            print(f"🎯 Placing OI-Guided Strangle:")
            print(f"   CE Strike: {ce_strike} (Score: {ce_strike_data['call_selling_score']:.1f})")
            print(f"   PE Strike: {pe_strike} (Score: {pe_strike_data['put_selling_score']:.1f})")
            
            # Get instrument keys
            ce_instrument_key = self.get_option_instrument_keys(ce_strike, "CE")
            pe_instrument_key = self.get_option_instrument_keys(pe_strike, "PE")
            
            if not ce_instrument_key or not pe_instrument_key:
                print(f"❌ Failed to get instrument keys for strangle")
                return False
            
            # Place CE order
            ce_order = place_order(
                access_token=self.access_token,
                instrument_token=ce_instrument_key,
                quantity=self.lot_size * self.market_lot,  # NIFTY lot size is 75
                transaction_type="SELL",
                order_type="MARKET",
                price=0,  # Required for market orders
                product="I",  # Intraday for options
                validity="DAY",
                tag=f"Strangle_CE_{ce_strike}"
            )
            
            # Place PE order
            pe_order = place_order(
                access_token=self.access_token,
                instrument_token=pe_instrument_key,
                quantity=self.lot_size * self.market_lot,  # NIFTY lot size is 75
                transaction_type="SELL",
                order_type="MARKET",
                price=0,  # Required for market orders
                product="I",  # Intraday for options
                validity="DAY",
                tag=f"Strangle_PE_{pe_strike}"
            )
            
            if ce_order and pe_order:
                ce_order_id = ce_order.get("data", {}).get("order_ids", [None])[0]
                pe_order_id = pe_order.get("data", {}).get("order_ids", [None])[0]
                
                # Get current prices for entry tracking
                ce_price, pe_price = self.get_current_prices(ce_instrument_key, pe_instrument_key)
                
                if ce_price is None or pe_price is None:
                    print(f"❌ Failed to get current prices for strangle entry tracking")
                    return False
                
                # Track strangle position
                strangle_id = f"{ce_strike}_{pe_strike}"
                self.strangle_positions[strangle_id] = {
                    'ce_strike': ce_strike,
                    'pe_strike': pe_strike,
                    'ce_order_id': ce_order_id,
                    'pe_order_id': pe_order_id,
                    'ce_instrument_key': ce_instrument_key,
                    'pe_instrument_key': pe_instrument_key,
                    'ce_entry_price': ce_price,
                    'pe_entry_price': pe_price,
                    'combined_entry_premium': ce_price + pe_price,
                    'timestamp': datetime.now(),
                    'strangle_analysis': strangle_analysis
                }
                
                print(f"✅ OI-Guided Strangle placed successfully!")
                print(f"   CE Order ID: {ce_order_id}")
                print(f"   PE Order ID: {pe_order_id}")
                print(f"   Combined Premium: ₹{ce_price + pe_price:.2f}")
                
                # Log the trade
                self.trades_log.append({
                    'timestamp': datetime.now(),
                    'action': 'OI_STRANGLE',
                    'ce_strike': ce_strike,
                    'pe_strike': pe_strike,
                    'ce_order_id': ce_order_id,
                    'pe_order_id': pe_order_id,
                    'combined_premium': ce_price + pe_price
                })
                
                return True
            else:
                print("❌ Failed to place strangle orders")
                return False
                
        except Exception as e:
            print(f"❌ Error placing OI-guided strangle: {e}")
            return False
    
    def manage_strangle_positions(self):
        """
        Manage OI-guided strangle positions
        """
        if not self.strangle_positions:
            return
        
        try:
            for strangle_id, position in list(self.strangle_positions.items()):
                ce_strike = position['ce_strike']
                pe_strike = position['pe_strike']
                ce_instrument_key = position['ce_instrument_key']
                pe_instrument_key = position['pe_instrument_key']
                ce_entry_price = position['ce_entry_price']
                pe_entry_price = position['pe_entry_price']
                combined_entry_premium = position['combined_entry_premium']
                
                # Get current prices
                ce_current_price, pe_current_price = self.get_current_prices(ce_instrument_key, pe_instrument_key)
                
                if ce_current_price is None or pe_current_price is None:
                    # Silently skip if prices unavailable (will retry next iteration)
                    continue
                
                # Calculate current P&L
                ce_pnl = (ce_entry_price - ce_current_price) * self.lot_size * self.market_lot
                pe_pnl = (pe_entry_price - pe_current_price) * self.lot_size * self.market_lot
                combined_pnl = ce_pnl + pe_pnl
                
                # Calculate current premium
                current_combined_premium = ce_current_price + pe_current_price
                premium_decay = combined_entry_premium - current_combined_premium
                
                if self.verbose:
                    print(f"🎯 Strangle {strangle_id}: CE {ce_strike} + PE {pe_strike}")
                    print(f"   Entry Premium: ₹{combined_entry_premium:.2f}")
                    print(f"   Current Premium: ₹{current_combined_premium:.2f}")
                    print(f"   Premium Decay: ₹{premium_decay:.2f}")
                    print(f"   Combined P&L: ₹{combined_pnl:.2f}")
                
                # Check exit conditions
                should_exit = False
                exit_reason = ""
                
                # Profit target (50% of entry premium)
                profit_target = combined_entry_premium * 0.5
                if premium_decay >= profit_target:
                    should_exit = True
                    exit_reason = f"Profit target reached (₹{profit_target:.2f})"
                
                # Stop loss (150% of entry premium)
                stop_loss = combined_entry_premium * 1.5
                if premium_decay <= -stop_loss:
                    should_exit = True
                    exit_reason = f"Stop loss hit (₹{stop_loss:.2f})"
                
                # Time-based exit (close to market close)
                current_time = datetime.now()
                if current_time.hour >= 15 and current_time.minute >= 10:
                    should_exit = True
                    exit_reason = "Market close approaching"
                
                if should_exit:
                    print(f"🚨 Exiting strangle {strangle_id}: {exit_reason}")
                    if self.exit_strangle_position(strangle_id, exit_reason):
                        print(f"✅ Strangle {strangle_id} exited successfully")
                    else:
                        print(f"❌ Failed to exit strangle {strangle_id}")
                
        except Exception as e:
            print(f"❌ Error managing strangle positions: {e}")
    
    def should_scale_position(self, strike: int) -> Tuple[bool, str, float]:
        """
        Determine if a position should be scaled up based on favorable conditions
        
        Args:
            strike (int): Strike price to analyze
            
        Returns:
            tuple: (should_scale, reason, confidence)
        """
        if not self.position_scaling_enabled or not self.enable_oi_analysis:
            return False, "Position scaling disabled", 0
        
        try:
            # Check if position exists and is profitable
            if strike not in self.active_positions:
                return False, "No active position at this strike", 0
            
            # Get current prices and calculate profit
            ce_instrument_key = self.get_option_instrument_keys(strike, "CE")
            pe_instrument_key = self.get_option_instrument_keys(strike, "PE")
            
            if not ce_instrument_key or not pe_instrument_key:
                return False, "Invalid instrument keys", 0
            
            ce_current_price, pe_current_price = self.get_current_prices(ce_instrument_key, pe_instrument_key)
            if ce_current_price is None or pe_current_price is None:
                return False, "Unable to get current prices", 0
            
            # Calculate current profit percentage
            entry_data = self.entry_prices.get(strike, {})
            ce_entry_price = entry_data.get('ce_entry_price', 0)
            pe_entry_price = entry_data.get('pe_entry_price', 0)
            
            if ce_entry_price <= 0 or pe_entry_price <= 0:
                return False, "Invalid entry prices", 0
            
            # Calculate profit percentage
            ce_profit = (ce_entry_price - ce_current_price) / ce_entry_price
            pe_profit = (pe_entry_price - pe_current_price) / pe_entry_price
            combined_profit = (ce_profit + pe_profit) / 2
            
            # Check minimum profit threshold
            if combined_profit < self.scaling_profit_threshold:
                return False, f"Profit {combined_profit*100:.1f}% below threshold {self.scaling_profit_threshold*100:.0f}%", 0
            
            # Check current scaling level
            current_scaling = self.scaled_positions.get(strike, {}).get('scaling_level', 0)
            if current_scaling >= self.max_scaling_level - 1:  # -1 because original position counts as level 0
                return False, f"Already at max scaling level {self.max_scaling_level}", 0
            
            # Analyze OI conditions for scaling
            oi_sentiment = self.analyze_oi_sentiment(strike)
            if "error" in oi_sentiment:
                return False, f"OI analysis error: {oi_sentiment['error']}", 0
            
            sentiment = oi_sentiment.get('strike_sentiment', 'neutral')
            confidence = oi_sentiment.get('confidence', 0)
            
            # Check OI confidence threshold
            if confidence < self.scaling_oi_confidence_threshold:
                return False, f"OI confidence {confidence}% below threshold {self.scaling_oi_confidence_threshold}%", confidence
            
            # Determine scaling recommendation based on sentiment
            if sentiment == 'bullish_for_sellers':
                return True, f"Very favorable OI conditions (confidence: {confidence}%)", confidence
            elif sentiment == 'neutral' and combined_profit > 0.5:  # 50% profit
                return True, f"Neutral OI with strong profit {combined_profit*100:.1f}% (confidence: {confidence}%)", confidence
            else:
                return False, f"OI sentiment {sentiment} not favorable for scaling", confidence
                
        except Exception as e:
            return False, f"Error analyzing scaling conditions: {e}", 0
    
    def scale_position(self, strike: int, reason: str) -> bool:
        """
        Scale up an existing position by adding more contracts
        
        Args:
            strike (int): Strike price to scale
            reason (str): Reason for scaling
            
        Returns:
            bool: True if scaling successful
        """
        try:
            # Get current scaling level
            current_scaling = self.scaled_positions.get(strike, {}).get('scaling_level', 0)
            new_scaling_level = current_scaling + 1
            
            print(f"📈 SCALING: Adding to position at {strike} (Level {new_scaling_level}) - {reason}")
            
            # Place additional straddle orders for scaling
            if not self.place_additional_straddle(strike):
                print(f"❌ SCALING: Failed to add position at {strike}")
                return False
            
            # Update scaling tracking
            if strike not in self.scaled_positions:
                self.scaled_positions[strike] = {
                    'scaling_level': 0,
                    'scaling_history': [],
                    'total_scaled_quantity': 0
                }
            
            # Update scaling data
            self.scaled_positions[strike]['scaling_level'] = new_scaling_level
            self.scaled_positions[strike]['total_scaled_quantity'] += self.lot_size * self.market_lot
            self.scaled_positions[strike]['scaling_history'].append({
                'level': new_scaling_level,
                'reason': reason,
                'timestamp': datetime.now(),
                'quantity': self.lot_size * self.market_lot
            })
            
            print(f"✅ SCALING: Successfully added to position at {strike} (Level {new_scaling_level})")
            return True
            
        except Exception as e:
            print(f"❌ Error scaling position: {e}")
            return False
    
    def place_additional_straddle(self, strike):
        """
        Place additional straddle orders for position scaling (adds to existing position)
        
        Args:
            strike (int): Strike price for the additional straddle
        
        Returns:
            bool: True if orders placed successfully
        """
        try:
            # Get instrument keys
            ce_instrument_key = self.get_option_instrument_keys(strike, "CE")
            pe_instrument_key = self.get_option_instrument_keys(strike, "PE")
            
            if not ce_instrument_key or not pe_instrument_key:
                print(f"Failed to get instrument keys for strike {strike}")
                return False
            
            # Validate margin before placing additional orders
            quantity = self.lot_size * self.market_lot  # NIFTY lot size is 75
            margin_valid, margin_info = self.validate_trade_margin(
                ce_instrument_key, pe_instrument_key, quantity, "equity"
            )
            
            if not margin_valid:
                print(f"❌ Insufficient margin for additional straddle at strike {strike}")
                if margin_info:
                    print(f"   Required: ₹{margin_info['required_margin']:,.2f}")
                    print(f"   Available: ₹{margin_info['available_margin']:,.2f}")
                    print(f"   Shortfall: ₹{margin_info['shortfall']:,.2f}")
                return False
            
            print(f"✅ Margin validation passed for additional straddle at strike {strike}")
            if margin_info:
                print(f"   Required: ₹{margin_info['required_margin']:,.2f}")
                print(f"   Available: ₹{margin_info['available_margin']:,.2f}")
                print(f"   Remaining: ₹{margin_info['remaining_margin']:,.2f}")
                print(f"   Utilization: {margin_info['utilization_percent']:.1f}%")
            
            print(f"Placing additional straddle at strike {strike} for scaling")
            print(f"CE Instrument: {ce_instrument_key}")
            print(f"PE Instrument: {pe_instrument_key}")
            
            # Place short CE order
            ce_order = place_order(
                access_token=self.access_token,
                instrument_token=ce_instrument_key,
                quantity=self.lot_size * self.market_lot,  # NIFTY lot size is 75
                transaction_type="SELL",
                order_type="MARKET",
                price=0,  # Required for market orders
                product="MIS"  # Intraday product
            )
            
            if not ce_order or ce_order.get('status') != 'success':
                print(f"Failed to place CE order for scaling: {ce_order}")
                return False
            
            ce_order_id = ce_order.get('data', {}).get('order_id')
            print(f"✅ Additional CE order placed: {ce_order_id}")
            
            # Place short PE order
            pe_order = place_order(
                access_token=self.access_token,
                instrument_token=pe_instrument_key,
                quantity=self.lot_size * self.market_lot,  # NIFTY lot size is 75
                transaction_type="SELL",
                order_type="MARKET",
                price=0,  # Required for market orders
                product="MIS"  # Intraday product
            )
            
            if not pe_order or pe_order.get('status') != 'success':
                print(f"Failed to place PE order for scaling: {pe_order}")
                # Try to cancel the CE order if PE failed
                if ce_order_id:
                    print(f"Attempting to cancel CE order {ce_order_id} due to PE failure")
                return False
            
            pe_order_id = pe_order.get('data', {}).get('order_id')
            print(f"✅ Additional PE order placed: {pe_order_id}")
            
            # Get current prices for the additional position
            ce_current_price, pe_current_price = self.get_current_prices(ce_instrument_key, pe_instrument_key)
            
            if ce_current_price is None or pe_current_price is None:
                print("Warning: Could not get current prices for additional position")
                ce_current_price = 0
                pe_current_price = 0
            
            # Update existing position with additional orders (append to existing)
            if strike in self.active_positions:
                # Add additional order IDs to existing position
                existing_position = self.active_positions[strike]
                if 'additional_ce_orders' not in existing_position:
                    existing_position['additional_ce_orders'] = []
                if 'additional_pe_orders' not in existing_position:
                    existing_position['additional_pe_orders'] = []
                
                existing_position['additional_ce_orders'].append(ce_order_id)
                existing_position['additional_pe_orders'].append(pe_order_id)
                
                # Update entry prices (average with existing)
                existing_entry = self.entry_prices[strike]
                existing_ce_price = existing_entry.get('ce_entry_price', 0)
                existing_pe_price = existing_entry.get('pe_entry_price', 0)
                
                # For simplicity, we'll track the additional entry prices separately
                if 'additional_entry_prices' not in existing_entry:
                    existing_entry['additional_entry_prices'] = []
                
                existing_entry['additional_entry_prices'].append({
                    'ce_entry_price': ce_current_price,
                    'pe_entry_price': pe_current_price,
                    'timestamp': datetime.now(),
                    'quantity': new_quantity
                })
                
                print(f"✅ Additional straddle added to existing position at strike {strike}")
                print(f"   Additional CE: ₹{ce_current_price:.2f} (Order: {ce_order_id})")
                print(f"   Additional PE: ₹{pe_current_price:.2f} (Order: {pe_order_id})")
                
                return True
            else:
                print(f"Error: No existing position found at strike {strike} for scaling")
                return False
                
        except Exception as e:
            print(f"Error placing additional straddle: {e}")
            return False
    
    def check_and_scale_positions(self):
        """
        Check all active positions for scaling opportunities
        """
        if not self.position_scaling_enabled or not self.active_positions:
            return
        
        try:
            for strike in list(self.active_positions.keys()):
                should_scale, reason, confidence = self.should_scale_position(strike)
                
                if should_scale:
                    print(f"🎯 SCALING: Opportunity detected at {strike} (Confidence: {confidence}%)")
                    
                    # Scale the position
                    if self.scale_position(strike, reason):
                        pass  # Success message already printed in scale_position
                    else:
                        print(f"❌ SCALING: Failed to scale position at {strike}")
                else:
                    # Only show scaling status occasionally to avoid clutter
                    if confidence > 0 and self._oi_check_counter % 20 == 0:
                        print(f"📈 SCALING: No opportunity at {strike} - {reason} ({confidence}%)")
                        
        except Exception as e:
            print(f"❌ Error checking scaling opportunities: {e}")
    
    def check_straddle_entry_opportunities(self):
        """
        Check for straddle entry opportunities during the trading session
        This runs independently to catch opportunities when width conditions are met
        """
        try:
            # Get current ATM strike
            current_atm = self.get_atm_strike()
            
            # Check straddle width at current ATM with dynamic VIX-based threshold
            dynamic_threshold = self.get_vix_width_threshold()
            is_valid, ce_price, pe_price, width_percentage, nifty_price, nifty_deviation, ratio = self.check_straddle_width(current_atm, dynamic_threshold=dynamic_threshold)
            if is_valid:
                print(f"📊 STRADDLE: Entry conditions met at {current_atm} (Threshold: {dynamic_threshold*100:.1f}%)")
                if self.place_short_straddle(current_atm):
                    print(f"✅ STRADDLE: Placed at {current_atm}")
                else:
                    print(f"❌ STRADDLE: Failed to place at {current_atm}")
            else:
                # Only show status occasionally to avoid clutter
                if self._oi_check_counter % 10 == 0:
                    try:
                        ce_key = self.get_option_instrument_keys(current_atm, "CE")
                        pe_key = self.get_option_instrument_keys(current_atm, "PE")
                        ce_price, pe_price = self.get_current_prices(ce_key, pe_key)
                        if ce_price is not None and pe_price is not None and ce_price > 0 and pe_price > 0:
                            print(f"📊 STRADDLE: Waiting (Width > {dynamic_threshold*100:.1f}%) - CE ₹{ce_price:.1f}, PE ₹{pe_price:.1f}")
                    except:
                        pass
                
        except Exception as e:
            print(f"❌ STRADDLE: Error - {e}")
    
    def check_continuous_strangle_entry(self):
        """
        Check for new strangle entry opportunities during the trading session
        This runs continuously to catch opportunities that may arise
        """
        try:
            # Only check if we don't already have too many strangle positions
            if len(self.strangle_positions) >= self.max_strangle_positions:
                return  # Don't check if we already have max positions
            
            # Check for strangle entry conditions
            should_enter_strangle, strangle_reason, strangle_confidence = self.should_enter_strangle()
            
            if should_enter_strangle and strangle_confidence >= 50:
                print(f"🎯 STRANGLE: Entry conditions met (Confidence: {strangle_confidence}%)")
                # Place OI-guided strangle
                if self.place_oi_guided_strangle():
                    print(f"✅ STRANGLE: Placed successfully")
                else:
                    print(f"❌ STRANGLE: Failed to place")
            else:
                # Only show status occasionally to avoid clutter
                if self._oi_check_counter % 10 == 0:
                    print(f"🎯 STRANGLE: Waiting - {strangle_reason} ({strangle_confidence}%)")
                        
        except Exception as e:
            print(f"❌ STRANGLE: Error - {e}")
    
    def analyze_safe_otm_opportunities(self) -> Dict:
        """
        Analyze safe OTM options for easy money opportunities on NIFTY expiry days (weekly and monthly)
        
        Returns:
            Dict: Analysis results with recommended OTM options
        """
        if not self.safe_otm_enabled or not self._is_nifty_expiry_day():
            return {"error": "Safe OTM strategy not enabled or not a NIFTY expiry day"}
        
        try:
            # Get current market data
            spot_price = self.get_current_spot_price()
            if not spot_price:
                return {"error": "Unable to get current spot price"}
            
            atm_strike = round(spot_price / 50) * 50
            
            # Get option chain data
            option_chain_df = self.get_option_chain_atm()
            if option_chain_df is None or option_chain_df.empty:
                return {"error": "No option chain data available"}
            
            # Analyze OTM options (both CE and PE)
            safe_otm_calls = []
            safe_otm_puts = []
            
            # Analyze Call options (OTM = strike > ATM)
            call_options = option_chain_df[option_chain_df['type'] == 'call']
            for _, row in call_options.iterrows():
                strike = row['strike_price']
                call_ltp = row['ltp']
                call_oi = row['oi']
                call_prev_oi = row.get('prev_oi', call_oi)
                
                # Check if it's OTM and within distance criteria
                if strike > atm_strike:
                    distance_strikes = (strike - atm_strike) // 50
                    
                    if (self.safe_otm_criteria['min_distance_from_atm'] <= distance_strikes <= 
                        self.safe_otm_criteria['max_distance_from_atm']):
                        
                        # Check premium criteria
                        if (self.safe_otm_criteria['min_premium'] <= call_ltp <= 
                            self.safe_otm_criteria['max_premium']):
                            
                            # Calculate OI change
                            oi_change = ((call_oi - call_prev_oi) / call_prev_oi * 100) if call_prev_oi > 0 else 0
                            
                            if abs(oi_change) >= self.safe_otm_criteria['min_oi_change']:
                                # Calculate selling score
                                selling_score = self._calculate_otm_selling_score(
                                    strike, call_ltp, call_oi, call_prev_oi, "call", spot_price
                                )
                                
                                if selling_score >= self.safe_otm_criteria['min_selling_score']:
                                    safe_otm_calls.append({
                                        'strike': strike,
                                        'option_type': 'CE',
                                        'ltp': call_ltp,
                                        'oi': call_oi,
                                        'oi_change': oi_change,
                                        'selling_score': selling_score,
                                        'distance_from_atm': distance_strikes,
                                        'risk_reward_ratio': self._calculate_risk_reward_ratio(call_ltp, strike, spot_price, "call")
                                    })
            
            # Analyze Put options (OTM = strike < ATM)
            put_options = option_chain_df[option_chain_df['type'] == 'put']
            for _, row in put_options.iterrows():
                strike = row['strike_price']
                put_ltp = row['ltp']
                put_oi = row['oi']
                put_prev_oi = row.get('prev_oi', put_oi)
                
                # Check if it's OTM and within distance criteria
                if strike < atm_strike:
                    distance_strikes = (atm_strike - strike) // 50
                    
                    if (self.safe_otm_criteria['min_distance_from_atm'] <= distance_strikes <= 
                        self.safe_otm_criteria['max_distance_from_atm']):
                        
                        # Check premium criteria
                        if (self.safe_otm_criteria['min_premium'] <= put_ltp <= 
                            self.safe_otm_criteria['max_premium']):
                            
                            # Calculate OI change
                            oi_change = ((put_oi - put_prev_oi) / put_prev_oi * 100) if put_prev_oi > 0 else 0
                            
                            if abs(oi_change) >= self.safe_otm_criteria['min_oi_change']:
                                # Calculate selling score
                                selling_score = self._calculate_otm_selling_score(
                                    strike, put_ltp, put_oi, put_prev_oi, "put", spot_price
                                )
                                
                                if selling_score >= self.safe_otm_criteria['min_selling_score']:
                                    safe_otm_puts.append({
                                        'strike': strike,
                                        'option_type': 'PE',
                                        'ltp': put_ltp,
                                        'oi': put_oi,
                                        'oi_change': oi_change,
                                        'selling_score': selling_score,
                                        'distance_from_atm': distance_strikes,
                                        'risk_reward_ratio': self._calculate_risk_reward_ratio(put_ltp, strike, spot_price, "put")
                                    })
            
            # Sort by selling score (highest first)
            safe_otm_calls.sort(key=lambda x: x['selling_score'], reverse=True)
            safe_otm_puts.sort(key=lambda x: x['selling_score'], reverse=True)
            
            # Select top opportunities
            top_calls = safe_otm_calls[:2]  # Top 2 call opportunities
            top_puts = safe_otm_puts[:2]    # Top 2 put opportunities
            
            # Calculate overall analysis
            total_opportunities = len(safe_otm_calls) + len(safe_otm_puts)
            avg_selling_score = 0
            if total_opportunities > 0:
                all_scores = [opt['selling_score'] for opt in safe_otm_calls + safe_otm_puts]
                avg_selling_score = sum(all_scores) / len(all_scores)
            
            return {
                'spot_price': spot_price,
                'atm_strike': atm_strike,
                'total_opportunities': total_opportunities,
                'avg_selling_score': avg_selling_score,
                'top_calls': top_calls,
                'top_puts': top_puts,
                'all_calls': safe_otm_calls,
                'all_puts': safe_otm_puts,
                'analysis_timestamp': datetime.now()
            }
            
        except Exception as e:
            return {"error": f"Error analyzing safe OTM opportunities: {e}"}
    
    def _calculate_otm_selling_score(self, strike: int, ltp: float, oi: int, prev_oi: int, 
                                   option_type: str, spot_price: float) -> float:
        """
        Calculate selling score for OTM options
        
        Args:
            strike: Strike price
            ltp: Last traded price
            oi: Current open interest
            prev_oi: Previous open interest
            option_type: 'call' or 'put'
            spot_price: Current spot price
            
        Returns:
            float: Selling score (0-100)
        """
        try:
            score = 50  # Base score
            
            # Factor 1: Distance from ATM (farther = better for selling)
            if option_type == 'call':
                distance_points = strike - spot_price
            else:  # put
                distance_points = spot_price - strike
            
            distance_strikes = distance_points / 50
            if distance_strikes >= 3:  # 3+ strikes away
                score += 20
            elif distance_strikes >= 2:  # 2+ strikes away
                score += 10
            
            # Factor 2: OI Analysis
            oi_change = ((oi - prev_oi) / prev_oi * 100) if prev_oi > 0 else 0
            if option_type == 'call':
                if oi_change < -10:  # OI unwinding (good for call sellers)
                    score += 15
                elif oi_change > 10:  # OI building (bad for call sellers)
                    score -= 10
            else:  # put
                if oi_change < -10:  # OI unwinding (good for put sellers)
                    score += 15
                elif oi_change > 10:  # OI building (bad for put sellers)
                    score -= 10
            
            # Factor 3: Premium level (lower premium = better for selling)
            if ltp <= 10:
                score += 15
            elif ltp <= 15:
                score += 10
            elif ltp <= 20:
                score += 5
            elif ltp > 25:
                score -= 10
            
            # Factor 4: Time decay advantage (NIFTY expiry day)
            if self._is_nifty_expiry_day():
                score += 10  # Bonus for NIFTY expiry day
            
            # Factor 5: Risk-reward ratio
            risk_reward = self._calculate_risk_reward_ratio(ltp, strike, spot_price, option_type)
            if risk_reward >= 3:  # 1:3 risk-reward
                score += 10
            elif risk_reward >= 2:  # 1:2 risk-reward
                score += 5
            
            return max(0, min(100, score))  # Clamp between 0-100
            
        except Exception as e:
            print(f"Error calculating OTM selling score: {e}")
            return 50
    
    def _calculate_risk_reward_ratio(self, premium: float, strike: int, spot_price: float, option_type: str) -> float:
        """
        Calculate risk-reward ratio for OTM option selling
        
        Args:
            premium: Option premium
            strike: Strike price
            spot_price: Current spot price
            option_type: 'call' or 'put'
            
        Returns:
            float: Risk-reward ratio
        """
        try:
            # For OTM options, max profit = premium received
            max_profit = premium
            
            # Max risk = premium + intrinsic value if ITM
            if option_type == 'call':
                intrinsic_value = max(0, spot_price - strike)
            else:  # put
                intrinsic_value = max(0, strike - spot_price)
            
            max_risk = premium + intrinsic_value
            
            if max_risk > 0:
                return max_profit / max_risk
            else:
                return 0
                
        except Exception as e:
            print(f"Error calculating risk-reward ratio: {e}")
            return 0
    
    def should_enter_safe_otm(self) -> Tuple[bool, str, float]:
        """
        Determine if we should enter safe OTM positions
        
        Returns:
            Tuple[bool, str, float]: (should_enter, reason, confidence)
        """
        if not self.safe_otm_enabled or not self._is_nifty_expiry_day():
            return False, "Safe OTM strategy not enabled or not a NIFTY expiry day", 0
        
        if len(self.safe_otm_positions) >= self.max_safe_otm_positions:
            return False, f"Already at max safe OTM positions ({self.max_safe_otm_positions})", 0
        
        try:
            # Analyze safe OTM opportunities
            analysis = self.analyze_safe_otm_opportunities()
            
            if "error" in analysis:
                return False, f"Analysis error: {analysis['error']}", 0
            
            total_opportunities = analysis['total_opportunities']
            avg_selling_score = analysis['avg_selling_score']
            
            if total_opportunities == 0:
                return False, "No safe OTM opportunities found", 0
            
            if avg_selling_score >= 80:
                return True, f"Excellent safe OTM opportunities (Score: {avg_selling_score:.1f}, Count: {total_opportunities})", avg_selling_score
            elif avg_selling_score >= 70:
                return True, f"Good safe OTM opportunities (Score: {avg_selling_score:.1f}, Count: {total_opportunities})", avg_selling_score
            else:
                return False, f"Safe OTM opportunities below threshold (Score: {avg_selling_score:.1f})", avg_selling_score
                
        except Exception as e:
            return False, f"Error checking safe OTM conditions: {e}", 0
    
    def place_safe_otm_position(self, opportunity: Dict) -> bool:
        """
        Place a safe OTM position
        
        Args:
            opportunity: Safe OTM opportunity data
            
        Returns:
            bool: True if position placed successfully
        """
        try:
            strike = opportunity['strike']
            option_type = opportunity['option_type']
            ltp = opportunity['ltp']
            selling_score = opportunity['selling_score']
            
            print(f"\n💰 PLACING SAFE OTM POSITION")
            print(f"   Strike: {strike} {option_type}")
            print(f"   Premium: ₹{ltp:.2f}")
            print(f"   Selling Score: {selling_score:.1f}%")
            
            # Get instrument key
            instrument_key = self.get_option_instrument_keys(strike, option_type)
            if not instrument_key:
                print(f"❌ Failed to get instrument key for {strike} {option_type}")
                return False
            
            # Calculate position size based on risk criteria
            max_risk = self.safe_otm_criteria['max_risk_per_position']
            position_size = min(self.lot_size * self.market_lot, int(max_risk / ltp))  # Limit by risk
            
            if position_size <= 0:
                print(f"❌ Position size too small (risk limit)")
                return False
            
            # Place short order
            order = place_order(
                access_token=self.access_token,
                instrument_token=instrument_key,
                quantity=position_size,
                transaction_type="SELL",
                order_type="MARKET",
                price=0,
                product="MIS"
            )
            
            if not order or order.get('status') != 'success':
                print(f"❌ Failed to place safe OTM order: {order}")
                return False
            
            order_id = order.get('data', {}).get('order_id')
            
            # Track position
            position_id = f"safe_otm_{strike}_{option_type}_{datetime.now().strftime('%H%M%S')}"
            self.safe_otm_positions[position_id] = {
                'strike': strike,
                'option_type': option_type,
                'instrument_key': instrument_key,
                'entry_price': ltp,
                'quantity': position_size,
                'order_id': order_id,
                'selling_score': selling_score,
                'entry_time': datetime.now(),
                'profit_target': self.safe_otm_criteria['profit_target_per_position'],
                'stop_loss': -max_risk
            }
            
            print(f"✅ Safe OTM position placed: {position_id}")
            print(f"   Order ID: {order_id}")
            print(f"   Quantity: {position_size}")
            print(f"   Entry Price: ₹{ltp:.2f}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error placing safe OTM position: {e}")
            return False
    
    def check_safe_otm_opportunities(self):
        """
        Check for safe OTM opportunities during the trading session
        """
        try:
            # Check if we should enter safe OTM positions
            should_enter, reason, confidence = self.should_enter_safe_otm()
            
            if should_enter and confidence >= 70:
                print(f"💰 SAFE OTM: Entry conditions met (Confidence: {confidence}%)")
                
                # Analyze opportunities and place positions
                analysis = self.analyze_safe_otm_opportunities()
                if "error" not in analysis:
                    # Place top opportunities
                    opportunities_placed = 0
                    
                    # Place top call opportunity
                    if analysis['top_calls'] and opportunities_placed < 1:
                        if self.place_safe_otm_position(analysis['top_calls'][0]):
                            opportunities_placed += 1
                    
                    # Place top put opportunity
                    if analysis['top_puts'] and opportunities_placed < 1:
                        if self.place_safe_otm_position(analysis['top_puts'][0]):
                            opportunities_placed += 1
                    
                    if opportunities_placed > 0:
                        print(f"✅ SAFE OTM: {opportunities_placed} positions placed")
                else:
                    print(f"❌ SAFE OTM: Analysis failed - {analysis['error']}")
            else:
                # Only show status occasionally to avoid clutter
                if self._oi_check_counter % 10 == 0:
                    print(f"💰 SAFE OTM: Waiting - {reason} ({confidence}%)")
                        
        except Exception as e:
            print(f"❌ SAFE OTM: Error - {e}")
    
    def manage_safe_otm_positions(self):
        """
        Manage existing safe OTM positions
        """
        try:
            if not self.safe_otm_positions:
                return
            
            positions_to_exit = []
            
            for position_id, position in self.safe_otm_positions.items():
                strike = position['strike']
                option_type = position['option_type']
                entry_price = position['entry_price']
                profit_target = position['profit_target']
                stop_loss = position['stop_loss']
                
                # Get current price
                instrument_key = position['instrument_key']
                current_price = self._get_single_current_price(instrument_key)
                
                if current_price is None:
                    continue
                
                # Calculate P&L
                pnl = (entry_price - current_price) * position['quantity']
                
                # Check exit conditions
                exit_reason = None
                
                if pnl >= profit_target:
                    exit_reason = "profit_target"
                elif pnl <= stop_loss:
                    exit_reason = "stop_loss"
                elif self.is_market_close_time():
                    exit_reason = "market_close"
                
                if exit_reason:
                    positions_to_exit.append((position_id, exit_reason, pnl))
            
            # Exit positions
            for position_id, exit_reason, pnl in positions_to_exit:
                self.exit_safe_otm_position(position_id, exit_reason, pnl)
                
        except Exception as e:
            print(f"❌ Error managing safe OTM positions: {e}")
    
    def exit_safe_otm_position(self, position_id: str, reason: str, pnl: float):
        """
        Exit a safe OTM position
        
        Args:
            position_id: Position ID
            reason: Exit reason
            pnl: Current P&L
        """
        try:
            if position_id not in self.safe_otm_positions:
                return
            
            position = self.safe_otm_positions[position_id]
            instrument_key = position['instrument_key']
            quantity = position['quantity']
            
            print(f"\n💰 EXITING SAFE OTM POSITION: {position_id}")
            print(f"   Strike: {position['strike']} {position['option_type']}")
            print(f"   Reason: {reason}")
            print(f"   P&L: ₹{pnl:.2f}")
            
            # Place buy order to close position
            order = place_order(
                access_token=self.access_token,
                instrument_token=instrument_key,
                quantity=quantity,
                transaction_type="BUY",
                order_type="MARKET",
                price=0,
                product="MIS"
            )
            
            if order and order.get('status') == 'success':
                order_id = order.get('data', {}).get('order_id')
                print(f"✅ Safe OTM position closed: {position_id}")
                print(f"   Exit Order ID: {order_id}")
                print(f"   Final P&L: ₹{pnl:.2f}")
                
                # Remove from tracking
                del self.safe_otm_positions[position_id]
                
                # Add to history
                self.safe_otm_history.append({
                    'position_id': position_id,
                    'strike': position['strike'],
                    'option_type': position['option_type'],
                    'entry_price': position['entry_price'],
                    'exit_price': self._get_single_current_price(instrument_key),
                    'quantity': quantity,
                    'pnl': pnl,
                    'exit_reason': reason,
                    'entry_time': position['entry_time'],
                    'exit_time': datetime.now(),
                    'selling_score': position['selling_score']
                })
            else:
                print(f"❌ Failed to close safe OTM position: {order}")
                
        except Exception as e:
            print(f"❌ Error exiting safe OTM position: {e}")
    
    def calculate_dynamic_profit_target(self) -> float:
        """
        Calculate dynamic profit target based on current P&L and market conditions
        
        Returns:
            float: Dynamic profit target
        """
        if not self.dynamic_risk_enabled:
            return self.base_profit_target
        
        try:
            current_pnl = self.calculate_total_pnl()
            base_target = self.base_profit_target
            multiplier = 1.0
            
            # Factor 1: Current P&L momentum
            if current_pnl > 0:
                # If already in profit, increase target based on profit momentum
                profit_ratio = current_pnl / base_target
                if profit_ratio > 0.5:  # If already 50%+ of base target
                    multiplier *= self.risk_adjustment_factors['profit_momentum_multiplier']
            
            # Factor 2: OI Analysis (if available)
            if self.enable_oi_analysis and self.oi_analyzer:
                try:
                    oi_sentiment = self.analyze_oi_sentiment(self.current_strike)
                    if "error" not in oi_sentiment:
                        sentiment = oi_sentiment.get('strike_sentiment', 'neutral')
                        if sentiment == 'bullish_for_sellers':
                            multiplier *= self.risk_adjustment_factors['oi_bullish_multiplier']
                        elif sentiment == 'bearish_for_sellers':
                            multiplier *= self.risk_adjustment_factors['oi_bearish_multiplier']
                except Exception:
                    pass  # Use default multiplier if OI analysis fails
            
            # Factor 3: Time decay (increase targets as day progresses)
            current_time = datetime.now()
            if current_time.hour >= 14:  # After 2 PM, time decay accelerates
                multiplier *= self.risk_adjustment_factors['time_decay_multiplier']
            
            # Factor 4: Volatility (if we can detect high volatility)
            # This could be enhanced with actual volatility calculation
            if current_pnl > base_target * 0.3:  # If already 30%+ profit, assume high volatility
                multiplier *= self.risk_adjustment_factors['volatility_multiplier']
            
            # Calculate dynamic target
            dynamic_target = base_target * multiplier
            
            # Set reasonable bounds (50% to 300% of base target)
            min_target = base_target * 0.5
            max_target = base_target * 3.0
            dynamic_target = max(min_target, min(dynamic_target, max_target))
            
            return dynamic_target
            
        except Exception as e:
            print(f"Error calculating dynamic profit target: {e}")
            return self.base_profit_target
    
    def calculate_dynamic_stop_loss(self) -> float:
        """
        Calculate dynamic stop loss based on current P&L and market conditions
        
        Returns:
            float: Dynamic stop loss (negative value)
        """
        if not self.dynamic_risk_enabled:
            return -self.base_stop_loss
        
        try:
            current_pnl = self.calculate_total_pnl()
            base_stop = self.base_stop_loss
            multiplier = 1.0
            
            # Factor 1: Current P&L (tighten stop if in profit)
            if current_pnl > 0:
                # If in profit, tighten stop loss
                profit_ratio = current_pnl / base_stop
                if profit_ratio > 0.3:  # If 30%+ profit, tighten stop
                    multiplier *= 0.8  # 20% tighter stop loss
            
            # Factor 2: OI Analysis (if available)
            if self.enable_oi_analysis and self.oi_analyzer:
                try:
                    oi_sentiment = self.analyze_oi_sentiment(self.current_strike)
                    if "error" not in oi_sentiment:
                        sentiment = oi_sentiment.get('strike_sentiment', 'neutral')
                        if sentiment == 'bearish_for_sellers':
                            multiplier *= 0.7  # Tighter stop when OI is bearish
                        elif sentiment == 'bullish_for_sellers':
                            multiplier *= 1.2  # Wider stop when OI is bullish
                except Exception:
                    pass
            
            # Factor 3: Time decay (tighten stop as day progresses)
            current_time = datetime.now()
            if current_time.hour >= 14:  # After 2 PM, time decay helps
                multiplier *= 0.9  # 10% tighter stop
            
            # Calculate dynamic stop loss
            dynamic_stop = base_stop * multiplier
            
            # Set reasonable bounds (50% to 150% of base stop)
            min_stop = base_stop * 0.5
            max_stop = base_stop * 1.5
            dynamic_stop = max(min_stop, min(dynamic_stop, max_stop))
            
            return -dynamic_stop  # Return negative value for stop loss
            
        except Exception as e:
            print(f"Error calculating dynamic stop loss: {e}")
            return -self.base_stop_loss
    
    def update_trailing_stop_loss(self):
        """
        Update trailing stop loss based on current profit milestones (Tiered Trailing SL)
        """
        if not self.trailing_stop_enabled or not self.trailing_tiers:
            return
        
        try:
            current_pnl = self.calculate_total_pnl()
            if current_pnl <= 0:
                return False
            
            # Update highest profit
            if current_pnl > self.highest_profit:
                self.highest_profit = current_pnl
            
            # Check milestones and update trailing stop level
            profit_percentage = self.highest_profit / self.profit_target
            new_trailing_level = self.trailing_stop_level
            
            # Iterate through tiers to find the highest applicable locked profit
            for milestone, lock_pct in sorted(self.trailing_tiers.items(), reverse=True):
                if profit_percentage >= milestone:
                    tier_level = self.profit_target * lock_pct
                    if tier_level > new_trailing_level:
                        new_trailing_level = tier_level
                        status_msg = f"🏆 SL TIER reached: {milestone*100:.0f}% Target | Locked ₹{new_trailing_level:.0f}"
                        print(f"📈 {status_msg}")
                    break # Found the highest applicable milestone
            
            # Standard trailing distance fallback if no tier is reached yet
            if new_trailing_level == 0 and self.highest_profit > self.trailing_stop_distance:
                standard_level = self.highest_profit - self.trailing_stop_distance
                if standard_level > new_trailing_level:
                    new_trailing_level = standard_level
            
            # Update global trailing level
            if new_trailing_level > self.trailing_stop_level:
                self.trailing_stop_level = new_trailing_level
            
            # Check if trailing stop is triggered
            if current_pnl <= self.trailing_stop_level and self.trailing_stop_level > 0:
                if not self.trailing_stop_triggered:
                    self.trailing_stop_triggered = True
                    print(f"🚨 TIERED TRAILING STOP TRIGGERED! P&L: ₹{current_pnl:.0f} ≤ Hidden Floor: ₹{self.trailing_stop_level:.0f}")
                    return True
            
            return False
            
        except Exception as e:
            print(f"Error updating trailing stop loss: {e}")
            return False
    
    def update_dynamic_risk_parameters(self):
        """
        Update dynamic risk parameters based on current market conditions
        """
        if not self.dynamic_risk_enabled:
            return
        
        try:
            # Update dynamic profit target
            old_target = self.current_profit_target
            self.current_profit_target = self.calculate_dynamic_profit_target()
            
            # Update dynamic stop loss
            old_stop = self.current_stop_loss
            self.current_stop_loss = self.calculate_dynamic_stop_loss()
            
            # Log significant changes
            target_change = abs(self.current_profit_target - old_target)
            stop_change = abs(self.current_stop_loss - old_stop)
            
            if target_change > 500:  # Significant change in profit target
                print(f"🎯 Dynamic Profit Target Updated: ₹{old_target:.0f} → ₹{self.current_profit_target:.0f}")
            
            if stop_change > 500:  # Significant change in stop loss
                print(f"🛡️  Dynamic Stop Loss Updated: ₹{old_stop:.0f} → ₹{self.current_stop_loss:.0f}")
            
            # Update trailing stop loss
            trailing_triggered = self.update_trailing_stop_loss()
            if trailing_triggered:
                return True  # Signal that trailing stop was triggered
            
            return False
            
        except Exception as e:
            print(f"Error updating dynamic risk parameters: {e}")
            return False
    
    def check_dynamic_profit_target(self) -> bool:
        """
        Check if dynamic profit target has been achieved
        
        Returns:
            bool: True if profit target achieved
        """
        try:
            current_pnl = self.calculate_total_pnl()
            
            if current_pnl >= self.current_profit_target:
                print(f"🎯 DYNAMIC PROFIT TARGET ACHIEVED!")
                print(f"   Current P&L: ₹{current_pnl:.2f}")
                print(f"   Dynamic Target: ₹{self.current_profit_target:.2f}")
                print(f"   Base Target: ₹{self.base_profit_target:.2f}")
                return True
            
            return False
            
        except Exception as e:
            print(f"Error checking dynamic profit target: {e}")
            return False
    
    def check_dynamic_stop_loss(self) -> bool:
        """
        Check if dynamic stop loss has been triggered
        
        Returns:
            bool: True if stop loss triggered
        """
        try:
            current_pnl = self.calculate_total_pnl()
            
            if current_pnl <= self.current_stop_loss:
                print(f"🚨 DYNAMIC STOP LOSS TRIGGERED!")
                print(f"   Current P&L: ₹{current_pnl:.2f}")
                print(f"   Dynamic Stop: ₹{self.current_stop_loss:.2f}")
                print(f"   Base Stop: ₹{-self.base_stop_loss:.2f}")
                return True
            
            return False
            
        except Exception as e:
            print(f"Error checking dynamic stop loss: {e}")
            return False
    
    def exit_strangle_position(self, strangle_id: str, reason: str):
        """
        Exit a strangle position
        
        Args:
            strangle_id (str): Strangle position ID
            reason (str): Exit reason
        
        Returns:
            bool: True if exited successfully
        """
        if strangle_id not in self.strangle_positions:
            return False
        
        try:
            position = self.strangle_positions[strangle_id]
            ce_instrument_key = position['ce_instrument_key']
            pe_instrument_key = position['pe_instrument_key']
            
            # Place buy orders to close positions
            ce_order = place_order(
                access_token=self.access_token,
                instrument_token=ce_instrument_key,
                quantity=self.lot_size * self.market_lot,
                transaction_type="BUY",
                order_type="MARKET",
                price=0,
                product="I",
                validity="DAY",
                tag=f"Strangle_Exit_CE_{position['ce_strike']}"
            )
            
            pe_order = place_order(
                access_token=self.access_token,
                instrument_token=pe_instrument_key,
                quantity=self.lot_size * self.market_lot,
                transaction_type="BUY",
                order_type="MARKET",
                price=0,
                product="I",
                validity="DAY",
                tag=f"Strangle_Exit_PE_{position['pe_strike']}"
            )
            
            if ce_order and pe_order:
                # Remove from tracking
                del self.strangle_positions[strangle_id]
                
                # Log the exit
                self.trades_log.append({
                    'timestamp': datetime.now(),
                    'action': 'OI_STRANGLE_EXIT',
                    'strangle_id': strangle_id,
                    'ce_strike': position['ce_strike'],
                    'pe_strike': position['pe_strike'],
                    'exit_reason': reason
                })
                
                return True
            else:
                print(f"❌ Failed to place exit orders for strangle {strangle_id}")
                return False
                
        except Exception as e:
            print(f"❌ Error exiting strangle position {strangle_id}: {e}")
            return False
    
    def _get_current_expiry(self):
        """Get current expiry date"""
        from datetime import datetime, timedelta
        today = datetime.now()
        # Simple logic to get next Tuesday (current NIFTY expiry)
        days_ahead = (1 - today.weekday()) % 7  # Tuesday is 1
        if days_ahead == 0:  # If today is Tuesday
            days_ahead = 7
        return (today + timedelta(days=days_ahead)).strftime('%Y-%m-%d')
    
    def _is_nifty_expiry_day(self):
        """
        Check if today is a NIFTY expiry day (weekly or monthly)
        
        Returns:
            bool: True if today is a NIFTY expiry day
        """
        from datetime import datetime, timedelta
        today = datetime.now()
        
        # NIFTY weekly options expire on Tuesdays, monthly on last Thursday
        if today.weekday() == 1:  # Tuesday is 1 (weekly expiry)
            return True
        elif today.weekday() == 3:  # Thursday is 3 (monthly expiry)
            # Check if it's the last Thursday of the month (monthly expiry)
            # Get the last day of the current month
            if today.month == 12:
                next_month = today.replace(year=today.year + 1, month=1, day=1)
            else:
                next_month = today.replace(month=today.month + 1, day=1)
            
            last_day_of_month = next_month - timedelta(days=1)
            
            # Find the last Thursday of the month
            last_thursday = last_day_of_month
            while last_thursday.weekday() != 3:  # Thursday is 3
                last_thursday -= timedelta(days=1)
            
            # If today is the last Thursday of the month, it's monthly expiry
            return today.date() == last_thursday.date()
        else:
            return False
    
    def place_short_straddle(self, strike):
        """
        Place short straddle orders (short CE and PE at the same strike).
        
        Args:
            strike (int): Strike price for the straddle
        
        Returns:
            bool: True if orders placed successfully
        """
        try:
            # Get instrument keys
            ce_instrument_key = self.get_option_instrument_keys(strike, "CE")
            pe_instrument_key = self.get_option_instrument_keys(strike, "PE")
            
            if not ce_instrument_key or not pe_instrument_key:
                print(f"Failed to get instrument keys for strike {strike}")
                return False
            
            # SIMPLE RATIO CHECK - Block entry if ratio < 0.8
            ce_price, pe_price = self.get_current_prices(ce_instrument_key, pe_instrument_key)
            if ce_price is not None and pe_price is not None and ce_price > 0 and pe_price > 0:
                ratio = self.calculate_ratio(ce_price, pe_price)
                if ratio < 0.8:
                    print(f"🚫 ENTRY BLOCKED: Ratio {ratio:.3f} below 0.8 threshold")
                    return False
                else:
                    print(f"✅ Ratio check passed: {ratio:.3f} >= 0.8")
            else:
                print(f"⚠️  Cannot verify ratio - proceeding with caution")
            
            # Validate margin before placing orders
            quantity = self.lot_size * self.market_lot  # NIFTY lot size is 75
            margin_valid, margin_info = self.validate_trade_margin(
                ce_instrument_key, pe_instrument_key, quantity, "equity"
            )
            
            if not margin_valid:
                print(f"❌ Insufficient margin for straddle at strike {strike}")
                if margin_info:
                    print(f"   Required: ₹{margin_info['required_margin']:,.2f}")
                    print(f"   Available: ₹{margin_info['available_margin']:,.2f}")
                    print(f"   Shortfall: ₹{margin_info['shortfall']:,.2f}")
                return False
            
            print(f"✅ Margin validation passed for straddle at strike {strike}")
            if margin_info:
                print(f"   Required: ₹{margin_info['required_margin']:,.2f}")
                print(f"   Available: ₹{margin_info['available_margin']:,.2f}")
                print(f"   Remaining: ₹{margin_info['remaining_margin']:,.2f}")
                print(f"   Utilization: {margin_info['utilization_percent']:.1f}%")
            
            print(f"Placing simultaneous short straddle at strike {strike}")
            
            # Prepare multi-order payload
            orders_payload = [
                {
                    "instrument_token": ce_instrument_key,
                    "quantity": quantity,
                    "transaction_type": "SELL",
                    "order_type": "MARKET",
                    "product": "I",
                    "validity": "DAY",
                    "tag": f"Strv3_CE_{strike}"
                },
                {
                    "instrument_token": pe_instrument_key,
                    "quantity": quantity,
                    "transaction_type": "SELL",
                    "order_type": "MARKET",
                    "product": "I",
                    "validity": "DAY",
                    "tag": f"Strv3_PE_{strike}"
                }
            ]
            
            # Use V3 Multi-Order Place API
            multi_response = place_multi_order(self.access_token, orders_payload)
            
            if multi_response and multi_response.get("status") == "success":
                # Extract order IDs from response
                order_ids = multi_response.get("data", {}).get("order_ids", [])
                
                if len(order_ids) >= 2:
                    ce_order_id = order_ids[0]
                    pe_order_id = order_ids[1]
                    
                    # Track this position in active_positions
                    self.active_positions[strike] = {
                        'ce_order_id': ce_order_id,
                        'pe_order_id': pe_order_id,
                        'ce_instrument_key': ce_instrument_key,
                        'pe_instrument_key': pe_instrument_key,
                        'timestamp': datetime.now()
                    }
                    
                    # Store entry prices (using same price for both as they are placed simultaneously)
                    self.entry_prices[strike] = {
                        'ce_entry_price': ce_price,
                        'pe_entry_price': pe_price,
                        'timestamp': datetime.now()
                    }
                    
                    self.entry_straddle_prices[strike] = {
                        'entry_straddle_price': ce_price + pe_price,
                        'timestamp': datetime.now()
                    }
                    
                    self.current_strike = strike
                    self.is_strategy_active = True
                    
                    print(f"✅ Simultaneous short straddle successful! IDs: {ce_order_id}, {pe_order_id}")
                    return True
                else:
                    print(f"⚠️  Multi-order placed but returned fewer IDs than expected: {order_ids}")
                    return False
            else:
                print(f"❌ Simultaneous order placement failed: {multi_response}")
                return False
                
        except Exception as e:
            print(f"Error placing short straddle: {e}")
            return False
    
    def place_single_option(self, strike, option_type):
        """
        Place a single option order (CE or PE).
        
        Args:
            strike (int): Strike price
            option_type (str): "CE" or "PE"
        
        Returns:
            str: Order ID if successful, None otherwise
        """
        try:
            instrument_key = self.get_option_instrument_keys(strike, option_type)
            if not instrument_key:
                print(f"Failed to get {option_type} instrument key for strike {strike}")
                return None
            
            print(f"Placing short {option_type} at strike {strike}")
            print(f"{option_type} Instrument: {instrument_key}")
            
            order = place_order(
                access_token=self.access_token,
                instrument_token=instrument_key,
                quantity=self.lot_size * self.market_lot,  # NIFTY lot size is 75
                transaction_type="SELL",
                order_type="MARKET",
                price=0,  # Required for market orders
                product="I",  # Intraday for options
                validity="DAY",
                tag=f"Single_{option_type}_{strike}"
            )
            
            if order:
                order_id = order.get("data", {}).get("order_ids", [None])[0]
                print(f"Short {option_type} placed successfully! Order ID: {order_id}")
                
                # Get current price for entry tracking
                current_price = self._get_single_current_price(instrument_key)
                if current_price is None:
                    print("Warning: Could not get current price for single option entry tracking")
                    current_price = 0
                
                # Track entry price
                if strike not in self.entry_prices:
                    self.entry_prices[strike] = {
                        'ce_entry_price': 0,
                        'pe_entry_price': 0,
                        'timestamp': datetime.now()
                    }
                
                if option_type == "CE":
                    self.entry_prices[strike]['ce_entry_price'] = current_price
                else:
                    self.entry_prices[strike]['pe_entry_price'] = current_price
                
                # Update entry straddle price if both CE and PE are now available
                ce_price = self.entry_prices[strike]['ce_entry_price']
                pe_price = self.entry_prices[strike]['pe_entry_price']
                if ce_price > 0 and pe_price > 0:
                    entry_straddle_price = ce_price + pe_price
                    if strike not in self.entry_straddle_prices:
                        self.entry_straddle_prices[strike] = {
                            'entry_straddle_price': entry_straddle_price,
                            'timestamp': datetime.now()
                        }
                    else:
                        self.entry_straddle_prices[strike]['entry_straddle_price'] = entry_straddle_price
                
                # Log the trade
                self.trades_log.append({
                    'timestamp': datetime.now(),
                    'action': f'SHORT_{option_type}',
                    'strike': strike,
                    'order_id': order_id,
                    'entry_price': current_price
                })
                
                return order_id
            else:
                print(f"Failed to place {option_type} order")
                return None
                
        except Exception as e:
            print(f"Error placing {option_type} order: {e}")
            return None
    
    def square_off_position(self, order_id, position_type, strike=None):
        """
        Square off a position by placing a buy order.
        
        Args:
            order_id (str): Order ID to square off
            position_type (str): "CE" or "PE"
            strike (int): Strike price for the position (optional)
        
        Returns:
            bool: True if squared off successfully
        """
        try:
            print(f"Squaring off {position_type} position: {order_id}")
            
            # Get order details to get instrument token
            order_book = get_order_book(self.access_token)
            if order_book.empty:
                print("Failed to get order book")
                return False
            
            # Find the order in order book
            order_details = order_book[order_book['order_id'] == order_id]
            if order_details.empty:
                print(f"Order {order_id} not found in order book")
                return False
            
            instrument_token = order_details.iloc[0]['instrument_token']
            quantity = int(order_details.iloc[0]['quantity'])  # Convert pandas int64 to Python int
            
            # Place buy order to square off
            square_off_order = place_order(
                access_token=self.access_token,
                instrument_token=instrument_token,
                quantity=quantity,
                transaction_type="BUY",
                order_type="MARKET",
                price=0,  # Required for market orders
                product="I",  # Intraday for options
                validity="DAY",
                tag=f"SquareOff_{position_type}_{strike if strike else self.current_strike}"
            )
            
            if square_off_order:
                square_off_id = square_off_order.get("data", {}).get("order_ids", [None])[0]
                print(f"{position_type} position squared off successfully: {square_off_id}")
                
                # Calculate realized P&L for this position
                if strike and strike in self.entry_prices:
                    entry_data = self.entry_prices[strike]
                    if position_type == "CE" and entry_data.get('ce_entry_price', 0) > 0:
                        # Get current price to calculate realized P&L
                        try:
                            current_price = self._get_single_current_price(instrument_token)
                            if current_price is not None:
                                entry_price = entry_data['ce_entry_price']
                                # For short positions: realized P&L = entry_price - exit_price
                                realized_pnl = (entry_price - current_price) * self.lot_size * self.market_lot
                                self.realized_pnl += realized_pnl
                                print(f"Realized P&L for {position_type} {strike}: ₹{realized_pnl:.2f} (Entry: ₹{entry_price:.2f}, Exit: ₹{current_price:.2f})")
                        except Exception as e:
                            print(f"Error calculating realized P&L: {e}")
                    
                    elif position_type == "PE" and entry_data.get('pe_entry_price', 0) > 0:
                        # Get current price to calculate realized P&L
                        try:
                            current_price = self._get_single_current_price(instrument_token)
                            if current_price is not None:
                                entry_price = entry_data['pe_entry_price']
                                # For short positions: realized P&L = entry_price - exit_price
                                realized_pnl = (entry_price - current_price) * self.lot_size * self.market_lot
                                self.realized_pnl += realized_pnl
                                print(f"Realized P&L for {position_type} {strike}: ₹{realized_pnl:.2f} (Entry: ₹{entry_price:.2f}, Exit: ₹{current_price:.2f})")
                        except Exception as e:
                            print(f"Error calculating realized P&L: {e}")
                
                # Log the trade
                self.trades_log.append({
                    'timestamp': datetime.now(),
                    'action': f'SQUARE_OFF_{position_type}',
                    'strike': strike if strike else self.current_strike,
                    'order_id': square_off_id
                })
                
                return True
            else:
                print(f"Failed to square off {position_type} position")
                return False
                
        except Exception as e:
            print(f"Error squaring off {position_type} position: {e}")
            return False
    
    def manage_positions(self):
        """
        Monitor and manage positions based on the ratio threshold.
        
        Returns:
            bool: True if positions were managed
        """
        try:
            if not self.is_strategy_active or not self.active_positions:
                return False
            
            # Find the current active CE and PE positions (they might be at different strikes)
            active_ce_strike = None
            active_pe_strike = None
            active_ce_position = None
            active_pe_position = None
            
            for strike, position in self.active_positions.items():
                if position.get('ce_order_id'):
                    active_ce_strike = strike
                    active_ce_position = position
                if position.get('pe_order_id'):
                    active_pe_strike = strike
                    active_pe_position = position
            
            # Check if we have both CE and PE active (they can be at different strikes)
            if not active_ce_position or not active_pe_position:
                return False
            
            # Get current prices for the active CE and PE positions
            ce_instrument_key = active_ce_position['ce_instrument_key']
            pe_instrument_key = active_pe_position['pe_instrument_key']
            
            # Get current prices for the active positions
            ce_price, pe_price = self.get_current_prices(ce_instrument_key, pe_instrument_key)
            if ce_price is None or pe_price is None or ce_price <= 0 or pe_price <= 0:
                return False
            
            # Calculate ratio
            ratio = self.calculate_ratio(ce_price, pe_price)
            
            # Get dynamic ratio threshold based on current prices
            dynamic_ratio_threshold = self.get_dynamic_ratio_threshold(ce_price, pe_price)
            
            # Check if ratio is below exit threshold (0.5)
            exit_threshold = 0.5
            if ratio < exit_threshold:
                
                # Determine which side is losing (higher price)
                if ce_price > pe_price:
                    # CE is losing (market moved higher), square off CE and move to higher strike
                    losing_side = "CE"
                    new_strike = active_ce_strike + 50  # Move 1 strike UP (e.g., 25350 → 25400)
                    losing_order_id = active_ce_position['ce_order_id']
                    if self.verbose:
                        print(f"📈 Market moved higher: CE({active_ce_strike}) ₹{ce_price:.2f} > PE({active_pe_strike}) ₹{pe_price:.2f}")
                        print(f"🔄 Attempting to move CE from {active_ce_strike} to {new_strike} (1 strike UP)")
                else:
                    # PE is losing (market moved lower), square off PE and move to lower strike
                    losing_side = "PE"
                    new_strike = active_pe_strike - 50  # Move 1 strike DOWN (e.g., 25300 → 25250)
                    losing_order_id = active_pe_position['pe_order_id']
                    if self.verbose:
                        print(f"📉 Market moved lower: PE({active_pe_strike}) ₹{pe_price:.2f} > CE({active_ce_strike}) ₹{ce_price:.2f}")
                        print(f"🔄 Attempting to move PE from {active_pe_strike} to {new_strike} (1 strike DOWN)")
                
                    # Check maximum deviation before moving
                    if self.verbose:
                        print(f"   🔍 Checking deviation limit for {losing_side} move to {new_strike}...")
                    if not self.check_max_deviation(new_strike):
                        print(f"🚨 Cannot move {losing_side} to {new_strike} - exceeds maximum deviation limit!")
                        if self.verbose:
                            print(f"🔄 Squaring off all positions and starting fresh at current ATM...")
                        
                        # Square off all current positions and start fresh
                        if self.square_off_all_positions():
                            # Start fresh straddle at current ATM
                            return self.start_fresh_straddle()
                        else:
                            print(f"❌ Failed to square off all positions")
                            return False
                    else:
                        if self.verbose:
                            print(f"   ✅ Deviation check passed for {losing_side} move to {new_strike}")
                    
                # Square off the losing side
                current_strike = active_ce_strike if losing_side == "CE" else active_pe_strike
                if self.verbose:
                    print(f"   🔄 Squaring off {losing_side} position at strike {current_strike}...")
                if self.square_off_position(losing_order_id, losing_side, current_strike):
                    if self.verbose:
                        print(f"   ✅ Successfully squared off {losing_side} position")
                    # Place new option at new strike
                    if self.verbose:
                        print(f"   🔄 Placing new {losing_side} order at strike {new_strike}...")
                    new_order_id = self.place_single_option(new_strike, losing_side)
                    
                    if new_order_id:
                        if self.verbose:
                            print(f"   ✅ Successfully placed new {losing_side} order: {new_order_id}")
                        # Update position tracking
                        if losing_side == "CE":
                            # Remove CE from current strike, add CE to new strike
                            active_ce_position['ce_order_id'] = None
                            active_ce_position['ce_instrument_key'] = None
                            
                            # Add or update position at new strike
                            if new_strike not in self.active_positions:
                                self.active_positions[new_strike] = {
                                    'ce_order_id': new_order_id,
                                    'pe_order_id': None,
                                    'ce_instrument_key': self.get_option_instrument_keys(new_strike, "CE"),
                                    'pe_instrument_key': None,
                                    'timestamp': datetime.now()
                                }
                            else:
                                self.active_positions[new_strike]['ce_order_id'] = new_order_id
                                self.active_positions[new_strike]['ce_instrument_key'] = self.get_option_instrument_keys(new_strike, "CE")
                            
                            if not self.verbose:
                                print(f"✓ Moved CE: {current_strike}→{new_strike}")
                            else:
                                print(f"Successfully moved CE from {current_strike} to {new_strike}")
                        else:  # PE
                            # Remove PE from current strike, add PE to new strike
                            active_pe_position['pe_order_id'] = None
                            active_pe_position['pe_instrument_key'] = None
                            
                            # Add or update position at new strike
                            if new_strike not in self.active_positions:
                                self.active_positions[new_strike] = {
                                    'ce_order_id': None,
                                    'pe_order_id': new_order_id,
                                    'ce_instrument_key': None,
                                    'pe_instrument_key': self.get_option_instrument_keys(new_strike, "PE"),
                                    'timestamp': datetime.now()
                                }
                            else:
                                self.active_positions[new_strike]['pe_order_id'] = new_order_id
                                self.active_positions[new_strike]['pe_instrument_key'] = self.get_option_instrument_keys(new_strike, "PE")
                            
                            print(f"Successfully moved PE from {current_strike} to {new_strike}")
                        
                        # Note: We don't update current_strike here as we want to maintain
                        # the original ATM strike for reference, but track multiple positions
                        
                        return True
                    else:
                        print(f"   ❌ Failed to place new {losing_side} order at strike {new_strike}")
                else:
                    print(f"   ❌ Failed to square off {losing_side} position")
            
            return False
            
        except Exception as e:
            print(f"Error managing positions: {e}")
            return False
    
    def calculate_total_pnl(self):
        """
        Calculate total P&L including realized and unrealized components.
        
        Returns:
            float: Total P&L (realized + unrealized)
        """
        try:
            # Calculate unrealized P&L from current open positions
            self.unrealized_pnl = 0
            
            for strike, position in self.active_positions.items():
                # Get entry prices for this strike (including scaled positions)
                entry_data = self.entry_prices.get(strike, {})
                ce_entry_price = entry_data.get('ce_entry_price', 0)
                pe_entry_price = entry_data.get('pe_entry_price', 0)
                
                # Calculate total quantity including scaled positions
                total_quantity = self.lot_size * self.market_lot  # Base quantity
                scaling_data = self.scaled_positions.get(strike, {})
                scaling_level = scaling_data.get('scaling_level', 0)
                total_quantity += scaling_level * self.lot_size * self.market_lot  # Add scaled quantity
                
                if position.get('ce_order_id') and position.get('ce_instrument_key') and ce_entry_price > 0:
                    # Get current CE price
                    current_ce_price = self._get_single_current_price(position['ce_instrument_key'])
                    if current_ce_price is not None:
                        # For short positions: profit = entry_price - current_price
                        # Use total quantity including scaled positions
                        ce_pnl = (ce_entry_price - current_ce_price) * total_quantity
                        self.unrealized_pnl += ce_pnl
                
                if position.get('pe_order_id') and position.get('pe_instrument_key') and pe_entry_price > 0:
                    # Get current PE price
                    current_pe_price = self._get_single_current_price(position['pe_instrument_key'])
                    if current_pe_price is not None:
                        # For short positions: profit = entry_price - current_price
                        # Use total quantity including scaled positions
                        pe_pnl = (pe_entry_price - current_pe_price) * total_quantity
                        self.unrealized_pnl += pe_pnl
            
            # Calculate total P&L
            self.total_profit = self.realized_pnl + self.unrealized_pnl
            return self.total_profit
            
        except Exception as e:
            print(f"Error calculating total P&L: {e}")
            return 0

    def check_profit_target(self):
        """
        Check if profit target has been achieved (dynamic or static).
        
        Returns:
            bool: True if profit target achieved
        """
        try:
            if self.dynamic_risk_enabled:
                return self.check_dynamic_profit_target()
            else:
                # Use static profit target
                total_pnl = self.calculate_total_pnl()
            if total_pnl >= self.profit_target:
                print(f"🎯 Profit target of ₹{self.profit_target} achieved! Current P&L: ₹{total_pnl:.2f}")
                return True
            return False
            
        except Exception as e:
            print(f"Error checking profit target: {e}")
            return False
    
    def check_max_loss_limit(self):
        """
        Check if maximum loss limit has been reached (dynamic or static).
        
        Returns:
            bool: True if max loss limit reached
        """
        try:
            if self.dynamic_risk_enabled:
                # Check dynamic stop loss and trailing stop
                if self.check_dynamic_stop_loss():
                    return True
                
                # Also check trailing stop
                if self.trailing_stop_triggered:
                    return True
                
                return False
            else:
                # Use static max loss limit
                total_pnl = self.calculate_total_pnl()
            if total_pnl <= -self.max_loss_limit:
                print(f"🚨 MAXIMUM LOSS LIMIT REACHED!")
                print(f"   Current P&L: ₹{total_pnl:.2f}")
                print(f"   Max Loss Limit: ₹{self.max_loss_limit}")
                print(f"   ❌ Strategy stopped for the day - no re-entry allowed")
                return True
            return False
            
        except Exception as e:
            print(f"Error checking max loss limit: {e}")
            return False
    
    def square_off_all_positions(self, reason="normal"):
        """
        Square off all active positions.
        
        Args:
            reason (str): Reason for squaring off ("normal", "max_loss", "profit_target")
        
        Returns:
            bool: True if all positions squared off
        """
        try:
            print("Squaring off all positions...")
            
            success = True
            
            # Square off all active straddle positions
            for strike, position in self.active_positions.items():
                print(f"Squaring off straddle position at strike {strike}")
                
                # Square off CE if exists
                if position.get('ce_order_id'):
                    if not self.square_off_position(position['ce_order_id'], "CE", strike):
                        success = False
                        print(f"Failed to square off CE at strike {strike}")
                
                # Square off PE if exists
                if position.get('pe_order_id'):
                    if not self.square_off_position(position['pe_order_id'], "PE", strike):
                        success = False
                        print(f"Failed to square off PE at strike {strike}")
                
                # Square off additional CE orders from scaling
                additional_ce_orders = position.get('additional_ce_orders', [])
                for ce_order_id in additional_ce_orders:
                    if not self.square_off_position(ce_order_id, "CE", strike):
                        success = False
                        print(f"Failed to square off additional CE {ce_order_id} at strike {strike}")
                
                # Square off additional PE orders from scaling
                additional_pe_orders = position.get('additional_pe_orders', [])
                for pe_order_id in additional_pe_orders:
                    if not self.square_off_position(pe_order_id, "PE", strike):
                        success = False
                        print(f"Failed to square off additional PE {pe_order_id} at strike {strike}")
            
            # Square off all active strangle positions
            if hasattr(self, 'strangle_positions') and self.strangle_positions:
                print(f"Squaring off {len(self.strangle_positions)} strangle positions...")
                for strangle_id, position in list(self.strangle_positions.items()):
                    print(f"Squaring off strangle position {strangle_id}")
                    if not self.exit_strangle_position(strangle_id, f"Strategy exit: {reason}"):
                        success = False
            
            # Square off all safe OTM positions
            if hasattr(self, 'safe_otm_positions') and self.safe_otm_positions:
                print(f"Squaring off {len(self.safe_otm_positions)} safe OTM positions...")
                for position_id, position in list(self.safe_otm_positions.items()):
                    print(f"Squaring off safe OTM position {position_id}")
                    instrument_key = position['instrument_key']
                    quantity = position['quantity']
                    
                    # Place buy order to close position
                    order = place_order(
                        access_token=self.access_token,
                        instrument_token=instrument_key,
                        quantity=quantity,
                        transaction_type="BUY",
                        order_type="MARKET",
                        price=0,
                        product="MIS"
                    )
                    
                    if order and order.get('status') == 'success':
                        print(f"✅ Safe OTM position {position_id} squared off")
                    else:
                        print(f"❌ Failed to square off safe OTM position {position_id}")
                        success = False
            
            if success:
                # Reset strategy state
                self.active_positions.clear()
                self.entry_prices.clear()
                self.entry_straddle_prices.clear()
                # Clear strangle positions if they exist
                if hasattr(self, 'strangle_positions'):
                    self.strangle_positions.clear()
                
                # Clear safe OTM positions if they exist
                if hasattr(self, 'safe_otm_positions'):
                    self.safe_otm_positions.clear()
                
                # Clear scaled positions tracking
                if hasattr(self, 'scaled_positions'):
                    self.scaled_positions.clear()
                
                # Reset P&L tracking if strategy is stopped due to max loss
                if reason == "max_loss":
                    self.realized_pnl = 0
                    self.unrealized_pnl = 0
                    self.total_profit = 0
                
                # Handle different exit reasons
                if reason == "max_loss":
                    self.is_strategy_stopped = True
                    self.is_strategy_active = False
                    print("All positions squared off due to max loss - strategy stopped for the day")
                elif reason == "profit_target":
                    self.is_strategy_active = False
                    print("All positions squared off due to profit target achieved")
                else:
                    # Normal square off - keep strategy active for fresh start
                    print("All positions squared off successfully - ready for fresh start")
            
            return success
            
        except Exception as e:
            print(f"Error squaring off all positions: {e}")
            return False
    
    def start_fresh_straddle(self):
        """
        Start a fresh straddle at the current ATM strike after maximum deviation is reached.
        
        Returns:
            bool: True if fresh straddle started successfully
        """
        try:
            print(f"\n🔄 STARTING FRESH STRADDLE...")
            
            # Check if strategy is stopped due to max loss
            if self.is_strategy_stopped:
                print(f"🚫 Strategy is stopped due to max loss limit. No re-entry allowed for the day.")
                return False
            
            # Check if market is still open
            current_time = datetime.now()
            market_close_time = current_time.replace(hour=15, minute=15, second=0, microsecond=0)
            
            if current_time >= market_close_time:
                print(f"⏰ Market close time reached (3:15 PM). Cannot start fresh straddle.")
                return False
            
            # Get current ATM strike (market might have moved)
            new_atm_strike = self.get_atm_strike()
            print(f"📍 Current ATM strike: {new_atm_strike}")
            
            # Update original ATM for fresh start (new reference point)
            self.original_atm_strike = new_atm_strike
            print(f"📍 Updated original ATM reference: {self.original_atm_strike}")
            
            # Check if valid immediately
            if self.wait_for_valid_straddle_width(new_atm_strike):
                # Place new straddle at new ATM
                if self.place_short_straddle(new_atm_strike):
                    print(f"✅ Fresh straddle successfully started at ATM: {new_atm_strike}")
                    return True
                else:
                    return False
            else:
                # Just return False - main loop will retry later
                print(f"⏳ Conditions not yet met at {new_atm_strike}. Will retry naturally in next loop...")
                return False

                
        except Exception as e:
            print(f"Error starting fresh straddle: {e}")
            return False

    # --- WebSocket Streaming Integration Methods ---

    def _setup_streaming(self):
        """Initialize the Upstox WebSocket streamer and subscribe to base symbols"""
        try:
            # FIX: Check if we already have a shared streamer instance provided in __init__
            if self.streamer is not None:
                if self.verbose:
                    print("\n📡 Using existing WebSocket streamer instance...")
            else:
                print("\n📡 Initializing new WebSocket Streaming...")
                self.streamer = UpstoxStreamer(self.access_token)
            
            # Enable debug if configured
            if Config.is_streaming_debug():
                self.streamer.enable_debug(True)
            
            # Register callbacks (connect_market_data handles cases where it's already connected)
            self.streamer.connect_market_data(
                instrument_keys=list(self.subscribed_keys),
                mode="full", # Fetch full market data (OHLC, Greeks, etc.)
                on_message=self._on_market_data
            )
            
            # Also connect portfolio feed for real-time order status
            self.streamer.connect_portfolio(
                order_update=True,
                position_update=True,
                on_order=self._on_order_update
            )
            
            print("✅ WebSocket Streaming setup completed")
            return True
        except Exception as e:
            print(f"❌ Failed to setup WebSocket streaming: {e}")
            return False

    def _on_market_data(self, data):
        """Handle incoming market data packets and update the price cache (Full Mode supported)"""
        try:
            feeds = data.get('feeds', {})
            now = datetime.now()
            
            for instrument_key, feed_data in feeds.items():
                ltp = None
                
                # normalize key
                cache_key = instrument_key.replace(":", "|") if ":" in instrument_key else instrument_key
                
                # CRITICAL: Upstox V3 uses 'fullFeed' not 'full' or 'ff'
                # 1. Parse LTP (Support ltpc and fullFeed modes)
                if 'ltpc' in feed_data:
                    ltp = feed_data['ltpc'].get('ltp')
                elif 'fullFeed' in feed_data:
                    # Full feed structure: fullFeed -> marketFF -> ltpc -> ltp
                    ltp = feed_data['fullFeed'].get('marketFF', {}).get('ltpc', {}).get('ltp')
                
                # Update basic price cache
                if ltp is not None:
                    # Normalized key
                    self.price_cache[cache_key] = {
                        'price': float(ltp),
                        'time': now
                    }
                    # Original key (for safety)
                    self.price_cache[instrument_key] = {
                        'price': float(ltp),
                        'time': now
                    }

                # 2. Parse Detailed Data (Greeks & OHLC) - Only in fullFeed mode
                if 'fullFeed' in feed_data:
                    market_ff = feed_data['fullFeed'].get('marketFF', {})
                    
                    # Initialize detailed cache for this key if missing
                    if cache_key not in self.detailed_market_cache:
                        self.detailed_market_cache[cache_key] = {'greeks': {}, 'ohlc': {}, 'depth': {}}
                    
                    # Store Greeks (optionGreeks, NOT option_greeks)
                    if 'optionGreeks' in market_ff:
                        self.detailed_market_cache[cache_key]['greeks'] = market_ff['optionGreeks']
                    
                    # Store OHLC (marketOHLC -> ohlc array)
                    if 'marketOHLC' in market_ff:
                        market_ohlc = market_ff['marketOHLC']
                        if 'ohlc' in market_ohlc:
                            self.detailed_market_cache[cache_key]['ohlc'] = market_ohlc['ohlc']
                    
                    # Store Market Depth (optional - if you need bid/ask quotes)
                    if 'marketLevel' in market_ff:
                        market_level = market_ff['marketLevel']
                        if 'bidAskQuote' in market_level:
                            self.detailed_market_cache[cache_key]['depth'] = market_level['bidAskQuote']
                        
        except Exception as e:
            # Log error but don't block the callback
            # Increment error counter for monitoring
            if not hasattr(self, '_ws_error_count'):
                self._ws_error_count = 0
            self._ws_error_count += 1
            
            # Print error every 10 occurrences to avoid spam
            if self._ws_error_count % 10 == 1:
                print(f"⚠️ WebSocket feed error (count: {self._ws_error_count}): {str(e)[:100]}")

    def _on_order_update(self, order):
        """Handle real-time order status updates from portfolio stream"""
        order_id = order.get('order_id')
        status = order.get('status')
        symbol = order.get('trading_symbol')
        
        if status == 'complete':
            print(f"✅ Real-time Order Confirmed: {symbol} (ID: {order_id}) is FILLED")
        elif status == 'rejected':
            print(f"❌ Real-time Order REJECTED: {symbol} (Reason: {order.get('status_message')})")

    def _subscribe_to_instruments(self, instrument_keys):
        """Dynamically add instrument keys to the WebSocket stream"""
        # Guard: Don't try to subscribe if streamer isn't initialized yet
        if not self.streamer:
            # This can happen if get_current_prices() is called before run_strategy()
            # Just return silently - subscriptions will happen when streamer connects
            return
            
        if not instrument_keys:
            return
            
        new_keys = [k for k in instrument_keys if k and k not in self.subscribed_keys]
        if new_keys:
            if self.verbose:
                print(f"🛰️ Subscribing to {len(new_keys)} new instruments via WebSocket...")
            
            try:
                self.streamer.subscribe_market_data(new_keys, mode="full")
                self.subscribed_keys.update(new_keys)
            except Exception as e:
                print(f"⚠️ WebSocket subscription error: {e}")
    
    def run_strategy(self, check_interval_seconds=15, override_market_hours=False):
        """
        Run the short straddle strategy until market close (3:15 PM).
        
        Args:
            check_interval_seconds (int): Check interval in seconds
            override_market_hours (bool): Bypass market hours check for testing (default: False)
        """
        # Step 0: Setup Streaming - Initialize WebSocket and Price Cache
        self._setup_streaming()
        
        try:
            print(f"Starting Short Straddle Strategy until market close (3:15 PM)")
            print(f"Check interval: {check_interval_seconds} seconds")
            print(f"Profit target: ₹{self.profit_target}")
            print(f"Ratio threshold: {self.ratio_threshold}")
            
            # Get current ATM strike (market might have moved since initialization)
            current_atm = self.get_atm_strike()
            print(f"📍 Current ATM strike for strategy: {current_atm}")
            
            # OI Analysis: Get initial sentiment and recommendations
            if self.enable_oi_analysis:
                # In normal mode: Single-line OI summary
                if not self.verbose:
                    oi_sentiment = self.analyze_oi_sentiment(current_atm)
                    cumulative_analysis = self.get_cumulative_oi_analysis()
                    
                    if "error" not in cumulative_analysis:
                        sentiment_data = cumulative_analysis['sentiment_data']
                        overall_sentiment = sentiment_data.get('overall_sentiment', 'neutral')
                        sentiment_score = sentiment_data.get('sentiment_score', 50)
                        pcr = cumulative_analysis['cumulative_data'].get('pcr', 1.0)
                        
                        sentiment_emoji = "🟢" if overall_sentiment == "bullish_for_sellers" else "🔴" if overall_sentiment == "bearish_for_sellers" else "🟡"
                        print(f"{sentiment_emoji} OI: {overall_sentiment.replace('_', ' ').upper()} (Score:{sentiment_score:.0f} PCR:{pcr:.2f})")
                else:
                    # Debug mode: Detailed OI analysis
                    print("\n📊 OI ANALYSIS - INITIAL ASSESSMENT")
                    print("="*50)
                    
                    # Analyze current ATM sentiment
                    oi_sentiment = self.analyze_oi_sentiment(current_atm)
                    if "error" not in oi_sentiment:
                        print(f"📍 Strike {current_atm} OI Sentiment: {oi_sentiment['strike_sentiment']}")
                        print(f"📞 Call Activity: {oi_sentiment['call_oi_activity']} ({oi_sentiment['call_oi_change_pct']:+.1f}%)")
                        print(f"📞 Put Activity: {oi_sentiment['put_oi_activity']} ({oi_sentiment['put_oi_change_pct']:+.1f}%)")
                    
                    # Get selling recommendation
                    oi_recommendation = self.get_oi_selling_recommendation(current_atm)
                    if "error" not in oi_recommendation:
                        rec_emoji = "🟢" if oi_recommendation['recommendation'] in ["strong_sell", "sell"] else "🔴" if oi_recommendation['recommendation'] in ["strong_avoid", "avoid"] else "🟡"
                        print(f"🎯 OI Recommendation: {rec_emoji} {oi_recommendation['recommendation']} (Score: {oi_recommendation['selling_score']:.1f})")
                        print(f"💡 Reasoning: {oi_recommendation['reasoning']}")
                    
                    # CUMULATIVE OI ANALYSIS
                    print("\n📊 CUMULATIVE OI ANALYSIS - MULTI-STRIKE SENTIMENT")
                    print("="*50)
                
                # Cumulative OI details (debug mode only)
                if self.verbose:
                    cumulative_analysis = self.get_cumulative_oi_analysis()
                    if "error" not in cumulative_analysis:
                        cumulative_data = cumulative_analysis['cumulative_data']
                        sentiment_data = cumulative_analysis['sentiment_data']
                        trend_data = cumulative_analysis['trend_data']
                        
                        # Display cumulative analysis
                        overall_sentiment = sentiment_data.get('overall_sentiment', 'unknown')
                        sentiment_score = sentiment_data.get('sentiment_score', 50)
                        sentiment_strength = sentiment_data.get('sentiment_strength', 'unknown')
                        
                        sentiment_emoji = "🟢" if overall_sentiment == "bullish_for_sellers" else "🔴" if overall_sentiment == "bearish_for_sellers" else "🟡"
                        
                        print(f"📊 Overall Market Sentiment: {sentiment_emoji} {overall_sentiment.upper()} ({sentiment_strength})")
                        print(f"🎯 Cumulative Sentiment Score: {sentiment_score:.1f}/100")
                        print(f"📈 Total Call OI: {cumulative_data['total_call_oi']:,} ({cumulative_data['total_call_oi_change_pct']:+.1f}%)")
                        print(f"📉 Total Put OI: {cumulative_data['total_put_oi']:,} ({cumulative_data['total_put_oi_change_pct']:+.1f}%)")
                        print(f"📊 Put-Call Ratio: {cumulative_data['pcr']:.2f}")
                        print(f"📊 Net OI Change: {cumulative_data['net_oi_change']:+,} ({cumulative_data['net_oi_change_pct']:+.1f}%)")
                        print(f"📊 Overall Trend: {trend_data.get('overall_trend', 'unknown').replace('_', ' ').title()}")
                        
                        # Show high activity strikes
                        high_activity = trend_data.get('high_activity_strikes', [])
                        if high_activity:
                            print(f"🔥 High Activity Strikes:")
                            for strike_data in high_activity[:3]:  # Show top 3
                                strike = strike_data['strike']
                                call_change = strike_data['call_change_pct']
                                put_change = strike_data['put_change_pct']
                                print(f"   {strike}: Call {call_change:+.1f}%, Put {put_change:+.1f}%")
                    else:
                        print(f"❌ Cumulative OI Analysis Error: {cumulative_analysis['error']}")
                    
                    # Start OI monitoring
                    if self.start_oi_monitoring():
                        print("🔍 OI monitoring started successfully")
                    else:
                        print("⚠️  Failed to start OI monitoring")
                    
                    print("="*50)
                else:
                    # Normal mode: Just start monitoring silently
                    self.start_oi_monitoring()
            
            # OI-GUIDED STRANGLE ANALYSIS (debug mode only)
            if self.enable_oi_analysis and self.verbose:
                print("\n🎯 OI-GUIDED STRANGLE ANALYSIS")
                print("="*50)
                
                strangle_analysis = self.get_strangle_analysis()
                if "error" not in strangle_analysis:
                    # Display strangle analysis
                    ce_strike = strangle_analysis['optimal_ce_strike']
                    pe_strike = strangle_analysis['optimal_pe_strike']
                    recommendation = strangle_analysis['recommendation']
                    strangle_metrics = strangle_analysis['strangle_analysis']
                    
                    print(f"🎯 Optimal Strangle Selection:")
                    print(f"   CE Strike: {ce_strike['strike']} (Score: {ce_strike['call_selling_score']:.1f})")
                    print(f"   PE Strike: {pe_strike['strike']} (Score: {pe_strike['put_selling_score']:.1f})")
                    print(f"   Combined Score: {strangle_metrics['combined_selling_score']:.1f}/100")
                    
                    rec_emoji = "🟢" if recommendation['recommendation'] in ["strong_strangle", "strangle"] else "🔴" if recommendation['recommendation'] == "avoid" else "🟡"
                    print(f"📊 Strangle Recommendation: {rec_emoji} {recommendation['recommendation'].upper()}")
                    print(f"   Confidence: {recommendation['confidence'].title()}")
                    print(f"   Risk Level: {strangle_metrics['overall_risk_level'].title()}")
                    print(f"   Strangle Width: {strangle_metrics['strangle_width']} points")
                    print(f"   Combined Premium: ₹{strangle_metrics['combined_premium']:.2f}")
                    
                    # Check if we should enter strangle
                    should_enter_strangle, strangle_reason, strangle_confidence = self.should_enter_strangle(strangle_analysis)
                    print(f"🎯 Strangle Entry Decision: {'✅ ENTER' if should_enter_strangle else '❌ AVOID'}")
                    print(f"   Reason: {strangle_reason}")
                    print(f"   Confidence: {strangle_confidence}%")
                else:
                    print(f"❌ Strangle Analysis Error: {strangle_analysis['error']}")
                
                print("="*50)
            
            # OI-Enhanced Strike Selection
            if self.enable_oi_analysis:
                # Get optimal strike based on OI analysis
                optimal_strike, optimal_score, oi_rec = self.get_oi_optimal_strike()
                
                if self.verbose:
                    print("\n🎯 OI-ENHANCED STRIKE SELECTION")
                    print("="*50)
                    
                    if optimal_score > 60:  # Good OI conditions
                        print(f"✅ Using OI-optimized strike: {optimal_strike} (Score: {optimal_score:.1f})")
                    else:
                        print(f"⚠️  OI conditions not optimal (Score: {optimal_score:.1f}) - using ATM: {current_atm}")
                    
                    print("="*50)
                
                # Set entry strike based on OI score
                if optimal_score > 60:
                    entry_strike = optimal_strike
                else:
                    entry_strike = current_atm

            else:
                entry_strike = current_atm
            
            # Check for OI-Guided Strangle Entry (parallel strategy) - BEFORE straddle waiting
            if self.enable_oi_analysis:
                if self.verbose:
                    print(f"\n🎯 Checking for OI-Guided Strangle Entry...")
                    
                should_enter_strangle, strangle_reason, strangle_confidence = self.should_enter_strangle()
                
                if should_enter_strangle and strangle_confidence >= 50:  # Reduced from 70% to 50% for weak strangles
                    if self.verbose:
                        print(f"✅ Strangle Entry Conditions Met!")
                        print(f"   Reason: {strangle_reason}")
                        print(f"   Confidence: {strangle_confidence}%")
                    
                    # Place OI-guided strangle
                    if self.place_oi_guided_strangle():
                        print("🎯 OI-Guided Strangle placed successfully!")  # Always show success
                    else:
                        if self.verbose:
                            print("❌ Failed to place OI-Guided Strangle")
                elif self.verbose:
                    print(f"❌ Strangle Entry Conditions Not Met")
                    print(f"   Reason: {strangle_reason}")
                    print(f"   Confidence: {strangle_confidence}%")

            
            # Start main strategy loop immediately - all strategies run independently
            print(f"🚀 Starting 3-Strategy System: Straddle | Strangle | Safe OTM")
            if self.position_scaling_enabled:
                print(f"📈 Position Scaling: ENABLED (Max {self.max_scaling_level}x, Min {self.scaling_profit_threshold*100:.0f}% profit)")
            else:
                print(f"📈 Position Scaling: DISABLED")
            self.is_strategy_active = True
            
            # Set market close time (3:15 PM)
            current_time = datetime.now()
            market_close_time = current_time.replace(hour=15, minute=15, second=0, microsecond=0)
            
            # If current time is already past 3:15 PM, strategy should not run
            if current_time >= market_close_time and not override_market_hours:
                print(f"⏰ Market already closed (3:15 PM). Strategy cannot run.")
                print(f"Current time: {current_time.strftime('%H:%M:%S')}")
                print(f"Market close: {market_close_time.strftime('%H:%M:%S')}")
                return
            else:
                if override_market_hours:
                    print("⚠️  OVERRIDE: Running strategy after market hours for testing")
                print(f"Strategy will run until market close: {market_close_time.strftime('%H:%M:%S')}")
            
            while (datetime.now() < market_close_time or override_market_hours) and self.is_strategy_active and not self.is_strategy_stopped:
                # Display current positions in single line
                self.display_current_positions()
                
                # OI Monitoring Update (every 2nd iteration to reduce API calls)
                if self.enable_oi_analysis and hasattr(self, '_oi_check_counter'):
                    self._oi_check_counter += 1
                else:
                    self._oi_check_counter = 1
                
                # Show iteration counter every 20th iteration for debugging
                if self._oi_check_counter % 20 == 0:
                    if self.verbose:
                        print(f"🔄 Iteration {self._oi_check_counter} | Strategies: Straddle, Strangle, Safe OTM")
                        print(f"   📊 Straddle: {'ACTIVE' if not self.active_positions else f'{len(self.active_positions)} positions'}")
                        print(f"   🎯 Strangle: {'ENABLED' if self.enable_oi_analysis else 'DISABLED'} ({len(self.strangle_positions)} positions)")
                        print(f"   💰 Safe OTM: {'ENABLED' if self.safe_otm_enabled and self._is_nifty_expiry_day() else 'DISABLED'} ({len(self.safe_otm_positions)} positions)")
                
                if self.enable_oi_analysis and self._oi_check_counter % 3 == 0:  # Reduced frequency to avoid rate limits
                    try:
                        oi_update = self.get_oi_monitoring_update()
                        if "error" not in oi_update:
                            # Check for critical alerts only
                            if oi_update.get('alerts') and self.verbose:
                                critical_alerts = [a for a in oi_update['alerts'] if a.get('severity') == 'high']
                                if critical_alerts:
                                    print(f"🚨 OI ALERT: {len(critical_alerts)} critical alerts")
                            
                            # Check for recommendation changes
                            recommendations = oi_update.get('recommendations', {})
                            if recommendations and 'strike_recommendations' in recommendations and self.verbose:
                                avoid_strikes = [strike for strike, rec in recommendations['strike_recommendations'].items() 
                                               if rec['recommendation'] in ['strong_avoid', 'avoid']]
                                if avoid_strikes:
                                    print(f"⚠️  OI: Avoid strikes {avoid_strikes}")
                    except Exception as e:
                        pass  # Silent error handling
                
                # Check for straddle entry opportunities (every 2nd iteration for independent monitoring)
                if not self.active_positions and self._oi_check_counter % 2 == 0:
                    self.check_straddle_entry_opportunities()

                
                # Check max loss limit first (priority over profit target)
                if self.check_max_loss_limit():
                    print("🚨 Max loss limit reached. Closing all positions and stopping strategy.")
                    self.square_off_all_positions(reason="max_loss")
                    break
                
                # Check profit target
                if self.check_profit_target():
                    print("🎯 Profit target achieved. Closing all positions.")
                    self.square_off_all_positions(reason="profit_target")
                    break
                
                # Manage positions
                self.manage_positions()
                
                # Manage strangle positions (parallel strategy)
                if self.enable_oi_analysis and self.strangle_positions:
                    if self.verbose:
                        print(f"🎯 STRANGLE: Managing {len(self.strangle_positions)} positions...")
                    self.manage_strangle_positions()
                
                # Manage safe OTM positions (parallel strategy)
                if self.safe_otm_enabled and self.safe_otm_positions:
                    if self.verbose:
                        print(f"💰 SAFE OTM: Managing {len(self.safe_otm_positions)} positions...")
                    self.manage_safe_otm_positions()
                
                # Check for new strangle entry opportunities (every 2nd iteration to ensure regular checking)
                if self.enable_oi_analysis and self._oi_check_counter % 2 == 0:
                    self.check_continuous_strangle_entry()
                
                # Check for safe OTM opportunities (every 2nd iteration to ensure regular checking)
                if self.safe_otm_enabled and self._is_nifty_expiry_day() and self._oi_check_counter % 2 == 0:
                    self.check_safe_otm_opportunities()
                
                # Check for position scaling opportunities (every 5th iteration to avoid over-trading)
                if self.position_scaling_enabled and self._oi_check_counter % 5 == 0:
                    self.check_and_scale_positions()
                
                # Update dynamic risk parameters (every iteration for real-time adjustment)
                if self.dynamic_risk_enabled:
                    trailing_triggered = self.update_dynamic_risk_parameters()
                    if trailing_triggered:
                        print("🚨 Trailing stop triggered. Closing all positions.")
                        self.square_off_all_positions(reason="trailing_stop")
                        break
                
                # Wait for next check
                time.sleep(check_interval_seconds)
            
            # Square off all positions at market close
            if self.is_strategy_active:
                print("Market close time reached (3:15 PM). Squaring off all positions.")
                self.square_off_all_positions()
            
            # Print strategy summary
            self.print_strategy_summary()
            
        except KeyboardInterrupt:
            print("\n🛑 Strategy Interrupted by User (Ctrl+C)")
            # Emergency square off
            self.square_off_all_positions(reason="user_interrupt")
        except Exception as e:
            print(f"Error running strategy: {e}")
            # Emergency square off
            self.square_off_all_positions(reason="error")
    
    def print_strategy_summary(self):
        """
        Print strategy execution summary.
        """
        if not self.verbose:
            # Compact summary for non-verbose mode
            print("\n" + "="*60)
            print(f"STRATEGY COMPLETE | {self.underlying_symbol} | {len(self.trades_log)} Trades")
            print(f"P&L: ₹{self.total_profit:.2f} (Realized: ₹{self.realized_pnl:.2f} | Unrealized: ₹{self.unrealized_pnl:.2f})")
            if self.is_strategy_stopped:
                print("Status: STOPPED (Max Loss)")
            else:
                print("Status: COMPLETED")
            print("="*60)
            return
        
        # Detailed summary for verbose mode
        print("\n" + "="*60)
        print("SHORT STRADDLE STRATEGY SUMMARY")
        print("="*60)
        print(f"Underlying: {self.underlying_symbol}")
        print(f"Lot Size: {self.lot_size}")
        if self.dynamic_risk_enabled:
            print(f"Dynamic Profit Target: ₹{self.current_profit_target:.2f} (Base: ₹{self.base_profit_target})")
            print(f"Dynamic Stop Loss: ₹{self.current_stop_loss:.2f} (Base: ₹{self.base_stop_loss})")
            if self.trailing_stop_enabled:
                print(f"Trailing Stop: ₹{self.trailing_stop_level:.2f} (Highest Profit: ₹{self.highest_profit:.2f})")
        else:
            print(f"Profit Target: ₹{self.profit_target}")
        print(f"Max Loss Limit: ₹{self.max_loss_limit}")
        print(f"Ratio Threshold: {self.ratio_threshold}")
        print(f"Max Deviation: {self.max_deviation_points} points")
        print(f"Final Strike: {self.current_strike}")
        print(f"Total Trades: {len(self.trades_log)}")
        print(f"Realized P&L: ₹{self.realized_pnl:.2f}")
        print(f"Unrealized P&L: ₹{self.unrealized_pnl:.2f}")
        print(f"Total P&L: ₹{self.total_profit:.2f}")
        print(f"Strategy Status: {'STOPPED (Max Loss)' if self.is_strategy_stopped else 'COMPLETED'}")
        
        # Display scaling information
        if hasattr(self, 'scaled_positions') and self.scaled_positions:
            print(f"\n📈 Position Scaling Summary:")
            for strike, scaling_data in self.scaled_positions.items():
                scaling_level = scaling_data.get('scaling_level', 0)
                total_quantity = scaling_data.get('total_scaled_quantity', 0)
                if scaling_level > 0:
                    print(f"   Strike {strike}: Scaled to {scaling_level}x (Total quantity: {total_quantity})")
                    for history in scaling_data.get('scaling_history', []):
                        print(f"     Level {history['level']}: {history['reason']} at {history['timestamp'].strftime('%H:%M:%S')}")
        else:
            print(f"\n📈 Position Scaling: No positions were scaled")
        
        # OI Analysis Summary
        if self.enable_oi_analysis:
            print(f"\n📊 OI ANALYSIS SUMMARY:")
            print(f"OI Analysis: {'ENABLED' if self.enable_oi_analysis else 'DISABLED'}")
            if hasattr(self, 'oi_sentiment_history') and self.oi_sentiment_history:
                print(f"OI Sentiment Checks: {len(self.oi_sentiment_history)}")
            if hasattr(self, 'oi_alerts') and self.oi_alerts:
                print(f"OI Alerts Generated: {len(self.oi_alerts)}")
                high_alerts = len([alert for alert in self.oi_alerts if alert.get('severity') == 'high'])
                if high_alerts > 0:
                    print(f"High Severity Alerts: {high_alerts}")
            if hasattr(self, 'strangle_history') and self.strangle_history:
                print(f"Strangle Analysis History: {len(self.strangle_history)}")
            if hasattr(self, 'strangle_positions') and self.strangle_positions:
                print(f"Active Strangle Positions: {len(self.strangle_positions)}")
                for strangle_id, position in self.strangle_positions.items():
                    print(f"  - {strangle_id}: CE {position['ce_strike']} + PE {position['pe_strike']}")
            
            if hasattr(self, 'safe_otm_positions') and self.safe_otm_positions:
                print(f"Active Safe OTM Positions: {len(self.safe_otm_positions)}")
                for position_id, position in self.safe_otm_positions.items():
                    print(f"  - {position_id}: {position['strike']} {position['option_type']} (Score: {position['selling_score']:.1f}%)")
            
            if hasattr(self, 'safe_otm_history') and self.safe_otm_history:
                print(f"Safe OTM History: {len(self.safe_otm_history)} trades")
                total_safe_otm_pnl = sum(trade['pnl'] for trade in self.safe_otm_history)
                print(f"Total Safe OTM P&L: ₹{total_safe_otm_pnl:.2f}")
        
        # Count fresh starts
        fresh_starts = len([trade for trade in self.trades_log if 'SHORT_STRADDLE' in trade['action']])
        if fresh_starts > 1:
            print(f"Fresh Starts: {fresh_starts - 1} (due to deviation limits)")
        
        print(f"\nTrade Log:")
        for i, trade in enumerate(self.trades_log, 1):
            print(f"  {i}. {trade['timestamp'].strftime('%H:%M:%S')} - {trade['action']} - Strike: {trade['strike']}")
        
        print("="*60)


def run_short_straddle_strategy(access_token, nse_data, verbose=False, streamer=None, override_market_hours=False):
    """
    Main function to run the short straddle strategy.
    
    Args:
        access_token (str): Upstox access token
        nse_data (DataFrame): NSE market data
        verbose (bool): Enable verbose logging (default: False)
        streamer (UpstoxStreamer): Shared streamer instance
        override_market_hours (bool): Bypass market hours check for testing (default: False)
    """
    try:
        # Initialize strategy with OI analysis enabled
        strategy = ShortStraddleStrategy(
            access_token=access_token,
            nse_data=nse_data,
            underlying_symbol="NIFTY",
            lot_size=1,
            profit_target=3000,
            max_loss_limit=3000,  # Maximum loss limit
            ratio_threshold=0.8,
            straddle_width_threshold=0.25,  # 25% width threshold (increased from 20% for better market adaptability)
            max_deviation_points=200,  # Maximum 200 points deviation from ATM
            enable_oi_analysis=True,  # Enable OI analysis for enhanced decision making
            expiry_day_mode=False,  # Expiry day mode now automatically detected via _is_nifty_expiry_day()
            verbose=verbose,  # Control verbose logging
            streamer=streamer # Pass shared streamer instance
        )
        
        # Check initial margin availability before starting strategy
        if strategy.verbose:
            print("\n" + "="*60)
            print("INITIAL MARGIN CHECK")
            print("="*60)
        
        available_funds = strategy.get_available_funds("equity")
        if strategy.verbose:
            print(f"Available Equity Funds: ₹{available_funds:,.2f}")
        
        if available_funds < 10000:  # Minimum threshold for trading
            print(f"⚠️  WARNING: Low available funds (₹{available_funds:,.2f})")
            if strategy.verbose:
                print("   Strategy may not be able to place trades")
                print("   Consider adding more funds to your account")
        else:
            if strategy.verbose:
                print(f"✅ Sufficient funds available for trading")
        
        if strategy.verbose:
            print("="*60)
        
        # Run strategy until market close (3:15 PM) with 5-second checks
        strategy.run_strategy(check_interval_seconds=5, override_market_hours=override_market_hours)
        
    except Exception as e:
        print(f"Error running short straddle strategy: {e}")


if __name__ == "__main__":
    # This would be called from main.py with proper parameters
    print("Short Straddle Strategy Module")
    print("This module should be imported and used from main.py")

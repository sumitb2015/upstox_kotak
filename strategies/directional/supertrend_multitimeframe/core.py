# Supertrend Multi-Timeframe Strategy - Core Logic

import os
import sys
# Adjust Paths to root for direct execution
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))


import logging
import pandas as pd
from datetime import datetime
from typing import Optional, Tuple, Dict, Any

from lib.utils.indicators import calculate_supertrend
from lib.api.market_data import get_option_chain_atm
from lib.api.historical import get_intraday_data_v3, get_historical_data_v3
from lib.utils.expiry_cache import get_expiry_for_strategy
from datetime import datetime, timedelta

logger = logging.getLogger("SupertrendMultiTFCore")

class SupertrendStrategyCore:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
        # State
        self.nifty_token = "NSE_INDEX|Nifty 50"
        self.nifty_trend = 0  # 1 (Bullish), -1 (Bearish)
        self.nifty_st_val = 0.0
        
        self.option_tokens = {} # type: ignore
        self.active_position = None # {'type': 'CE'/'PE', 'token': '...', 'symbol': '...', 'qty': 0}
        
        # Cache
        self.last_nifty_update = None
        self.last_option_update = {} # type: ignore
        self.side_cooldowns = {'CE': None, 'PE': None} # Cooldown tracking
        
        # Profit Tracking (Hardening)
        self.max_profit_reached = 0.0
        self.locked_profit = 0.0

    def check_profit_goals(self, current_pnl: float, entry_premium: float) -> Tuple[bool, str]:
        """Check Max Loss and Profit Locking (Percentage-based)."""
        if entry_premium <= 0: return False, ""
        
        cfg = self.config
        pnl_pct = current_pnl / entry_premium
        
        # 1. Update High Water Mark
        if current_pnl > self.max_profit_reached:
            self.max_profit_reached = current_pnl
            
        # 2. Max Loss Check (Percentage of Premium)
        if pnl_pct <= -abs(cfg.get('max_loss_pct', 0.50)):
            return True, f"Max Loss Hit: {pnl_pct:.1%}"

        # 3. Profit Locking
        pl_cfg = cfg.get('profit_locking', {})
        if pl_cfg.get('enabled'):
            threshold_pct = pl_cfg.get('lock_threshold_pct', 0.20)
            max_pnl_pct = self.max_profit_reached / entry_premium
            
            if max_pnl_pct >= threshold_pct:
                # Determine Lock Ratio based on Tiers
                lock_ratio = 0.50 # Default 50%
                for tier_profit_pct, tier_ratio in pl_cfg.get('lock_tiers', []):
                    if max_pnl_pct >= tier_profit_pct:
                        lock_ratio = tier_ratio
                
                # Calculate Lock Amount (Trailing)
                lock_amt = self.max_profit_reached * lock_ratio
                
                # Ratchet: Locked profit never decreases
                if lock_amt > self.locked_profit:
                    self.locked_profit = lock_amt
                
                # Exit Check
                if current_pnl <= self.locked_profit:
                    return True, f"Profit Lock Hit: PnL {current_pnl:.2f} <= {self.locked_profit:.2f} (Locking {lock_ratio*100:.0f}% of Peak)"
        
        return False, ""

    def record_exit(self, side: str):
        """Record exit time to enforce cooldown."""
        self.side_cooldowns[side] = datetime.now()
        logger.info(f"⏳ Cooldown started for {side} (Wait {self.config.get('cooldown_minutes', 5)} mins)")

    def _parse_interval(self, interval_str: str) -> Tuple[str, int]:
        """Parse '3minute' into ('minute', 3)."""
        unit = "minute"
        val = 1
        if "minute" in interval_str:
            try:
                numeric_part = interval_str.replace("minute", "")
                val = int(numeric_part) if numeric_part else 1
            except:
                val = 1
        return unit, val

    def _calculate_indicators(self, df: pd.DataFrame) -> Tuple[int, float]:
        """Generic helper to calculate supertrend on a dataframe."""
        if df.empty: return 0, 0.0
        trend, value = calculate_supertrend(
            df, 
            period=self.config['st_period'], 
            multiplier=self.config['st_multiplier']
        )
        return trend, value

    def update_nifty_supertrend(self, access_token: str, df: Optional[pd.DataFrame] = None) -> None:
        """Update Nifty Supertrend status using either passed DF or API."""
        try:
            if df is None:
                interval_str = self.config['nifty_interval']
                unit, val = self._parse_interval(interval_str)
                candles = get_intraday_data_v3(access_token, self.nifty_token, unit, val)
                if not candles: return
                df = pd.DataFrame(candles)

            trend, value = self._calculate_indicators(df)
            self.nifty_trend = trend
            self.nifty_st_val = value
            self.last_nifty_update = datetime.now()
            
            trend_str = "BULLISH 🟢" if trend == 1 else "BEARISH 🔴"
            logger.info(f"📊 Nifty ST Updated: {trend_str} | Level: {value:.2f} | Close: {df.iloc[-1]['close']:.2f}")
            
        except Exception as e:
            logger.error(f"Error updating Nifty ST: {e}")

    def get_target_strike(self, access_token: str, option_type: str) -> Tuple[Optional[str], Optional[str], float]:
        """Find strike with premium closest to target_premium."""
        try:
            expiry = get_expiry_for_strategy(access_token, self.config['expiry_type'], "NIFTY")
            if not expiry: return None, None, 0.0
            
            # Fetch Chain
            chain = get_option_chain_atm(access_token, self.nifty_token, expiry, strikes_above=10, strikes_below=10)
            if chain.empty: return None, None, 0.0
            
            # Filter by Type
            df = chain[chain['instrument_type'] == option_type].copy()
            
            # Find closest to target premium
            target = self.config['target_premium']
            df['diff'] = abs(df['ltp'] - target)
            df = df.sort_values('diff')
            
            if df.empty: return None, None, 0.0
            
            best_match = df.iloc[0]
            token = best_match['instrument_key']
            # symbol = best_match['trading_symbol'] # MISSING in data
            ltp = best_match['ltp']
            strike = best_match['strike_price']
            expiry = best_match['expiry']
            
            logger.info(f"🎯 Selected {option_type} Strike: {strike} | Premium: {ltp} (Target: {target})")
            return token, strike, ltp, expiry
            
        except Exception as e:
            logger.error(f"Error selecting strike: {e}")
            return None, None, 0.0, None

    def calculate_option_supertrend(self, access_token: str, token: str, df: Optional[pd.DataFrame] = None) -> Tuple[int, float, float, int]:
        """Calculate Supertrend for a specific option token."""
        try:
            if df is None:
                interval_str = self.config['option_interval']
                unit, val = self._parse_interval(interval_str)
                
                # Fetch History (5 days) + Intraday
                to_date = datetime.now()
                from_date = to_date - timedelta(days=5)
                
                hist_candles = get_historical_data_v3(
                    access_token, token, unit, val, 
                    from_date.strftime('%Y-%m-%d'), to_date.strftime('%Y-%m-%d')
                )
                intra_candles = get_intraday_data_v3(access_token, token, unit, val)
                
                # Merge
                hist_df = pd.DataFrame(hist_candles) if hist_candles else pd.DataFrame()
                intra_df = pd.DataFrame(intra_candles) if intra_candles else pd.DataFrame()
                
                df = pd.DataFrame()
                if not hist_df.empty: df = hist_df
                if not intra_df.empty:
                    df = pd.concat([df, intra_df]).drop_duplicates(subset=['timestamp']).sort_values('timestamp') if not df.empty else intra_df
                    
                if df.empty: return 0, 0.0, 0.0

            trend, value = self._calculate_indicators(df)
            
            # 5. Calculate COMPLETED Candle Trend (Strict Close)
            # We strip the last candle (forming) and calc ST on the rest
            trend_completed = trend # Default to current if only 1 candle
            if len(df) > 1:
                df_completed = df.iloc[:-1]
                trend_completed, _ = self._calculate_indicators(df_completed)
            
            return int(trend), float(value), float(df.iloc[-1]['close']), int(trend_completed)
            
        except Exception as e:
            logger.error(f"Error calc Option ST: {e}")
            return 0, 0.0, 0.0

    def check_signals(self, access_token: str, nifty_df: Optional[pd.DataFrame] = None) -> Tuple[Optional[str], Optional[str], Optional[int], Optional[str], float]:
        """
        Check Entry Signals.
        Returns: (SignalType 'CE'/'PE', Token, Strike, Expiry)
        """
        # 0. Check Stale Data Only if df not provided manually
        if nifty_df is None:
            if not self.last_nifty_update or (datetime.now() - self.last_nifty_update).total_seconds() > 300:
                 logger.warning("⚠️ Nifty Data Stale (>5 mins). Skipping signals.")
                 return None, None, None, None, 0.0
        
        # 1. Update Nifty if df provided
        if nifty_df is not None:
             self.update_nifty_supertrend(access_token, nifty_df)

        # 2. Check Nifty Trend
        if self.nifty_trend == 0: return None, None, None, None, 0.0
        
        # 2. Setup based on Nifty
        target_type = "CE" if self.nifty_trend == -1 else "PE" # Short CE if Bearish, Short PE if Bullish
        
        # 2b. Check Cooldown
        last_exit = self.side_cooldowns.get(target_type)
        if last_exit:
            cooldown_mins = self.config.get('cooldown_minutes', 5)
            elapsed = (datetime.now() - last_exit).total_seconds() / 60
            if elapsed < cooldown_mins:
                # logger.info(f"⏳ Cooldown active for {target_type}: {elapsed:.1f}/{cooldown_mins} mins")
                return None, None, None, None, 0.0
            else:
                 # Clear cooldown if expired
                 self.side_cooldowns[target_type] = None
        
        # 3. Find Strike (Now returns LTP from Option Chain)
        token, strike, ltp, expiry = self.get_target_strike(access_token, target_type)
        if not token: return None, None, None, None, 0.0
        
        # 4. Check Option Trend
        opt_trend, opt_st, opt_close, _ = self.calculate_option_supertrend(access_token, token)
        
        # Use LIVE LTP for Entry Signal if available, else Candle Close
        check_price = ltp if ltp > 0 else opt_close
        
        # LOGIC: 
        # For Shorting, we want the Option to be WEAK (Bearish, Price < Supertrend)
        
        if opt_trend == -1: # Option is in Downtrend
             # Double check current Price vs ST
             if check_price < opt_st:
                 
                 # NEW: Check Minimum Gap (Safety)
                 # Gap % = (Supertrend - Price) / Price
                 gap_pct = (opt_st - check_price) / check_price
                 min_gap = self.config.get('min_entry_gap_pct', 0.01)
                 
                 if gap_pct < min_gap:
                     logger.info(f"⏳ Waiting: Signal valid but Gap too small ({gap_pct:.2%} < {min_gap:.2%}) | Price: {check_price} | ST: {opt_st:.2f}")
                     return None, None, None, None, 0.0
                 
                 logger.info(f"🚀 ENTRY SIGNAL: Nifty {self.nifty_trend} & {target_type} Supertrend Bearish ({check_price} < {opt_st}) | Gap: {gap_pct:.2%}")
                 return target_type, token, strike, expiry, check_price
        
        logger.info(f"⏳ Waiting: Nifty {target_type} aligned, but Option Trend is {opt_trend} (Price {check_price} vs ST {opt_st:.2f})")
        return None, None, None, None, 0.0

if __name__ == "__main__":
    from strategies.directional.supertrend_multitimeframe.config import CONFIG
    logging.basicConfig(level=logging.INFO)
    core = SupertrendStrategyCore(CONFIG)
    print("✅ SupertrendStrategyCore Initialized")
    print(f"Target underlying: {core.config['underlying']}")

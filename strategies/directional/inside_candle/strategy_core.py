import pandas as pd
from datetime import datetime
from typing import Optional, Dict

class InsideCandleAnalyzer:
    """
    Core Logic for Inside Candle Strategy (Cluster Support).
    Detects Inside Bar patterns and manages Signal State for multiple baby candles.
    """
    def __init__(self):
        self.mother_candle = None
        self.baby_candles = [] # Track all baby candles in the current cluster
        self.pattern_active = False
        self.signal_side = None # "BULLISH" or "BEARISH"
        
    def detect_pattern(self, df: pd.DataFrame) -> bool:
        """
        Check if the last closed candle fits into an Inside Bar pattern (New or Existing).
        
        Args:
            df: DataFrame containing historical candles.
            
        Returns:
            bool: True if we are strictly INSIDE a pattern (Active Waiting State).
        """
        if len(df) < 2:
            return False
            
        curr = df.iloc[-1]
        
        # 1. Check if we already have an active Mother Candle
        if self.pattern_active and self.mother_candle is not None:
             # We have a Master Mother. Check if Current is STILL inside Master Mother.
             # Only High/Low matters relative to Mother.
             # If curr breaks Mother high/low, the pattern is technically broken/breakout, 
             # BUT here we usually return False to let check_breakout handle it?
             # Or we return False saying "Not Inside anymore".
             
             mother_h = self.mother_candle['high']
             mother_l = self.mother_candle['low']
             
             is_still_inside = (curr['high'] < mother_h) and (curr['low'] > mother_l)
             
             if is_still_inside:
                 self.baby_candles.append(curr)
                 print(f"🕯️ Inside Cluster Grows! Baby #{len(self.baby_candles)}: {curr['time']}")
                 return True
             else:
                 # It broke out OR invalidated (e.g. engulfing mother? No, just outside range).
                 # We don't reset here immediately, we let check_breakout see the cross.
                 # ACTUALLY: detect_pattern runs ON CLOSE. check_breakout runs ON TICK.
                 # If we are here, the candle CLOSED.
                 # If it closed outside, the pattern might be over or triggered.
                 return False

        # 2. No active pattern. Check for NEW Mother-Baby Pair (Last 2 candles)
        # Prev = Potential Mother, Curr = Potential Baby
        prev = df.iloc[-2]
        
        is_inside = (curr['high'] < prev['high']) and (curr['low'] > prev['low'])
        
        if is_inside:
            self.mother_candle = prev
            self.baby_candles = [curr]
            self.pattern_active = True
            print(f"🕯️ New Master Mother Detected: {prev['time']} [H:{prev['high']}, L:{prev['low']}]")
            print(f"   Baby #1: {curr['time']}")
            return True
            
        return False
        
    def check_breakout(self, current_ltp: float) -> Optional[Dict]:
        """
        Check if current LTP breaks the *Master Mother Candle* levels.
        Returns Signal Dict if breakout occurs, else None.
        """
        if not self.pattern_active or self.mother_candle is None:
            return None
            
        mother_high = self.mother_candle['high']
        mother_low = self.mother_candle['low']
        
        # Bullish Breakout (Cross Above Master High)
        if current_ltp > mother_high:
            print(f"🚀 Bullish Breakout! LTP {current_ltp} > Mother High {mother_high}")
            signal = {
                "signal": "BUY", # Underlying Buy -> Short PE
                "type": "BULLISH",
                "trigger_price": current_ltp,
                "mother_high": mother_high,
                "mother_low": mother_low,
                "sl": mother_low # Spot SL for Bullish trade is Mother Low
            }
            # Pattern is consumed
            self.reset()
            return signal
            
        # Bearish Breakout (Cross Below Master Low)
        elif current_ltp < mother_low:
            print(f"🚀 Bearish Breakout! LTP {current_ltp} < Mother Low {mother_low}")
            signal = {
                "signal": "SELL", # Underlying Sell -> Short CE
                "type": "BEARISH",
                "trigger_price": current_ltp,
                "mother_high": mother_high,
                "mother_low": mother_low,
                "sl": mother_high # Spot SL for Bearish trade is Mother High
            }
            # Pattern is consumed
            self.reset()
            return signal
            
        return None
    
    def reset(self):
        """Reset state after signal or invalidation"""
        self.mother_candle = None
        self.baby_candles = []
        self.pattern_active = False

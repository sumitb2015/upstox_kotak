import pandas as pd
from datetime import datetime, timedelta
import logging

logger = logging.getLogger("TickAggregator")

class TickAggregator:
    """
    Aggregates real-time ticks into OHLC candles for multiple symbols.
    Supports fixed minute intervals (e.g., 1, 3, 5, 15).
    """
    def __init__(self, interval_minutes: int):
        self.interval_minutes = interval_minutes
        self.data = {} # {symbol: pd.DataFrame}
        self.active_candles = {} # {symbol: {ohlc}}
        
    def _get_candle_start(self, dt: datetime):
        """Align timestamp to the start of the interval."""
        minutes = (dt.minute // self.interval_minutes) * self.interval_minutes
        return dt.replace(minute=minutes, second=0, microsecond=0)

    def update_historical(self, symbol: str, df: pd.DataFrame):
        """Seed the aggregator with historical candles from REST."""
        if df.empty:
            return
        
        # Ensure timestamp column exists and is index
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            # Enforce tz-naive to match datetime.now()
            if df['timestamp'].dt.tz is not None:
                df['timestamp'] = df['timestamp'].dt.tz_localize(None)
            df.set_index('timestamp', inplace=True)
        elif not isinstance(df.index, pd.DatetimeIndex):
            try:
                df.index = pd.to_datetime(df.index)
                if df.index.tz is not None:
                    df.index = df.index.tz_localize(None)
            except:
                logger.error(f"Could not convert index to datetime for {symbol}")
                return

        self.data[symbol] = df.sort_index()
        logger.info(f"💾 Seeded {len(df)} historical candles for {symbol}")

    def add_tick(self, symbol: str, timestamp: datetime, price: float, volume: int = 0):
        """Add a new tick and update/rollover candles."""
        # Ensure input timestamp is tz-naive
        if timestamp.tzinfo is not None:
             timestamp = timestamp.replace(tzinfo=None)
             
        candle_start = self._get_candle_start(timestamp)
        
        if symbol not in self.active_candles:
            self.active_candles[symbol] = {
                'timestamp': candle_start,
                'open': price,
                'high': price,
                'low': price,
                'close': price,
                'volume': volume
            }
            return

        active = self.active_candles[symbol]
        
        # Check if we need to rollover
        if candle_start > active['timestamp']:
            # Move active to history
            new_row = pd.DataFrame([active]).set_index('timestamp')
            if symbol in self.data:
                # Remove any existing row with same timestamp before appending
                self.data[symbol] = self.data[symbol][~self.data[symbol].index.isin(new_row.index)]
                self.data[symbol] = pd.concat([self.data[symbol], new_row]).sort_index()
            else:
                self.data[symbol] = new_row
            
            # Start new candle
            self.active_candles[symbol] = {
                'timestamp': candle_start,
                'open': price,
                'high': price,
                'low': price,
                'close': price,
                'volume': volume
            }
            logger.debug(f"⏰ Candle Rollover for {symbol} at {candle_start}")
        else:
            # Update existing candle
            active['high'] = max(active['high'], price)
            active['low'] = min(active['low'], price)
            active['close'] = price
            active['volume'] += volume

    def get_dataframe(self, symbol: str) -> pd.DataFrame:
        """Get combined historical + active candle DataFrame."""
        hist_df = self.data.get(symbol, pd.DataFrame())
        active = self.active_candles.get(symbol)
        
        if not active:
            return hist_df
            
        active_df = pd.DataFrame([active]).set_index('timestamp')
        
        if hist_df.empty:
            if isinstance(active_df.index, pd.DatetimeIndex):
                return active_df.reset_index()
            return active_df
            
        # Combine
        # Avoid duplicate index if active is already partially in history
        combined = pd.concat([hist_df[~hist_df.index.isin(active_df.index)], active_df])
        combined = combined.sort_index()
        
        # Return with timestamp as column for consistency with component expectation
        if isinstance(combined.index, pd.DatetimeIndex):
            return combined.reset_index()
            
        return combined

    def clear(self, symbol: str):
        if symbol in self.data: del self.data[symbol]
        if symbol in self.active_candles: del self.active_candles[symbol]

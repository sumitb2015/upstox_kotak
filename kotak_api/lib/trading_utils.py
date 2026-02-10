"""
Trading utilities: Market data lookups, option helpers, and indicator calculations.

This module provides common trading utilities:
- Instrument token lookups
- Option strike token resolution
- Expiry date calculations
- Technical indicators (EMA, etc.)
"""

import pandas as pd
import logging
import re
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def get_instrument_token(broker, symbol, exchange='nse_cm'):
    """
    Get instrument token from master data.
    """
    if broker is None or broker.master_df is None or broker.master_df.empty:
        return None
        
    try:
        df = broker.master_df[broker.master_df['pExchSeg'].str.lower() == exchange.lower()]
        
        # For Nifty, use pTrdSymbol = 'NIFTY'
        if 'nifty' in symbol.lower():
            df = df[df['pTrdSymbol'].str.upper() == 'NIFTY']
        else:
            df = df[df['pSymbolName'] == symbol]
        
        if not df.empty:
            token = int(df.iloc[0]['pSymbol'])
            logger.info(f"Found token for {symbol}: {token}")
            return token
        else:
            # Fallback: search by contains
            df2 = broker.master_df[broker.master_df['pExchSeg'].str.lower() == exchange.lower()]
            df2 = df2[df2['pTrdSymbol'].str.contains(symbol.split()[0].upper(), case=False, na=False)]
            if not df2.empty:
                token = int(df2.iloc[0]['pSymbol'])
                logger.info(f"Found token (fallback) for {symbol}: {token}")
                return token
                
    except Exception as e:
        logger.error(f"Token lookup error for {symbol}: {e}")
        
    return None


def get_nearest_expiry(base_date=None, index_name="NIFTY"):
    """
    Get nearest weekly expiry (Thursday for NIFTY, Tuesday for FINNIFTY).
    """
    today = base_date or datetime.now()
    
    # NIFTY/BANKNIFTY = Thursday (3)
    # FINNIFTY = Tuesday (1)
    target_weekday = 3 
    if "FINNIFTY" in index_name.upper():
        target_weekday = 1
    
    days_ahead = (target_weekday - today.weekday()) % 7
    if days_ahead == 0 and today.hour >= 15:
        days_ahead = 7
    expiry_date = today + timedelta(days=days_ahead)
    return expiry_date.replace(hour=15, minute=30, second=0, microsecond=0)


def get_strike_token(broker, strike, option_type, expiry, symbol="NIFTY"):
    """
    Get option token for given strike (Supports Weekly & Monthly formats).
    """
    if broker is None or broker.master_df is None or broker.master_df.empty:
        return None, None

    # Format 1: Weekly (NIFTY 26 1 13 25750 CE) -> YY M dd Strike Type
    # M is 1-9 for Jan-Sep, O=Oct, N=Nov, D=Dec
    m_val = expiry.month
    if m_val <= 9:
        m_char = str(m_val)
    else:
        m_char = {10: 'O', 11: 'N', 12: 'D'}[m_val]
    
    yy = expiry.strftime('%y')
    dd = expiry.strftime('%d')
    
    weekly_symbol = f"{symbol}{yy}{m_char}{dd}{int(strike)}{option_type}"
    
    # Format 2: Monthly (NIFTY 26 JAN 25750 CE) -> YY MMM Strike Type
    monthly_symbol = f"{symbol}{yy}{expiry.strftime('%b').upper()}{int(strike)}{option_type}"
    
    # Try Weekly First
    try:
        # Check Weekly
        res = broker.master_df[(broker.master_df['pTrdSymbol'] == weekly_symbol) & (broker.master_df['pExchSeg'] == 'nse_fo')]
        if not res.empty:
            return int(res.iloc[0]['pSymbol']), weekly_symbol
            
        # Check Monthly
        res = broker.master_df[(broker.master_df['pTrdSymbol'] == monthly_symbol) & (broker.master_df['pExchSeg'] == 'nse_fo')]
        if not res.empty:
            return int(res.iloc[0]['pSymbol']), monthly_symbol
            
    except Exception as e:
        logger.error(f"Token lookup error: {e}")

    logger.error(f"Token not found for symbols: {weekly_symbol} or {monthly_symbol}")
    return None, None


def calculate_ema(data, period):
    """
    Calculate EMA (Exponential Moving Average) for given period.
    """
    if len(data) < period:
        return None
    
    # Convert to pandas Series for easy EMA calculation
    series = pd.Series(data)
    ema = series.ewm(span=period, adjust=False).mean()
    return ema.iloc[-1]


def calculate_sma(data, period):
    """
    Calculate SMA (Simple Moving Average) for given period.
    """
    if len(data) < period:
        return None
    
    return sum(data[-period:]) / period


def calculate_rsi(data, period=14):
    """
    Calculate RSI (Relative Strength Index).
    """
    if len(data) < period + 1:
        return None
    
    # Calculate price changes
    deltas = [data[i] - data[i-1] for i in range(1, len(data))]
    
    # Separate gains and losses
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    
    # Calculate average gain and loss
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    
    if avg_loss == 0:
        return 100
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi


# Strike Price Calculations
def get_atm_strike(spot_price, strike_interval=50):
    """
    Calculate ATM (At-The-Money) strike.
    """
    return round(spot_price / strike_interval) * strike_interval


def get_otm_strike(spot_price, option_type, offset_points=100, strike_interval=50):
    """
    Calculate OTM (Out-of-The-Money) strike.
    """
    atm = get_atm_strike(spot_price, strike_interval)
    
    if option_type.upper() == 'CE':
        return atm + offset_points
    else:  # PE
        return atm - offset_points


def get_itm_strike(spot_price, option_type, offset_points=100, strike_interval=50):
    """
    Calculate ITM (In-The-Money) strike.
    """
    atm = get_atm_strike(spot_price, strike_interval)
    
    if option_type.upper() == 'CE':
        return atm - offset_points
    else:  # PE
        return atm + offset_points


# Position & Value Calculations
def calculate_position_value(ltp, qty):
    """
    Calculate position value (LTP × Qty).
    """
    return ltp * abs(qty)


def calculate_imbalance(value1, value2):
    """
    Calculate percentage imbalance between two values.
    """
    max_val = max(value1, value2)
    if max_val == 0:
        return 0
    return abs(value1 - value2) / max_val * 100


# Swing Point Detection
def find_swing_high(candles, lookback=10):
    """
    Find recent swing high from candle data.
    """
    if len(candles) < lookback:
        return None
    
    recent_candles = list(candles)[-lookback:]
    return max(c['high'] for c in recent_candles if 'high' in c)


def find_swing_low(candles, lookback=10):
    """
    Find recent swing low from candle data.
    """
    if len(candles) < lookback:
        return None
    
    recent_candles = list(candles)[-lookback:]
    return min(c['low'] for c in recent_candles if 'low' in c)


def detect_swing_points(candles, lookback=10):
    """
    Detect both swing high and low.
    """
    swing_high = find_swing_high(candles, lookback)
    swing_low = find_swing_low(candles, lookback)
    
    return swing_high, swing_low


def parse_expiry_from_symbol(trading_symbol):
    """
    Parse expiry date from trading symbol (Weekly & Monthly).
    """
    sym = trading_symbol.upper()
    # Weekly: NIFTY<YY><M><DD><STRIKE><Type>
    m = re.match(r'NIFTY(\d{2})([1-9OND])(\d{2})(\d+)(CE|PE)', sym)
    if m:
        try:
            y, m_char, d = int(m.group(1)), m.group(2), int(m.group(3))
            months = {'1':1,'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,'O':10,'N':11,'D':12}
            return datetime(2000+y, months[m_char], d)
        except: pass
    # Monthly
    m = re.match(r'NIFTY(\d{2})([A-Z]{3})(\d+)(CE|PE)', sym)
    if m:
        try:
            d, m_str = int(m.group(1)), m.group(2)
            months = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
            now = datetime.now()
            dt = datetime(now.year, months[m_str], d)
            if dt < now: dt = datetime(now.year+1, months[m_str], d)
            return dt
        except: pass
    return None


def get_all_option_tokens(master_df, expiry_dt):
    """
    Get ALL option tokens for the expiry.
    """
    if master_df is None or master_df.empty:
        return [], {}

    df = master_df[(master_df['pExchSeg'] == 'nse_fo') & (master_df['pSymbolName'] == 'NIFTY')]
    df = df.copy()
    df['expiry_dt'] = df['pTrdSymbol'].apply(parse_expiry_from_symbol)
    df = df[df['expiry_dt'].dt.date == expiry_dt.date()]
    
    tokens = []
    options_map = {}
    
    for _, row in df.iterrows():
        try:
            strike = float(row['dStrikePrice;']) / 100.0
            token = int(row['pSymbol'])
            opt_type = row['pOptionType']
            sym = row['pTrdSymbol']
            
            item = {'token': token, 'strike': strike, 'type': opt_type, 'symbol': sym}
            tokens.append(item)
            options_map[token] = item
        except: pass
        
    return tokens, options_map


def get_lot_size(master_df, full_symbol):
    """
    Get lot size for the given symbol from master data.
    """
    try:
        df = master_df
        df = df[df['pTrdSymbol'].astype(str).str.strip().str.upper() == full_symbol.strip().upper()]
        if len(df) >= 1:
            possible_cols = ['lLotSize', 'lLotsize', 'pLotSize', 'pLotSize;']
            for col in possible_cols:
                if col in df.columns:
                    return int(df[col].iloc[0])
            logger.warning(f"Lot size column not found for {full_symbol}")
            return 75 # Default fallback for Nifty
        return 75 
    except Exception as e:
        logger.error(f"Error getting lot size: {e}")
        return 75

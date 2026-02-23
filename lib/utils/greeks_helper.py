import pandas as pd
from datetime import datetime
from typing import Dict, Optional, Tuple

# --- Lot Size Configuration (Standardized for 2026) ---
LOT_SIZE_MAP = {
    "NIFTY": 65,
    "BANKNIFTY": 30,
    "FINNIFTY": 40,
    "MIDCPNIFTY": 50,
    "SENSEX": 10
}

def calculate_gex_for_chain(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """
    Calculates CE GEX and PE GEX for a given option chain DataFrame.

    Formula (Standard 1% move Notional Exposure):
        GEX = Gamma × OI_shares × (0.01 × Spot) × Spot
        GEX = Gamma × OI_shares × Spot² / 100
        
    Result units: Raw Rupees (scaling to Cr is handled by Frontend formatCurrency)

    Sign convention:
        Call GEX = +positive  (MMs long gamma → suppress volatility)
        Put  GEX = -negative  (MMs short gamma → amplify volatility)
    Net GEX = Σ(Call GEX) + Σ(Put GEX)

    Note: Upstox OI is provided in total units (shares), so LotSize multiplication
    is NOT required if using absolute OI.
    """
    if df is None or df.empty:
        return df

    # --- Spot Price
    spot_price = 0
    if 'spot_price' in df.columns:
        spot_price = df['spot_price'].iloc[0]
    elif 'underlying_spot_price' in df.columns:
        spot_price = df['underlying_spot_price'].iloc[0]
        
    if spot_price <= 0:
        df['ce_gex'] = 0
        df['pe_gex'] = 0
        return df

    # Try to find lot size from dataframe, fall back to map or 1
    lot_size = 1
    if 'lot_size' in df.columns and df['lot_size'].iloc[0] > 0:
        lot_size = df['lot_size'].iloc[0]
    else:
        symbol_upper = symbol.upper()
        for key in LOT_SIZE_MAP:
            if key in symbol_upper:
                lot_size = LOT_SIZE_MAP[key]
                break

    # Normalization divisor: Use 400 to align with 0.25% notional move (Institutional Standard).
    # This represents the Gamma Exposure for a standard daily volatility move.
    DIVISOR = 400
    
    # GEX Formula: Gamma * OI * LotSize * (Spot^2 / 400)
    # The multiplier Q (Lot Size) converts contract/unit gamma into total notional exposure.
    spot_sq_norm = (spot_price ** 2) / DIVISOR
    scaler = spot_sq_norm * lot_size

    # Call GEX — positive
    if 'ce_gamma' in df.columns and 'ce_oi' in df.columns:
        df['ce_gex'] = df['ce_gamma'] * df['ce_oi'] * scaler
    else:
        df['ce_gex'] = 0

    # Put GEX — negative
    if 'pe_gamma' in df.columns and 'pe_oi' in df.columns:
        df['pe_gex'] = df['pe_gamma'] * df['pe_oi'] * scaler * -1
    else:
        df['pe_gex'] = 0
        
    return df

def get_net_gex(df: pd.DataFrame) -> float:
    """Returns the aggregate Net GEX for the entire chain."""
    if df is None or df.empty:
        return 0.0
    # Ensure columns exist
    ce_total = df['ce_gex'].sum() if 'ce_gex' in df.columns else 0
    pe_total = df['pe_gex'].sum() if 'pe_gex' in df.columns else 0
    return float(ce_total + pe_total)

def get_total_exposure(df: pd.DataFrame) -> float:
    """
    Calculates the Total Notional Exposure (OI * Spot).
    Used as a baseline for GEX percentage/magnitude checks.
    """
    if df is None or df.empty:
        return 0.0
    
    spot_price = 0
    if 'spot_price' in df.columns:
        spot_price = df['spot_price'].iloc[0]
    elif 'underlying_spot_price' in df.columns:
        spot_price = df['underlying_spot_price'].iloc[0]
        
    if spot_price <= 0:
        return 0.0
        
    total_oi = (df['ce_oi'].sum() if 'ce_oi' in df.columns else 0) + \
               (df['pe_oi'].sum() if 'pe_oi' in df.columns else 0)
               
    notional_rs = total_oi * spot_price
    return float(notional_rs) # Return raw Rupees (frontend handles Scaling to L Cr)

def calculate_flip_point(df: pd.DataFrame) -> float:
    """
    Calculates the 'Flip Point' (Zero Gamma Level).
    Standard Industry Methodology: Finding the strike where CUMULATIVE Net GEX crosses zero.
    This identifies the boundary between Positive and Negative Gamma regimes.
    """
    if df is None or df.empty or 'strike_price' not in df.columns:
        return 0.0
        
    # Prepare strike-wise Net GEX
    temp = df.copy()
    temp['net_strike_gex'] = temp.get('ce_gex', 0) + temp.get('pe_gex', 0)
    # Sort strictly from lowest strike to highest
    temp = temp.sort_values('strike_price')
    
    # Calculate Cumulative GEX (Running total)
    temp['cum_gex'] = temp['net_strike_gex'].cumsum()
    
    strikes = temp['strike_price'].values
    cum_vals = temp['cum_gex'].values
    
    # Finding zero crossing in Cumulative GEX via linear interpolation
    crossings = []
    for i in range(len(cum_vals) - 1):
        # Ignore starting zeroes/boundaries to find the REAL systemic flip
        if i == 0 and cum_vals[i] == 0:
            continue
            
        # Detect where sign flips from neg to pos OR pos to neg
        if (cum_vals[i] <= 0 and cum_vals[i+1] > 0) or (cum_vals[i] >= 0 and cum_vals[i+1] < 0):
            # Intersect formula: x = x1 + (0 - y1) * (x2 - x1) / (y2 - y1)
            x1, x2 = strikes[i], strikes[i+1]
            y1, y2 = cum_vals[i], cum_vals[i+1]
            if y2 != y1:
                flip = x1 + (0 - y1) * (x2 - x1) / (y2 - y1)
                crossings.append(flip)
                
    if not crossings:
        return 0.0
        
    # Institutional preference: Usually the boundary where the primary regime starts.
    # User's benchmark logic suggests the 'first' crossover from the bottom up.
    # This represents the significant systemic flip point.
    return round(float(crossings[0]), 2)

def prepare_snapshot(df: pd.DataFrame) -> pd.DataFrame:
    """Prepares a clean snapshot of Greeks for historical tracking."""
    cols_to_keep = [
        'strike_price', 'spot_price', 
        'ce_delta', 'pe_delta', 'ce_gamma', 'pe_gamma', 
        'ce_vega', 'pe_vega', 'ce_theta', 'pe_theta',
        'ce_gex', 'pe_gex',
        'ce_oi', 'pe_oi'
    ]
    
    # Fill missing columns with 0
    for col in cols_to_keep:
        if col not in df.columns:
            df[col] = 0
            
    snapshot = df[cols_to_keep].copy()
    snapshot['timestamp'] = datetime.now()
    return snapshot

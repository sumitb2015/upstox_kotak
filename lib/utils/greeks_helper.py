import pandas as pd
from datetime import datetime
from typing import Dict, Optional, Tuple

def calculate_gex_for_chain(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """
    Calculates CE GEX and PE GEX for a given option chain DataFrame.

    Formula (NSE standard — gamma is per 1-point move in spot):
        GEX = Gamma × OI × LotSize × Spot² / 1Cr
    Result units: Crore (₹ Cr)

    Sign convention:
        Call GEX = +positive  (MMs long gamma → suppress volatility)
        Put  GEX = -negative  (MMs short gamma → amplify volatility)
    Net GEX = Σ(Call GEX) + Σ(Put GEX)

    Lot size is read from the DataFrame ('lot_size' column from Upstox API).
    Falls back to get_lot_size() from instrument_utils if not available.
    """
    if df is None or df.empty:
        return df

    # --- Lot Size: read from DataFrame first (authoritative source from Upstox API)
    if 'lot_size' in df.columns and df['lot_size'].iloc[0] > 0:
        lot_size = int(df['lot_size'].iloc[0])
    else:
        # Fall back to the core utility function
        try:
            from lib.utils.instrument_utils import get_lot_size
            lot_size = get_lot_size(f"NSE_INDEX|{symbol}", None)
        except Exception:
            lot_size = 65  # last-resort default (matches NSE min lot)
        print(f"   [GEX] lot_size not in DataFrame for {symbol}, resolved to: {lot_size}")

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

    # NSE/Upstox gamma is per 1-point move in spot (not per 1% of spot).
    # Correct formula: Gamma × OI × LotSize × Spot²
    # Divide by 1Cr (1e7) to keep numbers display-friendly (output = GEX in Cr)
    CRORE = 1e7
    spot_sq = (spot_price ** 2) / CRORE

    # Call GEX — positive (market maker long gamma → suppresses moves)
    if 'ce_gamma' in df.columns and 'ce_oi' in df.columns:
        df['ce_gex'] = df['ce_gamma'] * df['ce_oi'] * lot_size * spot_sq
    else:
        df['ce_gex'] = 0

    # Put GEX — negative (market maker short gamma → amplifies moves)
    if 'pe_gamma' in df.columns and 'pe_oi' in df.columns:
        df['pe_gex'] = df['pe_gamma'] * df['pe_oi'] * lot_size * spot_sq * -1
    else:
        df['pe_gex'] = 0
        
    return df

def get_net_gex(df: pd.DataFrame) -> float:
    """Returns the total Net GEX for the entire chain."""
    if df is None or df.empty:
        return 0.0
    # Ensure columns exist
    ce_gex = df['ce_gex'].sum() if 'ce_gex' in df.columns else 0
    pe_gex = df['pe_gex'].sum() if 'pe_gex' in df.columns else 0
    return float(ce_gex + pe_gex)

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

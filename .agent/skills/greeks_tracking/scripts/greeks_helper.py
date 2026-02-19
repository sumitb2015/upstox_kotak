import pandas as pd
from datetime import datetime
from typing import Dict, Optional, Tuple

# Standard Lot Sizes
LOT_SIZES = {
    "NIFTY": 65,
    "BANKNIFTY": 30,
    "FINNIFTY": 65,
    "MIDCPNIFTY": 50,
    "SENSEX": 10
}

def calculate_gex_for_chain(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """
    Calculates CE GEX and PE GEX for a given option chain DataFrame.
    Formula: Gamma * OI * LotSize * (SpotPrice^2) * 0.01
    """
    if df is None or df.empty:
        return df

    lot_size = LOT_SIZES.get(symbol.upper(), 65)
    
    # Ensure spot price is available
    spot_price = 0
    if 'spot_price' in df.columns:
        spot_price = df['spot_price'].iloc[0]
    elif 'underlying_spot_price' in df.columns:
        spot_price = df['underlying_spot_price'].iloc[0]
        
    if spot_price <= 0:
        df['ce_gex'] = 0
        df['pe_gex'] = 0
        return df

    spot_sq = (spot_price ** 2) * 0.01

    # Call GEX
    if 'ce_gamma' in df.columns and 'ce_oi' in df.columns:
        df['ce_gex'] = df['ce_gamma'] * df['ce_oi'] * lot_size * spot_sq
    else:
        df['ce_gex'] = 0

    # Put GEX (Negative)
    if 'pe_gamma' in df.columns and 'pe_oi' in df.columns:
        df['pe_gex'] = df['pe_gamma'] * df['pe_oi'] * lot_size * spot_sq * -1
    else:
        df['pe_gex'] = 0
        
    return df

def get_net_gex(df: pd.DataFrame) -> float:
    """Returns the total Net GEX for the entire chain."""
    if df is None or df.empty:
        return 0.0
    return float(df['ce_gex'].sum() + df['pe_gex'].sum())

def prepare_snapshot(df: pd.DataFrame) -> pd.DataFrame:
    """Prepares a clean snapshot of Greeks for historical tracking."""
    cols_to_keep = [
        'strike_price', 'spot_price', 
        'ce_delta', 'pe_delta', 'ce_gamma', 'pe_gamma', 
        'ce_vega', 'pe_vega', 'ce_theta', 'pe_theta',
        'ce_gex', 'pe_gex',
        'ce_oi', 'pe_oi'
    ]
    
    for col in cols_to_keep:
        if col not in df.columns:
            df[col] = 0
            
    snapshot = df[cols_to_keep].copy()
    snapshot['timestamp'] = datetime.now()
    return snapshot

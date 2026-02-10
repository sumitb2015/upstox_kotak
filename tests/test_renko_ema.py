
import pytest
import numpy as np
import pandas as pd
from lib.utils.indicators import calculate_renko_ema

def test_renko_ema_basic():
    """Test basic EMA calculation on a list of brick closes."""
    # Simple uptrend: 10, 11, 12, 13, 14
    bricks = [10.0, 11.0, 12.0, 13.0, 14.0]
    period = 3
    
    # Manual EMA Calc:
    # EMA_today = (Value_today * (2/(n+1))) + (EMA_yesterday * (1-(2/(n+1))))
    # Multiplier = 2/(3+1) = 0.5
    
    # Brick 1 (10): SMA initial = 10 (if we start from there, but TA-Lib handles warmup)
    # TA-Lib behavior:
    # 0: NaN
    # 1: NaN
    # 2: SMA(10,11,12) = 11.0
    # 3: (13 * 0.5) + (11 * 0.5) = 6.5 + 5.5 = 12.0
    # 4: (14 * 0.5) + (12 * 0.5) = 7.0 + 6.0 = 13.0
    
    ema = calculate_renko_ema(bricks, period)
    assert ema == 13.0

def test_renko_ema_pandas_series():
    """Test that it accepts pandas Series."""
    bricks = pd.Series([10, 20, 30, 40, 50])
    period = 2
    # Multiplier = 2/3 = 0.666...
    # 0: NaN
    # 1: SMA(10, 20) = 15
    # 2: (30 * 2/3) + (15 * 1/3) = 20 + 5 = 25
    # 3: (40 * 2/3) + (25 * 1/3) = 26.66 + 8.33 = 35
    # 4: (50 * 2/3) + (35 * 1/3) = 33.33 + 11.66 = 45
    
    ema = calculate_renko_ema(bricks, period)
    assert abs(ema - 45.0) < 0.1

def test_renko_ema_numpy_array():
    """Test that it accepts numpy array."""
    bricks = np.array([100, 105, 110, 115])
    ema = calculate_renko_ema(bricks, 3)
    assert isinstance(ema, float)
    assert ema > 0

def test_renko_ema_insufficient_data():
    """Test error handling for insufficient data."""
    bricks = [10, 20]
    with pytest.raises(ValueError, match="Insufficient brick data"):
        calculate_renko_ema(bricks, 5)

def test_renko_ema_empty_input():
    """Test error handling for empty input."""
    with pytest.raises(ValueError, match="Input data is empty"):
        calculate_renko_ema([], 5)

def test_renko_ema_invalid_type():
    """Test error handling for invalid input type."""
    with pytest.raises(ValueError, match="Unsupported input type"):
         calculate_renko_ema("invalid", 5)

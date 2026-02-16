# Aggressive Renko Dip Strategy Rules

## Overview
This is an aggressive version of the Renko Dip strategy, optimized for Nifty. It utilizes 5-point Renko bricks and RSI filters for momentum-based scalping and trend following.

## Core Logic

### Indicators
1.  **Signal Renko**: 5-point bricks on Nifty Spot/Futures.
2.  **Renko EMA (10)**: Exponential Moving Average calculated directly on Renko brick closes.
3.  **RSI (14)**: Calculated on 1-minute standard candles.
4.  **Market Regime Filter**: Monitors reversal frequency in the last 20 bricks (Max 40% reversals allowed).
5.  **Option Renko (Premium Trail)**: Dynamic brick size (5% of premium) used for TSL and Pyramiding.

### Entry Rules
*   **Bullish (Sell PE)**: 
    - 2 consecutive **Green Bricks**.
    - **RSI > 50** (Bullish momentum).
    - **Renko Close > EMA (10)** (Trend alignment).
    - **Market Regime**: Trending (< 40% reversals).
*   **Bearish (Sell CE)**: 
    - 2 consecutive **Red Bricks**.
    - **RSI < 50** (Bearish momentum).
    - **Renko Close < EMA (10)** (Trend alignment).
    - **Market Regime**: Trending (< 40% reversals).

### Pyramiding (Adding Units)
- **Trigger**: Forms every `pyramid_interval` (default: 1) **RED bricks** (moving in profit direction) on the **Option Renko** chart.
- **Limit**: Max 3 lots total (Initial + 2 Pyramids).
- **Safety**: Only pyramids if available funds > required margin.

### Exit Rules
1.  **Stop Loss (TSL)**: 
    - **Staircase Mode**: TSL price updates ONLY when a full RED brick forms on the Option Renko.
    - **Brick Count (3)**: Exit if 3 consecutive GREEN bricks (premium rising) form against the short.
    - **Wait for Candle Close**: TSL execution is evaluated at the close of the 1-minute candle.
2.  **Profit Target**: Fixed exit after 6 Option Bricks of movement in favor.
3.  **Hard Time Exit**: All positions are squared off at **15:15 PM**.

## File Structure
- `config.py`: Brick sizes, RSI/EMA settings, and TSL sensitivity.
- `core.py`: Mathematical logic for Renko construction, momentum, and regime filters.
- `live.py`: WebSocket integration, margin safety checks, and Kotak order execution.
- `strategy_state.json`: Persistent state for crash recovery.

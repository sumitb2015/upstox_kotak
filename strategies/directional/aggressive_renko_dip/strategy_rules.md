# Aggressive Renko Dip Strategy Rules

## Overview
This is an aggressive version of the Renko Dip strategy. It removes the Macro (Mega) trend filter to allow for more frequent trading opportunities based solely on 10-point Renko momentum and RSI.

## Core Logic

### Indicators
1.  **Signal Renko**: 10-point bricks on Nifty Spot/Futures.
2.  **RSI (14)**: 1-minute interval RSI.
3.  **Premium Trail Renko**: Dynamic brick size (~8% of premium) used for trailing stop loss.

### Entry Rules
*   **Bullish**: 2 consecutive Green Bricks + RSI > 50.
    *   **Action**: Sell ATM/OTM Put (PE).
*   **Bearish**: 2 consecutive Red Bricks + RSI < 50.
    *   **Action**: Sell ATM/OTM Call (CE).

### Pyramiding (Adding Units)
*   **Trend Continuation**: If Signal Renko prints additional bricks in the direction of the active trade.
*   **Interval**: Add 1 lot every `resumption_streak` (default: 2) bricks.
*   **Action**: Add 1 more lot (Max 3 lots total).

### Exit Rules
1.  **Structural Reversal**: Signal Renko prints bricks in the opposite direction (Requires 2x brick size reversal).
2.  **Premium Trail (TSL)**: 2 consecutive Green bricks (raising premium) on the Option's Renko chart.
3.  **Time Exit**: 15:15 PM.

## File Structure
- `config.py`: Brick sizes, RSI settings, and risk parameters.
- `core.py`: Pure logic for Renko calculation and signal detection.
- `live.py`: Real-time execution wrapper.

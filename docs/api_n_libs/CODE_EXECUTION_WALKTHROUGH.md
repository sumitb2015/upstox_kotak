# Upstox Trading Strategy - Code Execution Walkthrough

This document provides a comprehensive walkthrough of the code execution flow for the Upstox Short Straddle/Strangle trading strategy.

## 📊 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         main.py                                  │
│                    (Entry Point)                                 │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
        ┌────────────────────────────────────────┐
        │  1. Authentication (core/authentication.py) │
        │     - Check existing token              │
        │     - Auto-login with TOTP if needed    │
        └────────────────┬───────────────────────┘
                         │
                         ▼
        ┌────────────────────────────────────────┐
        │  2. Market Data Download                │
        │     (api/market_data.py)                │
        │     - Fetch NSE instrument data         │
        │     - Detect dynamic lot sizes          │
        └────────────────┬───────────────────────┘
                         │
                         ▼
        ┌────────────────────────────────────────┐
        │  3. Market Validation                   │
        │     (utils/market_validation.py)        │
        │     - Check market hours                │
        │     - Validate ATM strike               │
        └────────────────┬───────────────────────┘
                         │
                         ▼
        ┌────────────────────────────────────────┐
        │  4. Strategy Execution                  │
        │     (strategies/straddle_strategy.py)   │
        │     - Initialize pivot levels           │
        │     - Run main strategy loop            │
        └────────────────┬───────────────────────┘
                         │
                         ▼
                  [Strategy Loop]
```

## 🔄 Strategy Execution Flow

```
┌─────────────────────────────────────────────────────────────────┐
│              ShortStraddleStrategy.__init__()                    │
│  - Detect market lot size (e.g., NIFTY = 65)                    │
│  - Calculate CPR and Camarilla pivot levels                     │
│  - Initialize OI analyzers (if enabled)                         │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                   run_strategy() - Main Loop                     │
│  Runs every 15 seconds until market close (3:15 PM)             │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
        ┌────────────────────────────────────────┐
        │  Step 1: OI Analysis (if enabled)      │
        │  - Fetch option chain data             │
        │  - Analyze cumulative OI sentiment     │
        │  - Identify optimal strikes            │
        └────────────────┬───────────────────────┘
                         │
                         ▼
        ┌────────────────────────────────────────┐
        │  Step 2: Check Entry Opportunities     │
        │  ┌──────────────────────────────────┐  │
        │  │ A. OI-Guided Strangle Entry      │  │
        │  │    - Analyze CE/PE scores        │  │
        │  │    - Place if score > 60         │  │
        │  └──────────────────────────────────┘  │
        │  ┌──────────────────────────────────┐  │
        │  │ B. Straddle Entry                │  │
        │  │    - Check width threshold       │  │
        │  │    - Verify CE/PE ratio > 0.8    │  │
        │  │    - Place simultaneous orders   │  │
        │  └──────────────────────────────────┘  │
        │  ┌──────────────────────────────────┐  │
        │  │ C. Safe OTM Entry (Expiry Day)   │  │
        │  │    - Check premium/OI criteria   │  │
        │  │    - Place individual CE/PE      │  │
        │  └──────────────────────────────────┘  │
        └────────────────┬───────────────────────┘
                         │
                         ▼
        ┌────────────────────────────────────────┐
        │  Step 3: Monitor Active Positions      │
        │  - Fetch current LTP for all positions │
        │  - Calculate real-time P&L             │
        │  - Display position summary            │
        └────────────────┬───────────────────────┘
                         │
                         ▼
        ┌────────────────────────────────────────┐
        │  Step 4: Risk Management               │
        │  ┌──────────────────────────────────┐  │
        │  │ A. Profit Target Check           │  │
        │  │    - Exit if P&L > ₹3000         │  │
        │  └──────────────────────────────────┘  │
        │  ┌──────────────────────────────────┐  │
        │  │ B. Max Loss Check                │  │
        │  │    - Exit if P&L < -₹3000        │  │
        │  └──────────────────────────────────┘  │
        │  ┌──────────────────────────────────┐  │
        │  │ C. Ratio Management              │  │
        │  │    - Exit losing side if < 0.6   │  │
        │  └──────────────────────────────────┘  │
        │  ┌──────────────────────────────────┐  │
        │  │ D. Trailing Stop Loss            │  │
        │  │    - Lock profits at 30%/50%/70% │  │
        │  └──────────────────────────────────┘  │
        └────────────────┬───────────────────────┘
                         │
                         ▼
        ┌────────────────────────────────────────┐
        │  Step 5: Position Scaling (Optional)   │
        │  - Add to winning positions            │
        │  - Max 3x scaling allowed              │
        └────────────────┬───────────────────────┘
                         │
                         ▼
                  [Loop continues]
                         │
                         ▼
        ┌────────────────────────────────────────┐
        │  Market Close (3:15 PM)                │
        │  - Square off all positions            │
        │  - Display final P&L                   │
        └────────────────────────────────────────┘
```

## 🧩 Module Interaction Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        CORE MODULES                              │
├─────────────────────────────────────────────────────────────────┤
│  core/authentication.py  │  core/config.py  │  core/.env        │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                         API LAYER                                │
├─────────────────────────────────────────────────────────────────┤
│  api/market_data.py      │  Fetch option chains, historical data│
│  api/market_quotes.py    │  Get LTP, OHLC, Greeks               │
│  api/order_management.py │  Place/modify/cancel orders          │
│  api/streaming.py        │  WebSocket market data (V3 Protobuf) │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                      ANALYSIS LAYER                              │
├─────────────────────────────────────────────────────────────────┤
│  analysis/oi_analysis.py          │  Strike-level OI sentiment  │
│  analysis/cumulative_oi_analysis.py│  Multi-strike OI trends    │
│  analysis/oi_strangle_analyzer.py │  Optimal strangle selection │
│  analysis/oi_monitoring.py        │  Real-time OI tracking      │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                      STRATEGY LAYER                              │
├─────────────────────────────────────────────────────────────────┤
│  strategies/straddle_strategy.py  │  Main strategy logic        │
│  - Entry logic (Straddle/Strangle/OTM)                          │
│  - Exit logic (Profit/Loss/Ratio)                               │
│  - Position management                                           │
│  - Risk management                                               │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                       UTILITY LAYER                              │
├─────────────────────────────────────────────────────────────────┤
│  utils/instrument_utils.py   │  Strike/instrument key mapping   │
│  utils/margin_calculator.py  │  Margin requirement calculation  │
│  utils/funds_margin.py       │  Available funds check           │
│  utils/market_validation.py  │  Market hours/conditions check   │
└─────────────────────────────────────────────────────────────────┘
```

## 📈 Order Placement Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    Order Placement Decision                      │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
        ┌────────────────────────────────────────┐
        │  1. Validate Entry Conditions          │
        │     - Check ratio (CE/PE > 0.8)        │
        │     - Check width threshold            │
        │     - Verify OI sentiment              │
        └────────────────┬───────────────────────┘
                         │
                         ▼
        ┌────────────────────────────────────────┐
        │  2. Get Instrument Keys                │
        │     (utils/instrument_utils.py)        │
        │     - Map strike to NSE_FO keys        │
        └────────────────┬───────────────────────┘
                         │
                         ▼
        ┌────────────────────────────────────────┐
        │  3. Calculate Quantity                 │
        │     quantity = lot_size * market_lot   │
        │     Example: 1 * 65 = 65 units         │
        └────────────────┬───────────────────────┘
                         │
                         ▼
        ┌────────────────────────────────────────┐
        │  4. Validate Margin                    │
        │     (utils/margin_calculator.py)       │
        │     - Check available funds            │
        │     - Verify margin requirement        │
        └────────────────┬───────────────────────┘
                         │
                         ▼
        ┌────────────────────────────────────────┐
        │  5. Place Orders                       │
        │     (api/order_management.py)          │
        │     ┌──────────────────────────────┐   │
        │     │ Option A: Multi-Order API    │   │
        │     │  - Simultaneous CE + PE      │   │
        │     │  - Faster execution          │   │
        │     └──────────────────────────────┘   │
        │     ┌──────────────────────────────┐   │
        │     │ Option B: Sequential Orders  │   │
        │     │  - Place CE first            │   │
        │     │  - Then place PE             │   │
        │     └──────────────────────────────┘   │
        └────────────────┬───────────────────────┘
                         │
                         ▼
        ┌────────────────────────────────────────┐
        │  6. Store Position Data                │
        │     - Order IDs                        │
        │     - Entry prices                     │
        │     - Instrument keys                  │
        │     - Timestamp                        │
        └────────────────────────────────────────┘
```

## 🎯 OI Analysis Integration

```
┌─────────────────────────────────────────────────────────────────┐
│                   OI Analysis Workflow                           │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
        ┌────────────────────────────────────────┐
        │  1. Fetch Option Chain                 │
        │     (api/market_data.py)               │
        │     - Get CE/PE data for 5 strikes     │
        │     - Extract OI, prev_OI, LTP         │
        └────────────────┬───────────────────────┘
                         │
                         ▼
        ┌────────────────────────────────────────┐
        │  2. Classify OI Activity               │
        │     (analysis/oi_analysis.py)          │
        │     ┌──────────────────────────────┐   │
        │     │ Price ↑ + OI ↑ = Long Build  │   │
        │     │ Price ↓ + OI ↑ = Short Build │   │
        │     │ Price ↓ + OI ↓ = Long Unwind │   │
        │     │ Price ↑ + OI ↓ = Short Cover │   │
        │     └──────────────────────────────┘   │
        └────────────────┬───────────────────────┘
                         │
                         ▼
        ┌────────────────────────────────────────┐
        │  3. Calculate Strike Scores            │
        │     (analysis/oi_strangle_analyzer.py) │
        │     - CE selling score (0-100)         │
        │     - PE selling score (0-100)         │
        │     - Confidence level                 │
        └────────────────┬───────────────────────┘
                         │
                         ▼
        ┌────────────────────────────────────────┐
        │  4. Cumulative Sentiment               │
        │     (analysis/cumulative_oi_analysis.py)│
        │     - Aggregate OI across strikes      │
        │     - Determine market bias            │
        │     - Calculate Put-Call Ratio         │
        └────────────────┬───────────────────────┘
                         │
                         ▼
        ┌────────────────────────────────────────┐
        │  5. Strategy Decision                  │
        │     - If combined score > 60: ENTER    │
        │     - If score 40-60: WAIT             │
        │     - If score < 40: AVOID             │
        └────────────────────────────────────────┘
```

## 🔧 Key Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `lot_size` | 1 | Number of lots to trade |
| `market_lot` | Dynamic | Units per lot (auto-detected, e.g., 65 for NIFTY) |
| `profit_target` | ₹3000 | Exit when profit reaches this |
| `max_loss_limit` | ₹3000 | Exit when loss reaches this |
| `ratio_threshold` | 0.6 | Exit losing side if CE/PE ratio < this |
| `straddle_width_threshold` | 0.25 | Max allowed (CE-PE)/CE difference |
| `check_interval_seconds` | 15 | How often to check positions |
| `enable_oi_analysis` | True | Use OI for entry decisions |

## 📝 Execution Example (Live Run)

```
11:42:04 - Authentication successful
11:42:05 - NSE data loaded (88,184 instruments)
11:42:06 - Market lot detected: 65 units
11:42:07 - Pivot levels calculated (CPR, Camarilla)
11:42:08 - OI Analysis: BEARISH_FOR_SELLERS (Score: 35/100)
11:42:10 - Strangle opportunity identified (Score: 65/100)
11:42:12 - Placing CE 25700 SELL order (65 units)
11:42:13 - Order placed: ID 260115000001810
11:42:14 - Placing PE 25450 SELL order (65 units)
11:42:15 - Order placed: ID 260115000001811
11:42:17 - Position monitoring started
11:42:17 - STRANGLE 25700_25450: P&L ₹0
[Loop continues every 15 seconds until 3:15 PM or manual exit]
```

## 🚀 Future Enhancements

- **WebSocket Integration**: Replace polling with real-time tick data using `api/streaming.py`
- **Machine Learning**: Integrate ML models for OI pattern recognition
- **Multi-Symbol Support**: Extend to BANKNIFTY, FINNIFTY
- **Backtesting Framework**: Historical strategy validation
- **Alert System**: SMS/Email notifications for critical events

---

**Last Updated**: 2026-01-15  
**Version**: 2.0  
**Author**: Upstox Strategy Team

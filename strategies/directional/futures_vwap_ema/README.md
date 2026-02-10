# Futures VWAP EMA Options Selling Strategy

## Overview

A directional options selling strategy that uses Nifty Futures technical indicators (VWAP and 20 EMA) to time option entries, with pyramiding capabilities and dynamic trailing stop loss.

## Strategy Logic

### Entry Signals

**Call Option (CE) Entry:**
- Sell ATM+150 CE when:
  - Futures price < VWAP
  - Futures price < 20 EMA

**Put Option (PE) Entry:**
- Sell ATM-150 PE when:
  - Futures price > VWAP
  - Futures price > 20 EMA

### Pyramiding

- **Trigger:** Add 1 lot when any existing position reaches 10% profit
- **Maximum Levels:** 2 pyramid levels (total 3 positions max)
- **Lot Size:** 1 lot per entry/pyramid
- **Profit Calculation:** Per-position profit percentage

### Trailing Stop Loss (TSL)

Dynamic TSL that tightens as positions are pyramided:

| Pyramid Level | TSL from Lowest Price |
|---------------|----------------------|
| Level 0 (Initial) | 20% |
| Level 1 (First Pyramid) | 15% |
| Level 2 (Second Pyramid) | 10% |

### Exit Conditions

1. **TSL Hit:** Option price rises more than TSL% from lowest price
2. **VWAP Cross:** 
   - CE positions: Exit when futures crosses above VWAP
   - PE positions: Exit when futures crosses below VWAP
3. **Time Exit:** Force exit at 15:15 before market close

## Configuration

Edit `config.py` to customize strategy parameters:

```python
CONFIG = {
    'candle_interval_minutes': 3,      # Candle timeframe
    'lot_size': 1,                     # Lots per entry
    'max_pyramid_levels': 2,           # Maximum pyramids
    'atm_offset_ce': 150,              # CE: ATM+150
    'atm_offset_pe': -150,             # PE: ATM-150
    'ema_period': 20,                  # EMA period
    'pyramid_profit_pct': 0.10,        # 10% profit to pyramid
    'base_trailing_sl_pct': 0.20,      # Base TSL 20%
    'tsl_tightening_pct': 0.05,        # Reduce 5% per level
    'dry_run': True,                   # Set False for live trading
}
```

## Usage

### Prerequisites

1. **Authentication:** Ensure you have a valid Upstox access token
2. **Dependencies:** All required packages installed (see `requirements.txt`)
3. **Market Data:** NSE market data accessible

### Running the Strategy

```bash
# Navigate to project directory
cd c:\algo\upstox

# Activate virtual environment
.\venv\Scripts\activate

# Run the strategy
python strategies/futures_vwap_ema/live.py
```

### Dry Run (Paper Trading)

Set `dry_run: True` in `config.py` to test without placing real orders:

```python
CONFIG = {
    ...
    'dry_run': True,
}
```

### Live Trading

⚠️ **Warning:** Live trading involves real money. Test thoroughly in dry run mode first.

```python
CONFIG = {
    ...
    'dry_run': False,
    'product_type': 'D',  # 'D' for Intraday
}
```

## Features

### ✅ Reuses Existing Helper Functions

- **Authentication:** `core/authentication.py`
- **Market Data:** `api/market_data.py`
- **Historical Data:** `api/historical.py`
- **Streaming:** `api/streaming.py`
- **Order Management:** `api/order_management.py`
- **Instrument Utils:** `utils/instrument_utils.py`

### ✅ WebSocket Integration

- Real-time futures price monitoring
- Live option price tracking
- Instant exit signal detection

### ✅ Robust Position Management

- Per-position profit tracking
- Dynamic TSL calculation
- Automatic pyramid triggering

### ✅ Clean Code Structure

```
futures_vwap_ema/
├── config.py      # Configuration parameters
├── strategy_core.py # Strategy logic (reusable)
├── live.py        # Live trading implementation
└── README.md      # This file
```

## Risk Disclosures

⚠️ **Important Risk Warnings:**

1. **Options Selling Risk:** Unlimited loss potential for naked option selling
2. **Pyramiding Risk:** Adding to losing positions can amplify losses
3. **Gap Risk:** Markets can gap beyond stop loss levels
4. **Slippage:** Actual execution prices may differ from expected prices
5. **Technical Risk:** Strategy depends on API reliability and connectivity

### Risk Management Recommendations

- ✅ Start with minimum position sizes
- ✅ Monitor positions actively during market hours
- ✅ Set maximum daily loss limits
- ✅ Maintain sufficient margin buffer
- ✅ Test thoroughly in paper trading mode
- ✅ Understand all exit conditions before trading live

## Example Scenario

### Scenario: CE Entry and Pyramid

**Market Conditions:**
- Nifty Futures: 23,450
- VWAP: 23,500
- 20 EMA: 23,480

**Entry Signal:** Futures (23,450) < VWAP (23,500) AND < EMA (23,480) ✅

**Action:** Sell 1 lot 23,600 CE @ 45

**Position Structure:**

| Event | Lots | Avg Entry | Current Price | Profit% | TSL% | TSL Price |
|-------|------|-----------|---------------|---------|------|-----------|
| Initial Entry | 1 | 45 | 45 | 0% | 20% | 54 |
| Price drops to 40 | 1 | 45 | 40 | 11% | 20% | 48 |
| **Pyramid 1** | 2 | 42.5 | 40 | - | 15% | 46 |
| Price drops to 35 | 2 | 42.5 | 35 | 18% | 15% | 40.25 |
| **Pyramid 2** | 3 | 40 | 35 | - | 10% | 38.5 |

**Exit Trigger:** Price rises to 39 → TSL (38.5) hit → Exit all positions

## Troubleshooting

### Issue: No entry signals generated

**Check:**
- ✅ Futures price relative to VWAP and EMA
- ✅ Candle data is updating (`verbose: True` in config)
- ✅ Entry time window (after 09:20)

### Issue: WebSocket not connecting

**Solutions:**
- Check internet connectivity
- Verify access token is valid
- Review WebSocket logs for errors

### Issue: Orders not executing

**Check:**
- ✅ Sufficient margin available
- ✅ `dry_run` is set to `False` for live trading
- ✅ Instrument keys are valid
- ✅ Market is open

## Performance Monitoring

The strategy displays real-time status:

```
======================================================================
📊 Strategy Status - 12:30:45
======================================================================
Futures: 23450.50 | VWAP: 23500.25 | EMA: 23480.75
Positions: 2 | Direction: CE
Total P&L: ₹2,350.00

Level    Entry      Current    Lowest     Profit%    P&L         
----------------------------------------------------------------------
0        45.00      40.00      40.00      11.1       ₹250.00     
1        40.00      40.00      40.00      0.0        ₹0.00       
======================================================================
```

## Support

For issues or questions:
1. Review logs in console output
2. Check configuration parameters
3. Verify helper function imports
4. Ensure market data is accessible

## License

This strategy is part of the Upstox trading framework. Use at your own risk.

---

**Last Updated:** 2026-01-23
**Version:** 1.0

# Delta-Neutral Option Selling Strategy

A market-neutral strategy that maintains delta neutrality through automatic Greek-based hedging.

## Overview

This strategy sells ATM straddles and continuously monitors portfolio delta. When delta breaches thresholds (±15), it automatically hedges by selling additional options to bring delta back to neutral.

## Key Features

- ✅ **Delta-Neutral**: Maintains portfolio delta ≈ 0
- ✅ **Automatic Hedging**: No manual intervention needed
- ✅ **Greek-Based**: Uses real-time Greeks from option chain
- ✅ **Risk Controlled**: Delta limits prevent directional risk
- ✅ **Premium Collection**: Profits from time decay (theta)

## Documentation

- [Implementation Plan](./implementation_plan.md) - Detailed design and architecture
- [Walkthrough](./walkthrough.md) - Complete implementation guide with flow diagrams
- [README](./README.md) - This file

## Quick Start

```python
from strategies.delta_neutral_strategy import DeltaNeutralStrategy
from api.market_data import download_nse_market_data

# Load data
token = "your_access_token"
nse_data = download_nse_market_data()

# Initialize and run
strategy = DeltaNeutralStrategy(access_token=token, nse_data=nse_data, lot_size=65)
strategy.run(check_interval=30)
```

## Files

- **Strategy**: [`strategies/delta_neutral_strategy.py`](../../strategies/delta_neutral_strategy.py)
- **Test**: [`test_delta_neutral_strategy.py`](../../test_delta_neutral_strategy.py)

## Parameters

| `entry_time` | 9:20 AM | Time to enter initial position |
| `trailing_sl_pnl_trigger` | 0.25 | Start trailing at 25% of profit target |
| `trailing_sl_lock_pct` | 0.50 | Lock 50% of peak profit as dynamic SL |
| `max_gamma` | 0.50 | Emergency exit if portfolio Gamma exceeds this |
| `profit_target_pct` | 0.5 | Exit at 50% premium |
| `stop_loss_multiplier` | 0.3 | Exit at -0.3× premium (30% loss) |

## Advanced Safety Features

1.  **Time-Based Entry**: Waits for morning market volatility to subside (default 9:20 AM) before entering.
2.  **Trailing Stop Loss**: Protects your gains. If profit reaches 25% of the target, the stop loss starts trailing to lock in at least 50% of the peak profit.
3.  **Maximum Position Limit**: Stops adding exposure once the lot or round limit is reached.
4.  **Progressive Delta Tolerance**: Threshold widens (15 → 22.5 → 33.75) to prevent over-hedging.
5.  **Cooldown Period**: A 5-minute pause between hedges.

1. **Initialize**: Fetch option chain, find ATM strike
2. **Enter**: Sell ATM straddle (CE + PE)
3. **Monitor**: Calculate portfolio delta every 30s
4. **Hedge**: When \|Δ\| > 15, sell additional options
5. **Exit**: On profit target, stop loss (30%), or 3:15 PM

## Test Results

**5/5 tests passed (100%)**

```
✅ Initialization - ATM 25650, 85 strikes loaded
✅ Delta Calculation - Portfolio Δ = -7.83 (neutral)
✅ Greeks Calculation - All Greeks computed
✅ P&L Tracking - ₹370 unrealized on ₹17k premium
✅ Status Display - Real-time monitoring working
```

## Library Dependencies

Uses existing library code (zero duplication):
- `api/option_chain.py` - Greeks, market data, expiry detection
- `api/order_management.py` - Order placement
- `utils/instrument_utils.py` - Instrument key lookup
- `api/market_data.py` - NSE data download

## Example Output

```
🚀 Delta-Neutral Strategy Running...

================================================================================
⏰ 22:21:35
================================================================================
📊 Portfolio Greeks:
   Delta:     -7.8 | Gamma:  -0.1625
   Theta:  1346.14 | Vega:  -1689.09

💰 P&L Status:
   Premium Collected: ₹ 16,529.50
   Unrealized P&L:    ₹      0.00
   Total P&L:         ₹      0.00
   Profit Target:     ₹  8,264.75
   Stop Loss:         ₹-33,059.00

📋 Positions: 2
   1. SHORT 25650 CE @ ₹146.30 | Current: ₹146.30 | P&L: ₹    0.00
   2. SHORT 25650 PE @ ₹108.00 | Current: ₹108.00 | P&L: ₹    0.00
================================================================================

📊 Portfolio Delta: -7.8
✅ Delta within acceptable range (±15)
```

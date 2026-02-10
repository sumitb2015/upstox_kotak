# Unified Backtesting Framework - User Guide

## 1. Overview ("The DVR Analogy")
The backtesting framework acts like a **DVR for the Stock Market**. It allows you to:
- **Download** historical market data (Open, High, Low, Close).
- **Replay** that data candle-by-candle.
- **Simulate** your strategy's logic on that past data.
- **Verify** results ("What would have happened?") without risking real money.

> **Note**: The backtester uses a **Simulator File** (Adapter) that copies your strategy logic. It does NOT run your live trading code directly, keeping your live setup safe.

---

## 2. How to Run a Backtest
Run the `backtest.py` script from your terminal:

```bash
# Basic usage
python backtest.py --strategy vwap_straddle --from 2024-12-01 --to 2024-12-30

# List available strategies
python backtest.py --list
```

### Output
- **Console**: Shows day-by-day progress and trade logs.
- **Report**: Saves a detailed CSV file to `reports/{StrategyName}/`.

---

## 3. Configuration
All settings are managed in `config/backtest_config.yaml`. You can change parameters without touching the code.

```yaml
# Example Config
vwap_straddle:
  lot_size: 65
  stop_loss_points: 30.0
  candle_interval_minutes: 5
  max_trades_per_day: 1
```

---

## 4. Developer Guide: Adding a New Strategy
To add a new strategy (e.g., `DynamicStrangle`), follow these 4 steps:

### Step 1: Create Folder
Create a new folder for your strategy:
`strategies/dynamic_strangle/`

### Step 2: Create Simulator File
Create `strategies/dynamic_strangle/backtest.py`.
- **Copy** the code from `strategies/vwap_straddle/backtest.py`.
- **Modify** the `_run_day_logic` method with your new Entry/Exit rules.

### Step 3: Register Strategy
Edit `core/backtesting/registry.py`:
```python
from strategies.dynamic_strangle.backtest import DynamicStrangleBacktest

STRATEGY_REGISTRY = {
    # ... existing ...
    'dynamic_strangle': DynamicStrangleBacktest,
}
```

### Step 4: Update Config
Add your settings to `config/backtest_config.yaml`:
```yaml
dynamic_strangle:
  lot_size: 50
  multiplier: 1.5
```

You are now ready to run:
`python backtest.py --strategy dynamic_strangle ...`

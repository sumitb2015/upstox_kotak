# Expired API Usage Guide

This guide explains how to use the Upstox Expired Instruments API for backtesting and historical analysis.

## Overview

The expired API allows you to fetch historical data for options and futures contracts that have already expired. This is essential for backtesting strategies on historical data beyond the standard 6-month limit.

## Workflow

### 1. Fetch Available Expiries

```python
from api.expired_data import get_expired_expiry_dates

expiries = get_expired_expiry_dates(
    access_token,
    "NSE_INDEX|Nifty 50",
    from_date="2024-10-01",  # Optional filter
    to_date="2024-12-31"      # Optional filter
)

# Returns: ['2024-10-03', '2024-10-10', '2024-10-17', ...]
```

### 2. Fetch Option Contracts for an Expiry

```python
from api.expired_data import get_expired_option_contracts

contracts = get_expired_option_contracts(
    access_token,
    "NSE_INDEX|Nifty 50",
    "2024-10-03",
    min_strike=24000,  # Optional filter
    max_strike=26000,  # Optional filter
    option_type='CE'   # Optional: 'CE' or 'PE'
)

# Each contract contains:
# - instrument_key: 'NSE_FO|58423|03-10-2024'
# - strike_price: 25000.0
# - instrument_type: 'CE' or 'PE'
# - trading_symbol: 'NIFTY 25000 CE 03 OCT 24'
# - lot_size, tick_size, etc.
```

### 3. Find Specific Contracts

#### Find ATM Strike

```python
from api.expired_data import find_atm_strike

spot_price = 25234.50
atm_strike = find_atm_strike(contracts, spot_price)
# Returns: 25250.0 (closest strike to spot)
```

#### Get Specific Contract

```python
from api.expired_data import get_contract_by_criteria

ce_contract = get_contract_by_criteria(contracts, 25250, 'CE')
pe_contract = get_contract_by_criteria(contracts, 25250, 'PE')
```

#### Filter by Moneyness

```python
from api.expired_data import filter_contracts_by_moneyness

# Get contracts 0-5% OTM
otm_contracts = filter_contracts_by_moneyness(
    contracts,
    spot_price=25234.50,
    min_pct_otm=0,
    max_pct_otm=5
)
```

### 4. Fetch Historical Candles

```python
from api.expired_data import get_expired_historical_candles

# Get as list of dicts
candles = get_expired_historical_candles(
    access_token,
    instrument_key='NSE_FO|58423|03-10-2024',
    interval='1minute',  # or '5minute', '30minute', 'day', etc.
    from_date='2024-10-01',
    to_date='2024-10-03'
)

# Or get as pandas DataFrame
df = get_expired_historical_candles(
    access_token,
    instrument_key='NSE_FO|58423|03-10-2024',
    interval='5minute',
    from_date='2024-10-01',
    to_date='2024-10-03',
    return_dataframe=True
)

# DataFrame columns: timestamp, open, high, low, close, volume, oi
```

## Integration with Backtesting

The `BacktestDataManager` in `core/backtesting/engine.py` automatically uses these functions when fetching data for expired instruments.

```python
from core.backtesting.engine import BacktestEngine, BacktestDataManager

# The data manager handles expired vs live data automatically
data_manager = BacktestDataManager(access_token)

# Fetch data (automatically uses expired API if needed)
df = data_manager.fetch_data(
    instrument_key='NSE_FO|58423|03-10-2024',
    start_date='2024-10-01',
    end_date='2024-10-03',
    interval_val=5
)
```

## Common Use Cases

### Backtest a Straddle Strategy

```python
# 1. Get expiries for backtest period
expiries = get_expired_expiry_dates(
    access_token,
    "NSE_INDEX|Nifty 50",
    from_date="2024-10-01",
    to_date="2024-10-31"
)

# 2. For each expiry, get contracts
for expiry in expiries:
    contracts = get_expired_option_contracts(
        access_token,
        "NSE_INDEX|Nifty 50",
        expiry
    )
    
    # 3. Find ATM strike (you'd get spot from index data)
    atm = find_atm_strike(contracts, spot_price)
    
    # 4. Get CE and PE contracts
    ce = get_contract_by_criteria(contracts, atm, 'CE')
    pe = get_contract_by_criteria(contracts, atm, 'PE')
    
    # 5. Fetch candles for both legs
    ce_data = get_expired_historical_candles(
        access_token, ce['instrument_key'], '5minute',
        expiry, expiry, return_dataframe=True
    )
    pe_data = get_expired_historical_candles(
        access_token, pe['instrument_key'], '5minute',
        expiry, expiry, return_dataframe=True
    )
    
    # 6. Run your strategy logic...
```

## Troubleshooting

### Empty Data Response

If you get an empty response:
- Check that the expiry date is valid (was an actual expiry Thursday)
- Ensure the date is within the last 6 months (API limitation)
- Verify the instrument_key format is correct

### Rate Limiting

The API has rate limits. The `BacktestDataManager` includes caching to minimize API calls. For large backtests:
- Use date filtering to fetch only needed expiries
- Cache contract lookups
- Batch your requests where possible

## API Endpoints Reference

| Endpoint | Purpose | Format |
|----------|---------|--------|
| `/v2/expired-instruments/expiries` | Get expiry dates | GET with params |
| `/v2/expired-instruments/option/contract` | Get option contracts | GET with params |
| `/v2/expired-instruments/historical-candle/{key}/{interval}/{to}/{from}` | Get OHLCV data | GET path params |

## See Also

- [Upstox API Documentation](https://upstox.com/developer/api-documentation)
- `tests/test_expired_api_integration.py` - Complete working example
- `scripts/working_expired_data_upstox.ipynb` - Interactive exploration

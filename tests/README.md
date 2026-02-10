# Upstox Algorithmic Trading System - Test Suite

This directory contains the unit tests for the Upstox Algorithmic Trading System.
The tests are designed to verification the functionality of the core libraries and strategy logic.

## 🧪 Structure

- `tests/`
  - `test_lib_utils.py`: Tests for `lib.utils` (Instrument mapping, Expiry cache, etc.)
  - `test_lib_indicators.py`: Tests for `lib.utils.indicators` (RSI, EMA, Supertrend)
  - `test_strategy_core.py`: Tests for pure strategy logic (Signal generation only)
  - `test_api_mock.py`: Tests for Authentication and Market Data (Mocked Integration)

## 🏃 Value Proposition

To run the tests, use `pytest` (ensure you have the virtual environment activated).

```bash
# Run all tests
python -m pytest tests/

# Run a specific test file
python -m pytest tests/test_lib_utils.py

# Run with verbose output
python -m pytest -v tests/
```

## 📝 Guidelines

1.  **Mocking**: Strategy tests should Mock API calls (`market_data`, `order_manager`) to avoid placing real orders or calling the Upstox API during testing.
2.  **Pure Logic**: Focus on testing "Pure Logic" functions (e.g. `check_entry_signal(price, indicator)`) rather than side effects.
3.  **Isolation**: Tests should be independent of each other.

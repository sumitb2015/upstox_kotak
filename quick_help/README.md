# Quick Help - Upstox API Reference

This folder contains interactive Jupyter notebooks for quickly testing and exploring Upstox API functionality without modifying your strategy files.

## Files

### `upstox_api_reference.ipynb`
Comprehensive notebook covering all standard Upstox API functions:
- Authentication
- Market Data (NSE Instruments, Futures, Options)
- Historical & Intraday Data
- Option Chain & Greeks
- LTP & OHLC Quotes
- WebSocket Streaming
- Instrument Utilities

## Usage

1. **Start Jupyter Notebook:**
   ```bash
   cd c:/algo/upstox/quick_help
   jupyter notebook
   ```

2. **Open `upstox_api_reference.ipynb`**

3. **Run cells sequentially** to test API functions and see response formats

## Benefits

- ✅ Test API functions without modifying strategy code
- ✅ Explore response structures and data formats
- ✅ Quick debugging and validation
- ✅ Learn Upstox API interactively
- ✅ Copy-paste working code into your strategies

## Requirements

Make sure Jupyter is installed:
```bash
pip install jupyter notebook
```

## Official Documentation

- **Upstox Python SDK:** https://github.com/upstox/upstox-python
- **API Documentation:** https://upstox.com/developer/api-documentation/

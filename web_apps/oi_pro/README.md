# OI Pro Analytics - Feature & API Documentation

OI Pro is a comprehensive options analytics dashboard designed for Indian markets (Nifty, BankNifty, Finnifty, etc.). It provides real-time Greeks, Open Interest (OI) buildup, Gamma Exposure (GEX), and strategy management capabilities.

## 🌐 Website Pages & Functionalities

### 1. Dashboard / Home (`/`)
- **Functionality**: Serves as the central cockpit. Displays real-time prices for major indices (NIFTY 50, BANK NIFTY, FINNIFTY, etc.) with daily percentage changes.
- **Key Features**: Live market watch, quick navigation to all analytics modules.

### 2. Cumulative OI Analysis (`/cumulative`)
- **Functionality**: Aggregates Open Interest across multiple strikes (ATM ± N) to show overall market sentiment.
- **Key Features**: Tracks cumulative CE vs. PE OI, Net OI Change, and PCR momentum. Uses yesterday's close as a baseline for intraday buildup.

### 3. Net GEX Regime Analysis (`/gex`)
- **Functionality**: Visualizes total Gamma Exposure (GEX) and total Notional Exposure.
- **Key Features**: "Traffic light" regime chart showing if the market is in a Positive GEX (Stable/Mean Reverting) or Negative GEX (Volatile/Trending) environment. Includes Flip Point calculation.

### 4. Greeks Exposure Analysis (`/greeks`)
- **Functionality**: Provides a per-strike breakdown of all major Greeks.
- **Key Features**: Real-time Delta, Gamma, Vega, Theta, and GEX for every strike in the chain. Visualizes Net Delta and Net Gamma across the option chain.

### 5. OI Change Heatmap (`/heatmap`)
- **Functionality**: A time-series grid showing the intensity of OI change and price buildup across strikes.
- **Key Features**: Color-coded visualization of Long Buildup, Short Buildup, Short Covering, and Long Unwinding. Tracks strike-wise shifts every minute.

### 6. Max Pain & IV Smile (`/max-pain`)
- **Functionality**: Uses the Max Pain theory to identify the strike where option buyers lose the most (and sellers gain the most).
- **Key Features**: Displays the Max Pain strike and the Volatility Smile (Implied Volatility per strike).

### 7. Multi-Option Chart (`/multi`)
- **Functionality**: A custom strategy builder for multi-leg positions (Spreads, Iron Condors, etc.).
- **Key Features**: Allows users to add multiple legs (Buy/Sell) and generates a combined premium chart with a running VWAP.

### 8. Consolidated Multi-Strike Analysis (`/multi-strike`)
- **Functionality**: Highly detailed analysis for up to 5-10 specific strikes simultaneously.
- **Key Features**: Comparative time-series plots for both Price and Open Interest across multiple strikes on a single chart.

### 9. Option Chain Analytics (`/option-chain`)
- **Functionality**: A professional-grade option chain with advanced data columns.
- **Key Features**: Buildup indicators, Top 3 OI rankings for Calls/Puts, real-time LTPs, and PCR metadata.

### 10. PCR by Strike Grid (`/pcr`)
- **Functionality**: Breaks down the Put-Call Ratio for every individual strike.
- **Key Features**: Categorizes strikes into Bullish (Support) or Bearish (Resistance) zones based on writer domination.

### 11. PoP & Premium Analytics (`/pop`)
- **Functionality**: Helps in strike selection for option selling.
- **Key Features**: Scatter plot of Probability of Profit (PoP) vs. Premium received. Ideal for finding high-probability OTM credits.

### 12. ATM Straddle Analysis (`/straddle`)
- **Functionality**: Dedicated module for tracking the "heartbeat" of market volatility.
- **Key Features**: Real-time tracking of the ATM Straddle premium, intraday High/Low, and Straddle VWAP.

### 13. Strategy Command Center (`/strategies`)
- **Functionality**: Centralized management interface for automated trading strategies.
- **Key Features**: Start/Stop live strategies, view real-time logs in a terminal window, update configurations (`config.py`) on-the-fly, and monitor PnL/Uptime.

### 14. Strike Analysis (`/strike`)
- **Functionality**: Isolated deep-dive into a single strike.
- **Key Features**: Historical and real-time intraday tracking of CE vs. PE OI, Price, and Buildup for a specific strike price.

---

## 🚀 API Endpoints

The backend is built with **FastAPI** and provides the following RESTful endpoints:

### Market Data & Analytics
- `GET /api/expiries`: Returns all available expiry dates for a symbol.
- `GET /api/option-chain`: Detailed chain analytics including buildup and PCR.
- `GET /api/greeks-data`: Real-time Greeks, GEX, and Flip Point for the chain.
- `GET /api/delta-heatmap`: Time-series data for the OI change heatmap grid.
- `GET /api/pcr-data`: PCR and sentiment classification per strike.
- `GET /api/max-pain-data`: Max Pain strike and IV data for the volatility smile.
- `GET /api/cumulative-oi`: Aggregated OI metrics for a range of strikes.

### Specialized Analytics
- `GET /api/pop-data`: Premium and PoP data points for scatter charts.
- `GET /api/straddle-data`: Time-series and KPIs for ATM or custom straddles.
- `GET /api/strike-data`: Intraday price/OI history for a specific strike.
- `GET /api/gex-history`: Time-series of total Net GEX relative to Spot Price.
- `GET /api/strike-greeks-history`: Persistent historical Greeks for a specific strike.

### Multi-Leg & Parallel Data
- `POST /api/multi-strike-history`: Calculates combined premium/VWAP for custom leg lists.
- `GET /api/multi-strike-oi-data`: Parallel intraday OI history for multiple strikes.
- `GET /api/multi-strike-price-data`: Parallel intraday Price history for multiple strikes.

### Strategy Management
- `GET /api/strategies`: Returns status and metadata for all registered strategies.
- `POST /api/strategies/start/{id}`: Spawns a background `live.py` process.
- `POST /api/strategies/stop/{id}`: Gracefully terminates a strategy process.
- `GET /api/strategies/logs/{id}`: Fetches the latest console output from the strategy.
- `GET /api/strategies/config/{id}`: Reads the `CONFIG` dictionary from the strategy's `config.py`.
- `POST /api/strategies/config/{id}`: Safely updates specific config params using regex.

## 📖 Related Documentation
- [Exposure Change Heatmap Calculation Guide](file:///c:/upstox_kotak/upstox_kotak/web_apps/oi_pro/README_HEATMAP.md): Detailed logic for the heatmap color and intensity calculations.

---

## 📡 WebSocket Endpoints

- `/ws/market-watch`: Real-time price updates for Dashboard indices.
- `/ws/straddle`: High-speed tick data for specific option instrument keys.
- `/ws/price/{symbol}`: Dedicated live price feed for a specific underlying.

---

## 🛠️ Technical Details
- **Backend**: Python (FastAPI, Uvicorn)
- **Data Source**: Upstox API V3 (Market Feed & Quotation)
- **Frontend**: Vanilla JS / HTML5 / CSS3 (using shared `sidebar.js`)
- **Charts**: Plotly.js / Chart.js
- **Middleware**: CORS enabled for cross-origin access.

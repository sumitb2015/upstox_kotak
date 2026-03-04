# OI Pro Analytics - Feature & API Documentation

OI Pro is a comprehensive options analytics dashboard designed for Indian markets (Nifty, BankNifty, Finnifty, etc.). It provides real-time Greeks, Open Interest (OI) buildup, Gamma Exposure (GEX), and strategy management capabilities.

## 🌐 Website Pages & Functionalities

### 1. Stock Dashboard (`/index.html`)
- **Functionality**: Multi-layered analysis for Nifty and BankNifty constituent stocks.
- **Key Features**: 
  - **Live Price Grid**: Real-time tracking of LTP, Change%, and day's range.
  - **Buildup Analytics Tab**: Professional quadrant analysis (Long/Short Buildup, Short Covering, Long Unwinding) based on **Futures Price & OI Change**.
  - **Performance Optimization**: Powered by a 60-second Redis cache to ensure lightning-fast data delivery and reduced API overhead.
  - **Modern UI**: High-density list view with zero-gap layout and stylized sentiment indicators.

### 2. Cumulative OI Analysis (`/cumulative`)
- **Functionality**: Aggregates Open Interest across multiple strikes (ATM ± N) to show overall market sentiment.
- **Key Features**: Tracks cumulative CE vs. PE OI, Net OI Change, and PCR momentum. Uses yesterday's close as a baseline for intraday buildup.

### 3. Cumulative Option Prices (`/cumulative-prices`)
- **Functionality**: Real-time sum of all Call and Put option prices across the entire option chain.
- **Key Features**: Dual-axis real-time chart tracking CE premiums vs PE premiums alongside the Index Spot price, and a smoothed CE-PE Difference chart with sentiment coloration. Full-width layout.

### 3. Net GEX Regime Analysis (`/gex`)
- **Functionality**: Visualizes total Gamma Exposure (GEX) and total Notional Exposure.
- **Key Features**: "Traffic light" regime chart showing if the market is in a Positive GEX (Stable/Mean Reverting) or Negative GEX (Volatile/Trending) environment. Includes Flip Point calculation.

### 4. Greeks Exposure Analysis (`/greeks`)
- **Functionality**: Provides a per-strike breakdown of all major Greeks.
### 5. OI Change Heatmap (`/heatmap`)
- **Functionality**: A time-series grid showing the intensity of OI change and price buildup across strikes.
- **Key Features**: Color-coded visualization of Long Buildup, Short Buildup, Short Covering, and Long Unwinding. Tracks strike-wise shifts every minute.

### 6. Max Pain & Volatility Smile (`/max-pain`)
- **Functionality**: Uses the Max Pain theory to identify optimal strike prices and visualizes implied volatility dynamics.
- **Key Features**: Displays the Max Pain strike and a **Unified Volatility Smile (OTM IV Curve)** with rolling smoothing, analytics KPI grid, and Top 10 Opportunities table for options sellers.

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
- **Key Features**: Scatter plot of Probability of Profit (PoP) vs. Premium received. Includes 6-card KPI analytics strip (Highest CE/PE OI, Best CE/PE to Sell, PCR, Avg PoP) and a Top 10 Opportunities table ranked by premium. Full-width layout.

### 12. ATM Straddle Analysis (`/straddle`)
- **Functionality**: Dedicated module for tracking the "heartbeat" of market volatility.
- **Key Features**: Real-time tracking of the ATM Straddle premium, intraday High/Low, Straddle VWAP, and individual CE/PE leg traces on secondary axis. 8-card KPI strip adds Open, VWAP, CE LTP, PE LTP. High/Low band shading and open price reference line. Full-width layout.

### 13. Strategy Command Center (`/strategies`)
- **Functionality**: Centralized management interface for automated trading strategies.
- **Key Features**: Start/Stop live strategies, view real-time logs in a terminal window, update configurations (`config.py`) on-the-fly, and monitor PnL/Uptime.

### 14. Strike Analysis (`/strike`)
- **Functionality**: Isolated deep-dive into a single strike.
- **Key Features**: Historical and real-time intraday tracking of CE vs. PE OI, Price, and Buildup for a specific strike price. Includes dynamic-colored bars (buildup vs unwinding), Net OI / Net Change secondary lines, ATM amber annotations, zero-band shading, and a 6-card KPI strip (Max CE/PE OI, Max CE/PE OI Change, PCR, Sentiment).

### 15. OI Trend Analyzer (`/oi-buildup`)
- **Functionality**: Professional-grade high-density "Tape" visualization of strike-level OI buildup patterns.
- **Key Features**: Barcode-style high-density grid for PE (Top) and CE (Bottom) buildup visualization, slanting strike labels, and flicker-free 1-minute background updates.

### 16. Strike Greeks History (`/strike-greeks`)
- **Functionality**: Persistent historical time-series of option Greeks for a specific strike.
- **Key Features**: 5 charts — Delta, Gamma, Vega, Theta, and Implied Volatility. 8-card KPI strip with latest values and intraday change. Color-coded CE (solid) / PE (dashed) spline traces. Live pulse badge and informative empty-state.

### 17. Market Watch (`/market-watch`) [NEW]
- **Functionality**: Sector performance and constituent contribution tracking.
- **Key Features**: Plotly bar chart displaying the daily percentage changes of various indices (NIFTY IT, BANKNIFTY, etc.) and visual constituent boards for NIFTY and BANKNIFTY stocks with right-to-left and left-to-right bar progressions.

### 18. Future Intraday Buildup (`/future-intraday`) [NEW]
- **Functionality**: Detailed intraday tracking of Open Interest buildup for the current month's future contract.
- **Key Features**: Allows toggling between 3, 5, and 15-minute intervals. Calculates real-time sentiment (Long Buildup, Short Buildup, etc.) based on Price and OI changes. Includes a sentiment progress bar and a detailed color-coded table. Automatically refreshes every minute.

### 19. Future Price vs OI (`/future-price-oi`) [NEW]
- **Functionality**: High-performance streaming chart correlating Future Price with Open Interest.
- **Key Features**: Live dual-axis Plotly line chart rendering Future Price (left axis) vs Open Interest (right axis). Initializes using historical 1-minute data and seamlessly streams tick-by-tick updates via WebSockets for real-time visualization.

### 20. User Login (`/login`)
- **Functionality**: Secure gateway to the analytics platform using JWT-based authentication.
- **Key Features**: Persistent sessions via local storage, automatic redirection for unauthenticated users.
- **Default Credentials**: `admin@oipro.com` / `OIPro@123` (Administrator)

### 21. User Management (`/users`)
- **Functionality**: Administrator dashboard for managing platform accounts.
- **Key Features**: View all users, add new accounts with specific roles, and delete users. Access is strictly restricted to 'admin' role accounts.

### 22. FII / DII Analytics (`/fii-dii`) [NEW]
- **Functionality**: Visualizes institutional flow (FII and DII) together with Nifty performance.
- **Key Features**: Multi-pane Plotly chart showing Nifty Spot (Line/Area), FII Net (Bar), and DII Net (Bar) on a unified timeline. Includes an interactive side panel for "Historical Logs" and optimized monthly X-axis labeling for long-term trend analysis. Fully standardized with the global design system.

### 23. Broker Management (`/brokers`)
- **Functionality**: Centralized interface for managing broker API credentials and generating daily access tokens.
- **Key Features**: Add, edit, and delete broker credentials (masked API Keys/Secrets). Features an interactive popup-based OAuth token generation flow for Upstox without leaving the dashboard.

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
- `GET /api/stock-analytics`: Futures-based stock classification (Buildup/Unwinding) with 60s Redis caching.
- `GET /api/fii-dii`: Returns historical FII and DII net flow data along with Nifty close values from a CSV source.

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

### Authentication & User Management
- `POST /api/login`: Secure login endpoint returning a JWT including user role.
- `GET /api/me`: Returns the current authenticated user's details.
- `GET /api/users`: Admin-only endpoint to list all platform users.
- `POST /api/users`: Admin-only endpoint to create new users.
- `DELETE /api/users/{email}`: Admin-only endpoint to remove user accounts.

### Diagnostics
- `GET /api/debug/ws-state`: Returns live WebSocket subscription state for the authenticated user — streamer connection status, subscribed instrument keys, cached feed keys, and event loop health. Used to diagnose live tick delivery issues.

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
- `/ws/cumulative-prices`: Dedicated feed pushing aggregated CE/PE sums and real-time difference values.
- `/ws/price/{symbol}`: Dedicated live price feed for a specific underlying.

---

## 🛠️ Technical Details
- **Backend**: Python (FastAPI, Uvicorn)
- **Security**: JWT-based Authentication, Bcrypt password hashing.
- **Database**: SQLite (managed via Peewee ORM).
- **Data Source**: Upstox API V3 (Market Feed & Quotation)
- **Frontend**: Vanilla JS / HTML5 / CSS3 (using shared `sidebar.js` for dynamic RBAC navigation)
- **Charts**: Plotly.js / Chart.js
- **Middleware**: CORS enabled for cross-origin access.

### Recent Reliability Improvements
- **Full-System Semantic Theming**: Introduced a robust design system using CSS variables across 30+ pages, enabling seamless switching between Light and Dark modes while maintaining premium aesthetics.
- **Weekend/Off-Market High-Low Fix**: Enhanced the Upstox WebSocket parsing logic to correctly extract daily OHLC data from the `ohlc_day` nested structure, ensuring high/low prices are populated on all dashboards even during weekends and non-trading hours.
- **Authenticated UI Integrity**: The login gateway is now forced to Dark Mode permanently to ensure a consistent, secure-feeling point of entry, independent of the dashboard's theme settings.
- **Exposure Change Heatmap Overhaul**: Fixed a backend caching bug that prevented correct Open Interest baseline lookups for precise percentage scaling. Delivered a massive UI/UX overhaul implementing vibrant non-linear neon scaling (Green/Red/Cyan/Amber), glassmorphism effects, a new `#0f1117` terminal dark mode, and fully dynamic tooltips accommodating both Light & Dark modes natively.
- **Multi-Option Chart Live Ticks Bug Fix**: Resolved a race condition in `/ws/straddle` where option instrument keys were subscribed to Upstox before the WebSocket handshake had completed, causing silent subscription failures. `manager.subscribe()` now waits up to 5 seconds for `market_data_connected` before calling `subscribe_market_data()`. Also added a 10-second grace period in `StreamerRegistry.release()` to prevent needless streamer teardown on rapid page navigation. Frontend guard clauses blocking tick processing were also removed.
- **Stock Dashboard Analytics Integration**: Launched a professional "Buildup Analytics" suite within the Stock Dashboard, utilizing nearest-futures contract data (NSE_FO) for high-fidelity sentiment analysis. Implemented a robust 60-second Redis caching layer and an ultra-compact, high-density UI layout to maximize data visibility on a single screen.

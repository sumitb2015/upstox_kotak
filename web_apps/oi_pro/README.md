# OI Pro Analytics - Feature & API Documentation

OI Pro is a comprehensive options analytics dashboard designed for Indian markets (Nifty, BankNifty, Finnifty, etc.). It provides real-time Greeks, Open Interest (OI) buildup, Gamma Exposure (GEX), and strategy management capabilities.

## 🌐 Website Pages & Functionalities

### 1. Dashboard / Home (`/`)
- **Functionality**: Serves as the central cockpit. Displays real-time prices for major indices (NIFTY 50, BANK NIFTY, FINNIFTY, etc.) with daily percentage changes.
- **Key Features**: Live market watch, quick navigation to all analytics modules.

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
- **Key Features**: Real-time Delta, Gamma, Vega, Theta, and GEX for every strike in the chain. Visualizes Net Delta and Net Gamma across the option chain.

### 5. OI Change Heatmap (`/heatmap`)
- **Functionality**: A time-series grid showing the intensity of OI change and price buildup across strikes.
- **Key Features**: Color-coded visualization of Long Buildup, Short Buildup, Short Covering, and Long Unwinding. Tracks strike-wise shifts every minute.

### 6. Max Pain & IV Smile (`/max-pain`)
- **Functionality**: Uses the Max Pain theory to identify the strike where option buyers lose the most (and sellers gain the most).
- **Key Features**: Displays the Max Pain strike, Volatility Smile, analytics KPI grid (Highest CE/PE OI strikes, Best Premium to Sell, PCR, Average PoP), and Top 10 Opportunities table for options sellers. Full-width layout.

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

### 15. Options Buildup (`/`)
- **Functionality**: Visualizes strike-level OI buildup patterns with sentiment classification.
- **Key Features**: Three enhanced charts — Sentiment Scatter (√-scaled bubbles, quadrant zones, top-3 labels), Total OI Bar (dynamic opacity, Net OI line), OI Change Bar (dynamic coloring, Net Change line). ATM reference lines across all charts. Buildup Summary Strip showing CE/PE counts by type and dominant signal.

### 16. Strike Greeks History (`/strike-greeks`)
- **Functionality**: Persistent historical time-series of option Greeks for a specific strike.
- **Key Features**: 5 charts — Delta, Gamma, Vega, Theta, and Implied Volatility. 8-card KPI strip with latest values and intraday change. Color-coded CE (solid) / PE (dashed) spline traces. Live pulse badge and informative empty-state.

### 17. User Login (`/login`)
- **Functionality**: Secure gateway to the analytics platform using JWT-based authentication.
- **Key Features**: Persistent sessions via local storage, automatic redirection for unauthenticated users.
- **Default Credentials**: `admin@oipro.com` / `OIPro@123` (Administrator)

### 18. User Management (`/users`)
- **Functionality**: Administrator dashboard for managing platform accounts.
- **Key Features**: View all users, add new accounts with specific roles, and delete users. Access is strictly restricted to 'admin' role accounts.

### 19. Broker Management (`/brokers`)
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
- **Robust Cold Start & Standby Mode**: The server now starts in a refined "standby" mode, consolidating fragmented startup handlers into a single predictable sequence. Background services (Greeks History, Baseline OI, Streamer) now use "Lazy Initialization," waiting for the first authorized user login before activating. This ensures a clean, error-free startup in production environments.
- **User-Powered Background Polling**: Refactored the global data polling mechanism to dynamically "borrow" access tokens from active, authorized users. This removes the dependency on hardcoded `.env` credentials for production deployments.
- **Graceful Weekend Handling**: Endpoints for Option Chain, Straddle, and Strike data now return a successful 200 OK with empty metadata instead of 404/500 errors during non-trading hours. This ensures the dashboard UI remains stable even when indices have no active weekly contracts.
- **NaN Serialization Fix**: All numeric outputs (Spot, PCR, Greeks) are sanitized for `NaN` and `Inf` values before JSON serialization to prevent frontend crashes on low-liquidity future expiries.

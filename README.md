# Upstox & Kotak Algorithmic Trading System

A robust, modular algorithmic trading framework designed for Indian stock markets (NSE/BSE), utilizing Upstox and Kotak Securities APIs. This system is built for reliability, scalability, and advanced risk management.

## 🚀 Key Features

- [x] **Post-Development Fixes**: Resolved critical API routing bugs and standardized strategy telemetry.
- **Multibroker Support**: Seamless integration with Upstox and Kotak Securities.
- **Modular Architecture**: Clean separation between core logic, strategy implementations, and API adapters.
- **Advanced Risk Management**:
  - Hybrid Gated Stop Loss
  - Dynamic Trailing Stop Loss (TSL) with profit locking
  - Step-locking mechanisms
- **Real-Time Data**: Utilization of WebSockets for low-latency market data and order updates.
- **Option & Future Strategies**: tailored logic for NIFTY, BANKNIFTY, and FINNIFTY instruments.
- **Comprehensive Logging**: Detailed telemetry for strategy state, signals, and execution using standardized formats.
- **Integrated OI Pro Analytics Suite**: 25+ Advanced analytics pages protected by JWT-based authentication and role-based access control.
  - **Market-Wide Dashboards**:
    - **Stock Dashboard**: Grid view with Futures-based Buildup analysis (Long/Short Buildup, Unwinding).
    - **Indices Dashboard**: Categorized NSE Major, Sectoral, and Thematic indices with market breadth.
    - **FII / DII Analytics**: Tracking institutional flow and participation.
    - **Market Watch**: Real-time price tracking for selected internal symbols.
  - **Premium Option Analytics**:
    - **Dynamic Option Chain**: Real-time markers for OH/OL conditions and high-contrast ATM identification.
    - **Strike-wise PCR**: Sentiment analysis with bull/bear indicators across the entire chain.
    - **Max Pain & IV Smile**: Mathematical pinning analysis and volatility skew visualization.
    - **ATM Straddle Analysis**: Deep dive into straddle premiums with mean reversion tracking.
    - **Multi-Strike Comparison**: Contrast OI and Price action across 5 strikes simultaneously.
    - **Multi-Option Strategy Chart**: Synchronized Price and Normalized OI Change for custom multi-leg strategies.
  - **Risk & Exposure Management**:
    - **Net GEX Regime**: Market Volatility Regime identification (Traffic Light logic) and Gamma Flip points.
    - **Greeks Exposure**: Real-time systemic Delta and Gamma tracking per strike.
    - **Exposure Change Heatmap**: NIFTY-focused minute-by-minute OI change tracking from session start.
    - **Strike Greeks History**: Historical greeks data persistent across server restarts/sessions.
  - **Trend & Mathematical Analysis**:
    - **Future Intraday & Price vs OI**: Correlating future price movement with open interest buildup.
    - **3D Surface Analysis**: Volatility and OI surface visualization for whole-range diagnostic.
    - **OI Trend Analyzer & Cumulative Analysis**: Advanced filtering for OI buildup and cumulative option price flow.
    - **Seller's Edge (PoP)**: Probability of Profit scatter plots for premium vs risk assessment.
  - **Execution & Ecosystem**:
    - **Strategy Command Center**: Unified interface to monitor, start, and stop all live trading algorithms.
    - **Market News & News Pulse**: Aggregated financial news feeds with sentiment-focused views.
    - **Market Calendar**: Professional holiday tracking with count-downs and monthly grouping.
    - **Broker Management**: Centralized portal for multisegment API token session management.
    - **User Admin**: Backend dashboard for managing roles, permissions, and platform accounts.
- **Unified Navigation**: Sidebar-driven navigation with persistent semantic (Light/Dark) theming.
- **State Persistence Engine**: Automated daily snapshots ensuring analytics state recovery on restart.
- **Extensive Strategy Library**: Over 20+ detailed strategy implementations with comprehensive `README.md` guides covering entry/exit logic, risk management, and execution examples.

## 📂 Project Structure

```text
c:/algo/upstox/
├── strategies/         # Trading strategy implementations
│   ├── directional/    # Directional strategies (e.g., Breakout, Supertrend)
│   └── non_directional/# Non-directional strategies (e.g., Straddles, Strangles)
├── lib/                # Core libraries and utilities
│   ├── api/            # API wrappers for Upstox
│   ├── utils/          # Helper functions (indicators, time, math)
│   └── logger/         # Logging configuration
├── kotak_api/          # Kotak Securities specific integrations
├── docs/               # Detailed documentation and guides
├── .agent/             # AI Agent rules, skills, and workflows
├── tools/              # Utility scripts for maintenance and data
└── web_apps/           # Web-based analytics dashboards (OI Pro)
```

## 🛠️ Setup & Usage

### Prerequisites
- Python 3.10+
- Upstox / Kotak API Credentials
- Redis Server (Optional, but highly recommended for optimal Dashboard performance)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/sumitb2015/upstox_kotak.git
   cd upstox_kotak
   ```

2. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configuration**
   - Ensure you have your API credentials ready in a `.env` file.
   - Configure your strategy settings in the respective `config.py` files within the `strategies/` directory.
   - (Optional) Configure `REDIS_PASSWORD` in `.env` if exposing your Redis instance to production.

### Running the OI Pro Dashboard

```bash
# From the repo root
cd web_apps/oi_pro
PYTHONUTF8=1 python main.py
# Open http://127.0.0.1:8001/heatmap
```

> **Note (Windows):** The `PYTHONUTF8=1` prefix is required on Windows to prevent
> charmap encoding errors from emoji characters in log output.

### Running a Strategy

 Navigate to the strategy directory and run the `live.py` script:

```bash
# Example: Running the Nifty Breakout Strategy
python strategies/directional/nifty_breakout/live.py
```

## 🔒 Security & Backend

The analytics dashboard is protected by a professional security layer:
- **JWT Authentication**: Secure, token-based sessions with industry-standard JWT.
- **Credential Encryption**: Fernet-based symmetric encryption for all broker API secrets stored at rest.
- **Role-Based Access (RBAC)**: Distinct permissions for `admin` and `user` roles.
- **Rate Limiting**: Protection for sensitive authentication and analytical endpoints using `slowapi`.
- **Encrypted Storage**: Bcrypt hashing for all user portal passwords.
- **Persistent Database**: SQLite-based user management.

## 📚 Documentation

- [Agent Rules & Standards](.agent/rules/agent.md)
- [Console Output Guide](.agent/rules/agent_console_output.md)
- [Testing Guide](.agent/rules/agent_testing.md)

## 🤝 Contributing

Please ensure you follow the coding standards and workflow guidelines defined in `.agent/rules/` before submitting changes.
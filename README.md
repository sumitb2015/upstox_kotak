# Upstox & Kotak Algorithmic Trading System

A robust, modular algorithmic trading framework designed for Indian stock markets (NSE/BSE), utilizing Upstox and Kotak Securities APIs. This system is built for reliability, scalability, and advanced risk management.

## 🚀 Key Features

- **Multi-Broker Support**: Seamless integration with Upstox and Kotak Securities.
- **Modular Architecture**: Clean separation between core logic, strategy implementations, and API adapters.
- **Advanced Risk Management**:
  - Hybrid Gated Stop Loss
  - Dynamic Trailing Stop Loss (TSL) with profit locking
  - Step-locking mechanisms
- **Real-Time Data**: Utilization of WebSockets for low-latency market data and order updates.
- **Option & Future Strategies**: tailored logic for NIFTY, BANKNIFTY, and FINNIFTY instruments.
- **Comprehensive Logging**: Detailed telemetry for strategy state, signals, and execution using standardized formats.
- **Secure OI Pro Dashboard**: Interactive analytics dashboard with JWT-based authentication and role-based access control (RBAC).
  - **User Management**: Administrator dashboard for managing platform accounts directly from the web interface.
  - 1. **Stock Dashboard**: Grid view of customizable NIFTY & BANKNIFTY stocks showing LTP, change, and momentum with auto-refreshing logic.
  2. **Indices Dashboard**: Categorized view of NSE Major, Broad Market, Sectoral, and Thematic indices with market breadth indicators.
  3. **Semantic Theming**: Built-in Light and Dark Mode toggle embedded across the entire analytics suite, persisting user preferences seamlessly.
  - **Multi-Option Chart**: Build custom multi-leg option strategies and view net premium charts updating in real-time via WebSockets.
  - **Straddle Analysis**: Dedicated view for ATM straddle premiums with auto-scaling charts and custom strike selection.
  - **OI Buildup Heatmap**: NIFTY-focused heatmap tracking day-over-day OI buildup every minute. Loads full-day history from 9:15 AM on restart. Strikes auto-pin to current ATM ± 8 (50-pt intervals). Buildup classified as Long/Short Buildup, Short Covering, or Long Unwinding — all relative to previous session's baseline OI.
  - **Persistence Engine**: Automatic daily CSV snapshots of all index Greeks, allowing full state recovery on server restart.
  - **Unified Navigation**: Commonalized sidebar component for consistent navigation across all 14 analytics pages.
  - **Greeks Exposure Analysis**: Real-time tracking of systemic Delta and Gamma exposure per strike.
  - **Net GEX Regime Analysis**: Identification of Market Volatility Regimes (Traffic Light logic) and the Zero Gamma Flip Point.
- **Extensive Strategy Library**: Over 20+ detailed strategy implementations with comprehensive `README.md` guides covering entry/exit logic, risk management, and execution examples.
- **OI Pro Dashboards**: 15+ Advanced analytics pages including:
  - **Option PCR Grid**: Real-time Strike-wise PCR with Bull/Bear Sentiment indicators.
  - **Max Pain & Volatility Smile**: Automated Max Pain calculation with IV smile visualization.
  - **Cumulative GEX**: Systemic Gamma Exposure tracking with Regime Identification.
  - **Multi-Strike Comparison**: Contrast OI and Price action across up to 5 strikes simultaneously.
  - **Live Straddle Premium**: Real-time ATM straddle tracking with Mean Reversion indicators.

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
- **Role-Based Access (RBAC)**: Distinct permissions for `admin` and `user` roles.
- **Encrypted Storage**: Bcrypt hashing for all user credentials.
- **Persistent Database**: SQLite-based user management.

## 📚 Documentation

- [Agent Rules & Standards](.agent/rules/agent.md)
- [Console Output Guide](.agent/rules/agent_console_output.md)
- [Testing Guide](.agent/rules/agent_testing.md)

## 🤝 Contributing

Please ensure you follow the coding standards and workflow guidelines defined in `.agent/rules/` before submitting changes.
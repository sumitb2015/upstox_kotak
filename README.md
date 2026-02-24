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
- **OI Pro Analytics Dashboard**: Interactive web-based dashboard for real-time Open Interest (OI), PCR, and Greeks analysis.
  - **Multi-Option Chart**: Build custom multi-leg option strategies and view net premium charts updating in real-time via WebSockets.
  - **Straddle Analysis**: Dedicated view for ATM straddle premiums with auto-scaling charts and custom strike selection.
  - **OI Buildup Heatmap**: NIFTY-focused heatmap tracking day-over-day OI buildup every minute. Loads full-day history from 9:15 AM on restart. Strikes auto-pin to current ATM ± 8 (50-pt intervals). Buildup classified as Long/Short Buildup, Short Covering, or Long Unwinding — all relative to previous session's baseline OI.
  - **Persistence Engine**: Automatic daily CSV snapshots of all index Greeks, allowing full state recovery on server restart.
  - **Unified Navigation**: Commonalized sidebar component for consistent navigation across all 14 analytics pages.
  - **Greeks Exposure Analysis**: Real-time tracking of systemic Delta and Gamma exposure per strike.
  - **Net GEX Regime Analysis**: Identification of Market Volatility Regimes (Traffic Light logic) and the Zero Gamma Flip Point.

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
   - Ensure you have your API credentials ready.
   - Configure your strategy settings in the respective `config.py` files within the `strategies/` directory.

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

## 📚 Documentation

- [Agent Rules & Standards](.agent/rules/agent.md)
- [Console Output Guide](.agent/rules/agent_console_output.md)
- [Testing Guide](.agent/rules/agent_testing.md)

## 🤝 Contributing

Please ensure you follow the coding standards and workflow guidelines defined in `.agent/rules/` before submitting changes.
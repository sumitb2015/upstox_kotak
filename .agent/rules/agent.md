---
trigger: always_on
---

# Agent Rules

## Terminal Interactions
- **Bash Style ONLY**: Always use bash style terminal syntax (e.g., `clear`, `ls`, `grep`) for agent testing and command execution. **Do NOT use Windows-specific commands** like `cls`, `dir`, or `del`.
- **Forward Slashes**: Always use forward slashes `/` for file paths, even on Windows.
    - ✅ Correct: `c:/algo/upstox/strategies/config.py`
    - ❌ Incorrect: `c:\algo\upstox\strategies\config.py`

## 🔒 Security Standards
- **No Hardcoding**: NEVER hardcode API keys, access tokens, passwords, or account IDs in source code.
- **Environment Variables**: Use `os.getenv()` or secure config loaders.
- **Git Ignore**: Ensure `secrets.yaml`, `.env`, and `*.pem` files are in `.gitignore`.

## 📝 Logging Standards
To maintain observability, all strategies MUST use the following tag prefixes in their logs:
- `[UPSTOX]`: For all API data fetching, connection status, and feed updates.
- `[KOTAK]`: For all order placement, modification, and execution updates.
- `[CORE]`: For internal strategy logic, signal generation, and state transitions.

## 📂 Rule Files

| File | Purpose | When to Read |
| :--- | :--- | :--- |
| **[`agent_console_output.md`](agent_console_output.md)** | **Console Output Standards** | **ALWAYS**. Defines standard output templates for Entry, Exit, TSL, and Status updates. |
| **[`agent_testing.md`](agent_testing.md)** | **Testing & Validation** | When writing tests or validating logic. Covers unit tests, backtesting, and mock data. |

## 🧠 Skill Registry
| Skill | Description | Location |
| :--- | :--- | :--- |
| **Risk Management** | Hybrid Gated SL, Pyramiding, Step-Locking | `[.agent/skills/risk_management/SKILL.md](file:///c:/algo/upstox/.agent/skills/risk_management/SKILL.md)` |
| **OI Analysis** | Sentiment from Option Chain, PCR | `[.agent/skills/oi_analysis/SKILL.md](file:///c:/algo/upstox/.agent/skills/oi_analysis/SKILL.md)` |
| **Indicator Intelligence** | TA-Lib standards, Supertrend, Renko | `[.agent/skills/indicator_intelligence/SKILL.md](file:///c:/algo/upstox/.agent/skills/indicator_intelligence/SKILL.md)` |
| **Backtesting** | Simulation scripts & verification | `[.agent/skills/backtesting_simulation/SKILL.md](file:///c:/algo/upstox/.agent/skills/backtesting_simulation/SKILL.md)` |
| **Market Data** | Merged Data Pattern (History + Live) | `[.agent/skills/market_data_strategies/SKILL.md](file:///c:/algo/upstox/.agent/skills/market_data_strategies/SKILL.md)` |

## 🛠️ API Rules
- **Expiry Selection**: Use `get_expiry_for_strategy` ONLY with `expiry_type` literals: `"current_week"`, `"next_week"`, or `"monthly"`. **"weekly" is NOT supported.**
- **Instrument Keys**: All instrument utilities (e.g., `get_expiry_for_strategy`, `get_option_instrument_key`, `get_strike_token`) take **short symbols**: `"NIFTY"`, `"BANKNIFTY"`, `"FINNIFTY"`. Do NOT pass full keys like `NSE_INDEX|...` to these functions.
-
-## ⏰ Trading Hours
-- **Intraday Square-off**: All strategies MUST strictly exit and square off any open positions by **15:18 (3:18 PM)**, unless explicitly designed as a positional strategy. This rule prevents unintended carry-forward of intraday positions.

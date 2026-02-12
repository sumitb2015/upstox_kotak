# Agent Rules

## Terminal Interactions
- **Bash Style**: Always use bash style terminal syntax (e.g., `clear`, `ls`, `grep`) for agent testing and command execution. Avoid Windows-specific commands like `cls` unless absolutely necessary or running specifically in a batch context.

## 📂 Rule Files

| File | Purpose | When to Read |
| :--- | :--- | :--- |
| **[`agent_best_practices.md`](agent_best_practices.md)** | **Coding Standards & Safety** | **ALWAYS**. Covers critical safety rules (Atomic Execution, Auth, Logging), error handling, and performance patterns. |
| **[`agent_strategy_guidelines.md`](agent_strategy_guidelines.md)** | **Strategy Architecture** | When creating or refactoring a strategy. Defines structure, naming conventions, and standard patterns (Core/Live separation). |
| **[`agent_api_guide.md`](agent_api_guide.md)** | **API Usage** | When using Upstox/Kotak APIs. Explains wrappers, data fetching, and order management functions. |
| **[`agent_testing.md`](agent_testing.md)** | **Testing & Validation** | When writing tests or validating logic. Covers unit tests, backtesting, and mock data. |
| **[`agent_console_output.md`](agent_console_output.md)** | **Console Output Standards** | **ALWAYS**. Defines standard output templates for Entry, Exit, TSL, and Status updates. |

## 🛠️ API Rules
- **Expiry Selection**: Use `get_expiry_for_strategy` ONLY with `expiry_type` literals: `"current_week"`, `"next_week"`, or `"monthly"`. **"weekly" is NOT supported.**
- **Instrument Keys**: All instrument utilities (e.g., `get_expiry_for_strategy`, `get_option_instrument_key`, `get_strike_token`) take **short symbols**: `"NIFTY"`, `"BANKNIFTY"`, `"FINNIFTY"`. Do NOT pass full keys like `NSE_INDEX|...` to these functions.
-
-## ⏰ Trading Hours
-- **Intraday Square-off**: All strategies MUST strictly exit and square off any open positions by **15:18 (3:18 PM)**, unless explicitly designed as a positional strategy. This rule prevents unintended carry-forward of intraday positions.

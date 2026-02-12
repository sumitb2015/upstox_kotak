---
name: Backtesting & Simulation Skill
description: Instructions for validating strategy logic using simulation scripts before live deployment.
---

# Backtesting & Simulation Skill

This skill guides you through the process of verifying strategy logic using the existing simulation tools in `strategies/tools`.

## 🧪 1. Why Simulate?
Live markets are unforgiving. Simulation allows us to:
- verify logic without risking capital.
- test edge cases (gaps, rapid reversals).
- ensure indicators behave as expected.

## 🛠️ 2. Key Tools
These scripts are located in `strategies/tools/`:

| Script | Purpose |
| :--- | :--- |
| `analyze_adaptive_threshold.py` | Tests dynamic threshold logic against historical data. |
| `verify_directional_logic.py` | Validates entry/exit signals for directional strategies. |
| `visualize_adaptive_threshold.py` | Generates plots to visualize how thresholds adapt to market volatility. |

## 🚀 3. How to Run a Simulation
1.  **Prepare Data**: Ensure you have historical data in `data/historical`.
2.  **Configure Script**: Update the `SYMBOL` and `DATE_RANGE` in the script.
3.  **Execute**:
    ```bash
    python strategies/tools/verify_directional_logic.py
    ```
4.  **Analyze Output**: Look for "SIGNAL GENERATED" logs and verify they align with your strategy's rules.

## ✅ 4. Verification Checklist
Before approving a strategy for live trading:
- [ ] Does it handle Gap Up/Down correctly?
- [ ] Do Stop Losses trigger at the correct price levels?
- [ ] Are profit targets respected?
- [ ] Does the strategy shut down gracefully after `EXIT_TIME`?

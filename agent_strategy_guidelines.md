# Agent Strategy Guidelines

This document defines the architectural standards and patterns for all strategies in the `algo/upstox` codebase.

## 🏗️ Strategy Structure
All strategies must follow the **Core/Live separation** pattern:
- **`core.py`**: Contains pure business logic, indicator calculations, and signal generation. 
  - MUST NOT contain any API calls or broker interactions.
  - MUST be testable in isolation.
- **`live.py`**: The execution engine.
  - Handles API authentication, data fetching, and order placement.
  - Imports and uses the logic from `core.py`.
- **`config.py`**: centralized configuration.
  - Must include a `validate_config()` function.

## ⚙️ Configuration Rules
### Mandatory Expiry Selection
All strategies that trade options **MUST** allow the user to choose the expiry type in `config.py`.
- ** Parameter**: `expiry_type`
- **Supported Values**: `'current_week'`, `'next_week'`, `'monthly'`
- **Implementation**:
  ```python
  # config.py
  'expiry_type': 'current_week',  # Options: 'current_week', 'next_week', 'monthly'
  ```
  ```python
  # live.py
  self.expiry_date = get_expiry_for_strategy(
      self.access_token,
      expiry_type=config['expiry_type'],
      instrument=config['underlying']
  )
  ```
### State Persistence
State restoration MUST be **disabled by default** to preventing unintended position management after a restart.
- **Parameter**: `restore_state` (Default: `False`)
- **Implementation**:
  ```python
  # config.py
  'restore_state': False,
  ```

## 📦 Standard Patterns
- **Atomic Execution**: For multi-leg strategies (Spreads, Straddles), use atomic execution logic with rollback capability.
- **Logging**: Use the standard `agent_console_output` formats for all user-facing output.

## 📝 Documentation
- **Live Strategy Docs**: Always update the docstring header in `live.py` whenever strategy logic is modified. It must act as the source of truth for the strategy's behavior.

## 🛑 Graceful Shutdown
- **KeyboardInterrupt Handling**: All strategies MUST wrap their main `run()` loop in a `try...except KeyboardInterrupt` block.
- **Auto-Exit**: Upon interruption, the strategy MUST call a dedicated `exit_all()` method to close all open legs immediately.
- **Verification**: The exit logic MUST verify that orders are placed/completed before terminating the process.

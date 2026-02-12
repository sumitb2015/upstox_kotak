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

## ⏰ Global Time Exit
- **Mandatory 15:18 Exit**: All intraday strategies MUST implement a hard exit at **15:18:00**.
- **Reason**: To avoid auto-square-off charges by brokers and ensure positions are closed before market close.
- **Implementation**:
  ```python
  # config.py
  EXIT_TIME = "15:18:00"
  ```
  ```python
  # live.py
  if now.time() >= datetime.strptime(EXIT_TIME, "%H:%M:%S").time():
      self.square_off_all(tag="Intraday_Exit")
      sys.exit(0)
  ```

## 🔒 Deadlock Prevention (Multi-Action Strategies)
For strategies with **multiple conditional actions** (e.g., Pyramid, Roll, Reduce), ensure there is **always at least one valid action path** under any market condition.

### Common Deadlock Patterns
1. **Conflicting Guards**: Action A blocked by Guard X, Action B blocked by Guard Y, where X and Y can both be true simultaneously.
   - **Example**: Pyramid blocked by "Net Loss", Roll blocked by "Skew < 40%".
   - **Result**: Strategy freezes when Net Loss AND Skew is 30-40%.

2. **Circular Dependencies**: Action A requires state from Action B, which requires state from Action A.

### Prevention Rules
- **State-Aware Thresholds**: Adjust action thresholds dynamically based on portfolio state (Profit/Loss).
  - **Example**: Lower Roll threshold to Pyramid threshold when in Net Loss.
  ```python
  # Dynamic threshold based on Net Loss state
  if is_net_loss:
      roll_threshold = config['skew_threshold_pct']  # More aggressive
  else:
      roll_threshold = config['roll_skew_threshold']  # Standard
  ```

- **Fallback Actions**: Ensure at least one "escape hatch" action is always available.
  - **Example**: If Pyramid and Roll are both blocked, allow Reduction as a defensive fallback.

- **Testing**: Create reproduction scripts to simulate edge cases where multiple guards could trigger simultaneously.

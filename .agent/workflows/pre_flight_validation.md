---
description: Mandatory checklist and validation steps before starting a live trading session.
---

# Pre-Flight Validation Workflow

Perform these checks **15 minutes before market open** (09:00 AM IST) to ensure system readiness.

## 1. Environment Check
- [ ] **Internet**: Verify connectivity.
- [ ] **Time Sync**: Ensure system time is synced with NTP.
- [ ] **Disk Space**: Check if there is enough space for logs (`df -h`).

## 2. Authentication & Tokens
- [ ] **Upstox Token**: Generate a fresh access token for the day.
    - Run: `python lib/core/authentication.py --force`
    - Verify: `access_token.txt` is updated with today's date.
- [ ] **Kotak Session**: Verify Kotak Neo execution API login.

## 3. Financial Readiness
- [ ] **Margin Availablity**:
    - Run: `python lib/tools/check_margin.py` (if available) or check dashboard.
    - Ensure `Available Margin > Max Strategy Allocation`.
- [ ] **Holdings**: Verify no unexpected open positions from the previous day.

## 4. Strategy Configuration
- [ ] **Config File**: Review `strategies/target_strategy/config.py`.
    - `LOT_SIZE`: Is it set correctly for today?
    - `EXPIRY`: Is the correct expiry date set (especially on Thursdays)?
    - `DRY_RUN`: Set to `False` for real money, `True` for paper trading.

## 5. Dry Run Verification
- [ ] Run the strategy in `DRY_RUN = True` mode for 2 minutes to ensure:
    - It connects to the WebSocket.
    - It subscribes to tokens without error.
    - No "Crash" or "Traceback" on startup.

## 🟢 Launch
If all checks pass, start the strategy using `python live.py`.

---
description: Structured approach to debugging live strategy failures using log analysis.
---

# Incident Investigation Workflow

Follow this procedure when a strategy behaves unexpectedly (e.g., unintended exit, missing entry, order rejection).

## 1. Locate the Logs
All strategy logs are stored in `strategies/logs/`.
Identify the relevant log file by date: e.g., `strategies/logs/strategy_name_2024-05-21.log`.

## 2. Search for Error Tags
Use `grep` or search for the standard error tags:
- `ERROR`: General errors.
- `CRITICAL`: Severe failures (crashes).
- `[KOTAK] REJECTED`: Order rejections from the broker.

## 3. Analyze the Sequence
Reconstruct the event timeline:

1.  **Trigger**: What signal caused the action? Search for `[CORE] Signal Generated`.
2.  **Action**: Did the order go through? Search for `[KOTAK] Placed Order`.
3.  **Response**: What was the broker's reply?
    - If `REJECTED`: Check the `reason` field (e.g., "RMS: Margin Exceeded").
    - If `COMPLETE`: Check `avg_price`.

## 4. Common RCA (Root Cause Analysis) Patterns

| Symptom | Search Term | Probable Cause |
| :--- | :--- | :--- |
| **No Trade Entry** | `[CORE] Signal` | Check if `Trading View` signal arrived or if `filtering condition` (e.g., VWAP, OI) blocked it. |
| **Premature Exit** | `[CORE] Stop Loss` | Check if a rogue tick triggered the SL. Look at `ltp` values around the timestamp. |
| **Order Rejection** | `Margin` | Insufficient funds or blocked strike price. |
| **API Error** | `429`, `500` | Rate limiting or broker downtime. |

## 5. Remediation
- **Code Fix**: If logic was wrong, create a fix branch.
- **Config Adjust**: If thresholds were too tight, update `config.py`.
- **Manual Intervention**: If a position is stuck open, use the `square_off_all()` utility.

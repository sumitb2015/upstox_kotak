---
description: Standardized procedure for building and deploying a new trading strategy.
---

# Strategy Creation Workflow

1. **Directory Structure**: Create `strategies/category/my_strategy/` with `config.py`, `core.py`, `live.py`.
2. **Configuration**: Define parameters in `config.py`, include `validate_config()` and `EXIT_TIME`.
3. **Logic**: Implement pure math/logic in `core.py` (No API calls).
4. **Execution (`live.py`)**: 
    - **Authentication**: Usage of `lib.core.authentication.get_access_token` is MANDATORY.
    - **API Verification**: Check `quick_help/FUNCTION_REFERENCE.md` for every API call.
    - **Data Fetching**: Use `lib.api.market_data.fetch_historical_data` (for history) and `get_intraday_data_v3` (for live).
    
    **✅ STANDARD TEMPLATE**:
    Copy the pre-built template from: `[strategies/templates/live.py](file:///c:/algo/upstox/strategies/templates/live.py)`
    
    *It contains the correct imports, authentication boilerplate, and data fetching structure.*

5. **Documentation**: Create `README.md` with logic and diagrams.
6. **Validation**: Run manual tests and check margins.
7. **Code Review**: Conduct a final review for corner cases and critical errors.
8. **Deployment**: Test with `dry_run=True` and verify logs (`[UPSTOX]`, `[KOTAK]`, `[CORE]`).

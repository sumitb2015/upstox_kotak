"""
OI Pro Analytics - Dashboard Server
====================================
Main entry point for the OI Pro web application.
Handles real-time market data streaming, Greeks history polling, and strategy management.

Authentication: JWT-based security with SQLite user store.
API Base: /api
WebSocket Paths: /ws/market-watch, /ws/straddle, /ws/cumulative-prices

Author: OI Pro Team
"""
import sys
import os
import time
from datetime import datetime, timedelta
import asyncio
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("OIPRO")

# Force UTF-8 output so Windows cp1252 doesn't crash on any emoji/unicode in logs
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect, Depends, Request, Form
from fastapi.middleware.cors import CORSMiddleware
import json
import asyncio
import requests
from typing import Dict, List, Optional, Any
from pydantic import BaseModel
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
import uvicorn
import subprocess
import signal
import psutil
from pathlib import Path
import re
from contextlib import asynccontextmanager

# Add project root to path for lib imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# Import custom authentication module
from web_apps.oi_pro.auth import router as auth_router, init_db, get_current_user, check_admin, User, BrokerCredential, db, get_token

# --- Global Background Token Cache ---
# Replaced with redis_wrapper.get_raw("token:admin")

from lib.utils.redis_client import redis_wrapper
from lib.api.option_chain import get_expiries, get_option_chain_dataframe, calculate_pcr, calculate_volume_pcr, calculate_oi_change_pcr, calculate_max_pain
from lib.api.market_data import get_full_option_chain, fetch_historical_data
from lib.utils.instrument_utils import get_option_instrument_key
from lib.api.streaming import UpstoxStreamer
from lib.api.historical import get_intraday_data_v3
from lib.core.authentication import get_access_token as auth_get_token
from lib.utils.greeks_helper import calculate_gex_for_chain, get_net_gex, prepare_snapshot, get_total_exposure, calculate_flip_point
from lib.utils.greeks_storage import greeks_storage
# Fix #6: Fernet encryption helper for broker credentials at rest
from lib.utils.crypto_helper import encrypt_value, decrypt_value
from web_apps.oi_pro.news_service import start_news_scheduler, news_cache
# Fix #8: Rate limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import pandas as pd
from datetime import datetime

# --- Instrument Map for Dashboard ---
SYMBOL_MAP = {
    "NIFTY": "NSE_INDEX|Nifty 50",
    "BANKNIFTY": "NSE_INDEX|Nifty Bank",
    "FINNIFTY": "NSE_INDEX|Nifty Fin Service",
    "NIFTYIT": "NSE_INDEX|Nifty IT",
    "MIDCPNIFTY": "NSE_INDEX|NIFTY MID SELECT",
    "SENSEX": "BSE_INDEX|SENSEX",
    "NIFTY PHARMA": "NSE_INDEX|Nifty Pharma",
}
# Reverse map for broadcasting
KEY_TO_SYMBOL = {v: k for k, v in SYMBOL_MAP.items()}

# --- Nifty 50 Dashboard Config ---
NIFTY_50_KEYS = {
    "ADANIENT": "NSE_EQ|INE423A01024",
    "ADANIPORTS": "NSE_EQ|INE742F01042",
    "APOLLOHOSP": "NSE_EQ|INE437A01024",
    "ASIANPAINT": "NSE_EQ|INE021A01026",
    "AXISBANK": "NSE_EQ|INE238A01034",
    "BAJAJ-AUTO": "NSE_EQ|INE917I01010",
    "BAJAJFINSV": "NSE_EQ|INE918I01026",
    "BAJFINANCE": "NSE_EQ|INE296A01032",
    "BHARTIARTL": "NSE_EQ|INE397D01024",
    "BPCL": "NSE_EQ|INE029A01011",
    "BRITANNIA": "NSE_EQ|INE216A01030",
    "CIPLA": "NSE_EQ|INE059A01026",
    "COALINDIA": "NSE_EQ|INE522F01014",
    "DIVISLAB": "NSE_EQ|INE361B01024",
    "DRREDDY": "NSE_EQ|INE089A01031",
    "EICHERMOT": "NSE_EQ|INE066A01021",
    "GRASIM": "NSE_EQ|INE047A01021",
    "HCLTECH": "NSE_EQ|INE860A01027",
    "HDFCBANK": "NSE_EQ|INE040A01034",
    "HDFCLIFE": "NSE_EQ|INE795G01014",
    "HEROMOTOCO": "NSE_EQ|INE158A01026",
    "HINDALCO": "NSE_EQ|INE038A01020",
    "HINDUNILVR": "NSE_EQ|INE030A01027",
    "ICICIBANK": "NSE_EQ|INE090A01021",
    "INDUSINDBK": "NSE_EQ|INE095A01012",
    "INFY": "NSE_EQ|INE009A01021",
    "ITC": "NSE_EQ|INE154A01025",
    "JSWSTEEL": "NSE_EQ|INE019A01038",
    "KOTAKBANK": "NSE_EQ|INE237A01036",
    "LT": "NSE_EQ|INE018A01030",
    "LTIM": "NSE_EQ|INE214T01019",
    "M&M": "NSE_EQ|INE101A01026",
    "MARUTI": "NSE_EQ|INE585B01010",
    "NESTLEIND": "NSE_EQ|INE239A01024",
    "NTPC": "NSE_EQ|INE733E01010",
    "ONGC": "NSE_EQ|INE213A01029",
    "POWERGRID": "NSE_EQ|INE752E01010",
    "RELIANCE": "NSE_EQ|INE002A01018",
    "SBILIFE": "NSE_EQ|INE123W01016",
    "SBIN": "NSE_EQ|INE062A01020",
    "SUNPHARMA": "NSE_EQ|INE044A01036",
    "TATACONSUM": "NSE_EQ|INE192A01025",
    "TATASTEEL": "NSE_EQ|INE081A01020",
    "TCS": "NSE_EQ|INE467B01029",
    "TECHM": "NSE_EQ|INE669C01036",
    "TITAN": "NSE_EQ|INE280A01028",
    "TMPV": "NSE_EQ|INE155A01022",
    "ULTRACEMCO": "NSE_EQ|INE481G01011",
    "UPL": "NSE_EQ|INE628A01036",
    "WIPRO": "NSE_EQ|INE075A01022",
}

NIFTY_50_STOCKS = list(NIFTY_50_KEYS.keys())
NIFTY_50_REVERSE_MAP = {v: k for k, v in NIFTY_50_KEYS.items()}

# --- Bank Nifty Dashboard Config ---
BANKNIFTY_KEYS = {
    'PNB': 'NSE_EQ|INE160A01022',
    'KOTAKBANK': 'NSE_EQ|INE237A01036',
    'CANBK': 'NSE_EQ|INE476A01022',
    'BANKBARODA': 'NSE_EQ|INE028A01039',
    'YESBANK': 'NSE_EQ|INE528G01035',
    'SBIN': 'NSE_EQ|INE062A01020',
    'HDFCBANK': 'NSE_EQ|INE040A01034',
    'AUBANK': 'NSE_EQ|INE949L01017',
    'INDUSINDBK': 'NSE_EQ|INE095A01012',
    'AXISBANK': 'NSE_EQ|INE238A01034',
    'UNIONBANK': 'NSE_EQ|INE692A01016',
    'FEDERALBNK': 'NSE_EQ|INE171A01029',
    'ICICIBANK': 'NSE_EQ|INE090A01021',
    'IDFCFIRSTB': 'NSE_EQ|INE092T01019'
}
BANKNIFTY_STOCKS = list(BANKNIFTY_KEYS.keys())

# --- Indices Dashboard Config ---
INDICES_KEYS = {
    # Major / Nifty 50 Family Indices
    "NIFTY": "NSE_INDEX|Nifty 50",
    "BANKNIFTY": "NSE_INDEX|Nifty Bank",
    "FINNIFTY": "NSE_INDEX|Nifty Fin Service",
    "MIDCPNIFTY": "NSE_INDEX|NIFTY MID SELECT",
    "INDIA VIX": "NSE_INDEX|India VIX",
    # Broad Market Indices
    "NIFTYNXT50": "NSE_INDEX|Nifty Next 50",
    "NIFTY 100": "NSE_INDEX|Nifty 100",
    "NIFTY 200": "NSE_INDEX|Nifty 200",
    "NIFTY 500": "NSE_INDEX|Nifty 500",
    "NIFTY MIDCAP 50": "NSE_INDEX|Nifty Midcap 50",
    "NIFTY MIDCAP 100": "NSE_INDEX|NIFTY MIDCAP 100",
    "NIFTY SMLCAP 50": "NSE_INDEX|NIFTY SMLCAP 50",
    "NIFTY SMLCAP 100": "NSE_INDEX|NIFTY SMLCAP 100",
    "NIFTY SMLCAP 250": "NSE_INDEX|NIFTY SMLCAP 250",
    "NIFTY MICROCAP250": "NSE_INDEX|NIFTY MICROCAP250",
    "NIFTY TOTAL MKT": "NSE_INDEX|NIFTY TOTAL MKT",
    # Sectoral Indices
    "NIFTY AUTO": "NSE_INDEX|Nifty Auto",
    "NIFTY ENERGY": "NSE_INDEX|Nifty Energy",
    "NIFTY FMCG": "NSE_INDEX|Nifty FMCG",
    "NIFTY IT": "NSE_INDEX|Nifty IT",
    "NIFTY MEDIA": "NSE_INDEX|Nifty Media",
    "NIFTY METAL": "NSE_INDEX|Nifty Metal",
    "NIFTY PHARMA": "NSE_INDEX|Nifty Pharma",
    "NIFTY PVT BANK": "NSE_INDEX|Nifty Pvt Bank",
    "NIFTY PSU BANK": "NSE_INDEX|Nifty PSU Bank",
    "NIFTY REALTY": "NSE_INDEX|Nifty Realty",
    "NIFTY HEALTHCARE": "NSE_INDEX|NIFTY HEALTHCARE",
    "NIFTY CONSR DURBL": "NSE_INDEX|NIFTY CONSR DURBL",
    "NIFTY OIL AND GAS": "NSE_INDEX|NIFTY OIL AND GAS",
    # Thematic / Strategy Indices
    "NIFTY CPSE": "NSE_INDEX|Nifty CPSE",
    "NIFTY INFRA": "NSE_INDEX|Nifty Infra",
    "NIFTY MNC": "NSE_INDEX|Nifty MNC",
    "NIFTY PSE": "NSE_INDEX|Nifty PSE",
    "NIFTY COMMODITIES": "NSE_INDEX|Nifty Commodities",
    "NIFTY CONSUMPTION": "NSE_INDEX|Nifty Consumption",
    "NIFTY IND DEFENCE": "NSE_INDEX|Nifty Ind Defence",
    "NIFTY IPO": "NSE_INDEX|Nifty IPO",
    "NIFTY DIV OPPS 50": "NSE_INDEX|Nifty Div Opps 50",
    "NIFTY50 VALUE 20": "NSE_INDEX|Nifty50 Value 20",
    "NIFTY100 ESG": "NSE_INDEX|NIFTY100 ESG",
}

# Lookup for fetching LTP by symbol (Dynamic)
# Replaced with redis_wrapper.set_raw("symbol_lookup:...", ...)

# --- Global Cache for Greeks History ---
# Replaced with Redis lists: greeks_chain:* and heatmap:*
GREEKS_LOCK = asyncio.Lock()
HEATMAP_LOCK = asyncio.Lock()
LAST_CACHE_RESET_DATE = datetime.now().date()

# --- Global Cache for Previous Closes (Indices) ---
# Replaced with redis_wrapper.hset_json("PREV_CLOSES", ...)

# --- Baseline OI for Heatmap (fetched once at startup, static for the day) ---
# Replaced with redis_wrapper.hset_json("BASELINE_OI", ...)

def tail_file(filename, lines=100):
    """Efficiently get the last N lines of a file by seeking to the end."""
    try:
        if not os.path.exists(filename):
            return "Log file not found."
        with open(filename, 'rb') as f:
            f.seek(0, os.SEEK_END)
            buffer = bytearray()
            pointer = f.tell()
            lines_found = 0
            while pointer > 0 and lines_found <= lines:
                pointer -= 1
                f.seek(pointer)
                char = f.read(1)
                if char == b'\n':
                    lines_found += 1
                buffer.extend(char)
            return buffer[::-1].decode('utf-8', errors='replace')
    except HTTPException as he:
        raise he
    except Exception as e:
        return f"Error tailing log: {str(e)}"


# --- Strategy Management ---

# Fix #7: Use portable relative paths, not Windows-hardcoded 'c:\\...' strings.
# Override at deploy time by setting the STRATEGIES_BASE_PATH env variable.
_default_strategies_path = Path(__file__).parent.parent.parent / "strategies"
STRATEGIES_BASE_PATH = Path(os.getenv("STRATEGIES_BASE_PATH", str(_default_strategies_path)))

STRATEGIES_INFO = {
    "aggressive_renko_dip": {
        "id": "aggressive_renko_dip",
        "name": "Aggressive Renko Dip",
        "path": STRATEGIES_BASE_PATH / "directional" / "aggressive_renko_dip",
        "description": "Trend-following strategy using Renko bricks and RSI filters."
    },
    "dynamic_straddle_skew": {
        "id": "dynamic_straddle_skew",
        "name": "Dynamic Straddle Skew",
        "path": STRATEGIES_BASE_PATH / "directional" / "dynamic_straddle_skew",
        "description": "Delta-neutral straddle adjustment strategy based on skew momentum."
    }
}

class StrategyManager:
    """
    Manages background strategy processes.
    Handles starting, stopping, monitoring logs, and tracking PnL state.
    """
    def __init__(self):
        """Initializes the StrategyManager with empty tracking dicts."""
        self.processes: Dict[str, subprocess.Popen] = {}
        self.start_times: Dict[str, datetime] = {}
        self.log_files: Dict[str, object] = {}
        
    def _check_is_running(self, strategy_id: str) -> bool:
        """Helper to check if strategy is running (memory or system check)."""
        # 1. Internal memory check
        proc = self.processes.get(strategy_id)
        if proc and proc.poll() is None:
            return True
            
        # 2. System check (psutil) - Recovery for restarts
        for p in psutil.process_iter(['pid', 'cmdline']):
            try:
                cmdline = p.info['cmdline']
                if cmdline and "live.py" in cmdline[-1] and strategy_id in "".join(cmdline):
                    # Recover process handle if missing
                    if strategy_id not in self.processes:
                        # We can't easily recover subprocess.Popen object but we know it's running
                        # We could reconstruct a Popen wrapper if needed, but for now just returning True
                        pass
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False

    async def get_strategy_status(self, strategy_id: str) -> Dict:
        """Checks if a strategy process is running and returns its metadata."""
        is_running = await run_in_threadpool(self._check_is_running, strategy_id)
        pid = None
        uptime = None
        
        # Try to get PID/Uptime if running
        proc = self.processes.get(strategy_id)
        if proc and proc.poll() is None:
            pid = proc.pid
            uptime_delta = datetime.now() - self.start_times.get(strategy_id, datetime.now())
            uptime = str(uptime_delta).split('.')[0] # HH:MM:SS
        elif is_running:
            # Running but handle lost, find PID via psutil again for display
            def find_pid():
                for p in psutil.process_iter(['pid', 'cmdline']):
                    try:
                        cmdline = p.info['cmdline']
                        if cmdline and "live.py" in cmdline[-1] and strategy_id in "".join(cmdline):
                            return p.info['pid'], datetime.fromtimestamp(p.create_time())
                    except:
                        pass
                return None, None
                
            found_pid, create_time = await run_in_threadpool(find_pid)
            if found_pid:
                pid = found_pid
                if create_time:
                    self.start_times[strategy_id] = create_time
                    uptime_delta = datetime.now() - create_time
                    uptime = str(uptime_delta).split('.')[0]

        # Get PnL from state file if it exists AND strategy is running
        pnl = 0.0
        state_details = {}
        
        if is_running:
            info = STRATEGIES_INFO.get(strategy_id)
            if info:
                state_file = info['path'] / "strategy_state.json"
                
                def read_state_file():
                    if state_file.exists():
                        try:
                            with open(state_file, 'r') as f:
                                return json.load(f)
                        except:
                            pass
                    return None
                    
                state = await run_in_threadpool(read_state_file)
                if state:
                    pnl = state.get('pnl', 0.0) or state.get('total_pnl', 0.0)
                    state_details['entry_state'] = state.get('entry_state', 'UNKNOWN')
                    state_details['total_qty'] = state.get('total_qty', 0)
                    raw_positions = state.get('active_positions', {})
                    enhanced_positions = {}
                    
                    for sym, qty in raw_positions.items():
                        ltp = None
                        key = redis_wrapper.get_raw(f"symbol_lookup:{sym}")
                        if key:
                            # Try any active user streamer for LTP lookup
                            s = streamer_registry.get_any()
                            if s:
                                data = s.get_latest_data(key)
                                if data:
                                    ltp = data.get('ltp')
                        enhanced_positions[sym] = {"qty": qty, "ltp": ltp}
                    state_details['positions'] = enhanced_positions

        return {
            "id": strategy_id,
            "is_running": is_running,
            "pid": pid,
            "uptime": uptime,
            "pnl": round(pnl, 2),
            "details": state_details
        }

    async def start_strategy(self, strategy_id: str):
        """Starts a strategy live.py as a background process."""
        if strategy_id in self.processes and self.processes[strategy_id].poll() is None:
            raise HTTPException(status_code=400, detail="Strategy already running")
            
        info = STRATEGIES_INFO.get(strategy_id)
        if not info:
             raise HTTPException(status_code=404, detail="Strategy not found")
             
        live_file = info['path'] / "live.py"
        if not await run_in_threadpool(live_file.exists):
            raise HTTPException(status_code=404, detail="live.py not found")
            
        # Set PYTHONPATH to project root so imports work
        env = os.environ.copy()
        # Fix #7: Use portable path relative to this file, not Windows-hardcoded path
        project_root = str(Path(__file__).parent.parent.parent.resolve())
        env["PYTHONPATH"] = os.environ.get("PYTHONPATH", project_root)
        
        try:
            # Create/Open log file (overwrite for fresh logs on new run)
            log_path = info['path'] / "strategy.log"
            
            def open_log():
                return open(log_path, "w")
                
            self.log_files[strategy_id] = await run_in_threadpool(open_log)

            # Run in a new process group so it doesn't die with main.py if needed
            # On Windows, we use creationflags
            proc = subprocess.Popen(
                [sys.executable, "-u", str(live_file)],
                cwd=str(info['path']),
                env=env,
                stdout=self.log_files[strategy_id], 
                stderr=subprocess.STDOUT, # Redirect stderr to stdout
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
            )
            self.processes[strategy_id] = proc
            self.start_times[strategy_id] = datetime.now()
            return {"status": "success", "pid": proc.pid}
        except HTTPException as he:
            raise he
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to start: {str(e)}")

    async def stop_strategy(self, strategy_id: str):
        """Terminated a strategy process. Tries graceful stop via file signal first."""
        # 1. Check internal tracking
        proc = self.processes.get(strategy_id)
        info = STRATEGIES_INFO.get(strategy_id)
        
        if proc:
            # A. Graceful Stop Signal (.STOP file)
            if info:
                stop_signal_file = info['path'] / ".STOP"
                try:
                    await run_in_threadpool(stop_signal_file.touch)
                    # Wait for strategy to pick it up and exit (max 5s)
                    for _ in range(50):
                        if proc.poll() is not None:
                            break
                        await asyncio.sleep(0.1)
                except HTTPException as he:
                    raise he
                except Exception as e:
                    logger.error(f"[CORE] Error sending stop signal: {e}")

            # B. Force Terminate if still running
            if proc.poll() is None:
                def kill_process():
                    try:
                        p = psutil.Process(proc.pid)
                        for child in p.children(recursive=True):
                            child.terminate()
                        p.terminate()
                        p.wait(timeout=3)
                    except:
                        if proc.poll() is None:
                            proc.kill()
                await run_in_threadpool(kill_process)
            
            # C. Cleanup
            if strategy_id in self.processes: del self.processes[strategy_id]
            if strategy_id in self.start_times: del self.start_times[strategy_id]
            
            # Close log file handle if open
            if strategy_id in self.log_files:
                try:
                    await run_in_threadpool(self.log_files[strategy_id].close)
                except:
                    pass
                del self.log_files[strategy_id]
                
            # Remove signal file if it still exists
            if info:
                def cleanup_stop_file():
                    if (info['path'] / ".STOP").exists():
                        try: (info['path'] / ".STOP").unlink()
                        except: pass
                await run_in_threadpool(cleanup_stop_file)

            return {"status": "stopped"}
        
        # 2. Check psutil (for orphaned processes)
        def terminate_orphans():
            stopped = False
            for p in psutil.process_iter(['pid', 'cmdline']):
                try:
                    cmdline = p.info['cmdline']
                    if cmdline and "live.py" in cmdline[-1] and strategy_id in "".join(cmdline):
                        p.terminate()
                        stopped = True
                except:
                    continue
            return stopped
                
        if await run_in_threadpool(terminate_orphans):
            return {"status": "stopped"}
            
        raise HTTPException(status_code=400, detail="Strategy not running")

    async def get_strategy_logs(self, strategy_id: str, lines: int = 100) -> Dict:
        """Reads the last N lines from the strategy log file using efficient tailing."""
        info = STRATEGIES_INFO.get(strategy_id)
        if not info:
             raise HTTPException(status_code=404, detail="Strategy not found")
        
        log_file = info['path'] / "strategy.log"
        content = await run_in_threadpool(tail_file, str(log_file), lines)
        
        return {
            "strategy_id": strategy_id,
            "logs": content
        }

strategy_manager = StrategyManager()

app = FastAPI(title="OI Pro Analytics API", version="1.0.0")

# Fix #8: Use the shared limiter from auth.py (single instance for auth routes)
from web_apps.oi_pro.auth import auth_limiter
if auth_limiter:
    app.state.limiter = auth_limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ─── Middleware Block (must be registered BEFORE routes) ─────────────────────
#
# Fix #10: Security Headers Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Injects standard HTTP security headers on every response."""
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response

app.add_middleware(SecurityHeadersMiddleware)

# Fix #3: CORS — env-configurable origin whitelist.
# Set CORS_ORIGINS to a comma-separated list of allowed origins in .env
# Default: localhost only (safe for development)
_cors_origins_raw = os.getenv("CORS_ORIGINS", "http://localhost:8001,http://127.0.0.1:8001")
ALLOWED_ORIGINS = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
if "*" in ALLOWED_ORIGINS:
    import logging as _clog
    _clog.getLogger("OIPRO").critical(
        "[SECURITY] CORS_ORIGINS contains '*' — this is unsafe in production! "
        "Set explicit allowed origins in your .env file."
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

@app.middleware("http")
async def db_session_middleware(request: Request, call_next):
    # Ensure fresh DB connection per request to prevent SQLite thread locks
    db.connect(reuse_if_open=True)
    try:
        response = await call_next(request)
        return response
    finally:
        if not db.is_closed():
            db.close()

# Register auth routes
app.include_router(auth_router)

# --- PoP & Premium Analytics ---
from fastapi.concurrency import run_in_threadpool

def calculate_theoretical_pop(delta: float, option_type: str) -> float:
    """
    Calculate Probability of Profit (PoP) for checking SHORT positions.
    Approximation: PoP = 1 - |Delta|
    """
    if delta is None:
        return 0.0
    
    abs_delta = abs(delta)
    pop = 100 * (1 - abs_delta)
    return round(pop, 1)

@app.get("/api/pop-data")
async def get_pop_data(current_user: User = Depends(get_current_user),
                      symbol: str = Query(..., description="Symbol like NIFTY"), 
                      expiry: str = Query(..., description="Expiry Date")):
    """
    Get data for Seller's Probability Edge Scatter Plot (Premium vs Risk).
    """
    logger.info(f"[CORE] [PoP API] Request received for {symbol} expiry {expiry}")
    try:
        instrument_key = SYMBOL_MAP.get(symbol.upper())
        if not instrument_key:
            raise HTTPException(status_code=400, detail="Invalid symbol")
            
        token = await get_access_token(current_user)
        
        # Run blocking call in threadpool to prevent freezing the server
        logger.info(f"[UPSTOX] [PoP API] Fetching option chain for {instrument_key}...")
        df = await run_in_threadpool(get_option_chain_dataframe, token, instrument_key, expiry)
        
        if df is None or df.empty:
            logger.warning(f"[UPSTOX] [PoP API] No data found for {symbol}")
            return {"data": []}

        logger.info(f"[CORE] [PoP API] Processing {len(df)} rows...")
        
        # Process DataFrame for Chart
        points = []
        
        for _, row in df.iterrows():
            strike = row['strike_price']
            
            # --- CE Data ---
            ce_ltp = row.get('ce_ltp') or 0
            ce_delta = row.get('ce_delta')
            ce_oi = row.get('ce_oi') or 0
            
            # Filter garbage data
            if ce_ltp > 2.0 and ce_oi > 0:
                ce_pop = calculate_theoretical_pop(ce_delta, "CE")
                
                # We typically sell OTM calls (Strike > Spot), but the Delta formula handles ITM too
                points.append({
                    "type": "CE",
                    "strike": strike,
                    "premium": ce_ltp,
                    "pop": ce_pop,
                    "oi": ce_oi,
                    "delta": ce_delta,
                    "label": f"{strike} CE"
                })

            # --- PE Data ---
            pe_ltp = row.get('pe_ltp') or 0
            pe_delta = row.get('pe_delta')
            pe_oi = row.get('pe_oi') or 0
            
            if pe_ltp > 2.0 and pe_oi > 0:
                pe_pop = calculate_theoretical_pop(pe_delta, "PE")
                
                points.append({
                    "type": "PE",
                    "strike": strike,
                    "premium": pe_ltp,
                    "pop": pe_pop,
                    "oi": pe_oi,
                    "delta": pe_delta,
                    "label": f"{strike} PE"
                })
                
        # Sort by PoP for clean rendering if needed
        points.sort(key=lambda x: x['pop'], reverse=True)
        
        logger.info(f"[CORE] [PoP API] Returning {len(points)} data points")
        return {"data": points}
        
    except HTTPException as he:
        raise he
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/news")
async def get_market_news(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    source: str = Query("All")
):
    """Fetch paginated news from cache."""
    try:
        articles = news_cache.get("articles", [])
        last_updated = news_cache.get("last_updated")
        
        if source != "All":
            articles = [a for a in articles if a['source'] == source]
        
        total = len(articles)
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paginated_data = articles[start_idx:end_idx]
        
        return {
            "status": "success",
            "data": paginated_data,
            "pagination": {
                "total": total,
                "page": page,
                "limit": limit,
                "has_more": end_idx < total
            },
            "last_updated": last_updated
        }
    except Exception as e:
        logger.error(f"Error fetching news: {e}")
        return {"status": "error", "message": str(e), "data": []}

# --- Strategy Management API ---

@app.get("/api/strategies")
async def list_strategies(current_user: User = Depends(get_current_user)):
    """Returns status of all tracked strategies."""
    results = []
    for strategy_id in STRATEGIES_INFO:
        status = await strategy_manager.get_strategy_status(strategy_id)
        info = STRATEGIES_INFO[strategy_id]
        results.append({
            **status,
            "name": info["name"],
            "description": info["description"]
        })
    return {"strategies": results}

@app.post("/api/strategies/start/{strategy_id}")
async def start_strategy(strategy_id: str, admin: User = Depends(check_admin)):
    return await strategy_manager.start_strategy(strategy_id)

@app.post("/api/strategies/stop/{strategy_id}")
async def stop_strategy(strategy_id: str, admin: User = Depends(check_admin)):
    return await strategy_manager.stop_strategy(strategy_id)

@app.get("/api/strategies/logs/{strategy_id}")
async def get_strategy_logs(strategy_id: str, current_user: User = Depends(get_current_user)):
    return await strategy_manager.get_strategy_logs(strategy_id)

@app.get("/api/strategies/config/{strategy_id}")
async def get_strategy_config(strategy_id: str, current_user: User = Depends(get_current_user)):
    """Parses config.py and returns the CONFIG dictionary."""
    info = STRATEGIES_INFO.get(strategy_id)
    if not info:
        raise HTTPException(status_code=404, detail="Strategy not found")
        
    config_file = info['path'] / "config.py"
    if not await run_in_threadpool(config_file.exists):
        raise HTTPException(status_code=404, detail="config.py not found")
        
    try:
        def import_config():
            import importlib.util
            spec = importlib.util.spec_from_file_location("config", str(config_file))
            config_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(config_module)
            return config_module.CONFIG
            
        config_data = await run_in_threadpool(import_config)
        return {"config": config_data}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read config: {str(e)}")

@app.post("/api/strategies/config/{strategy_id}")
async def update_strategy_config(strategy_id: str, new_config: Dict, admin: User = Depends(check_admin)):
    """Updates specific keys in config.py using regex to preserve comments."""
    info = STRATEGIES_INFO.get(strategy_id)
    if not info:
        raise HTTPException(status_code=404, detail="Strategy not found")
        
    config_file = info['path'] / "config.py"
    if not config_file.exists():
        raise HTTPException(status_code=404, detail="config.py not found")
        
    try:
        content = await run_in_threadpool(config_file.read_text)
        
        for key, value in new_config.items():
            if isinstance(value, str):
                replacement_val = f"'{value}'"
            elif isinstance(value, bool):
                replacement_val = str(value)
            else:
                replacement_val = str(value)
                
            pattern = rf"(['\"]{key}['\"]\s*:\s*).*?(?=[,\s]*#|[,\s]*$|\s*,)"
            match = re.search(pattern, content)
            if match:
                 content = re.sub(pattern, rf"\g<1>{replacement_val}", content)
            else:
                pass
            
        await run_in_threadpool(config_file.write_text, content)
        return {"status": "success", "message": "Configuration updated"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update config: {str(e)}")

# --- Broker Management API ---

@app.get("/api/broker/status")
def broker_status(current_user: User = Depends(get_current_user)):
    """
    Lightweight endpoint for sidebar.js to check if the user has
    a valid broker token. Returns {has_token: bool}.
    Used as the access control gate — dashboard pages are only
    accessible when has_token=True.
    """
    has_token = BrokerCredential.select().where(
        BrokerCredential.user == current_user,
        BrokerCredential.access_token.is_null(False),
        BrokerCredential.access_token != ""
    ).exists()
    return {"has_token": has_token}

@app.get("/api/brokers")
def list_brokers(current_user: User = Depends(get_current_user)):
    """Returns the list of brokers for the current user."""
    brokers = BrokerCredential.select().where(BrokerCredential.user == current_user).dicts()
    return [{
        "id": b["id"],
        "broker_name": b["broker_name"],
        "name_tag": b["name_tag"],
        "api_key": "***" + b["api_key"][-4:] if b["api_key"] else None,
        "api_secret": "***" + b["api_secret"][-4:] if b["api_secret"] else None,
        "redirect_uri": b["redirect_uri"],
        "status": b["status"],
        "token_exists": True if b["access_token"] else False,
        "last_token_at": b["last_token_at"].strftime("%d-%m-%Y, %H:%M") if b["last_token_at"] else "-",
        "created_at": b["created_at"].strftime("%d-%m-%Y, %H:%M") if b["created_at"] else "-"
    } for b in brokers]

@app.post("/api/brokers")
def add_broker(broker_data: dict, current_user: User = Depends(get_current_user)):
    """Creates or updates broker credentials for the current user."""
    broker_id = broker_data.get("id")
    broker_name = broker_data.get("broker_name", "Upstox")
    name_tag = broker_data.get("name_tag")
    api_key = broker_data.get("api_key")
    api_secret = broker_data.get("api_secret")
    redirect_uri = broker_data.get("redirect_uri")

    if broker_id:
        # Update existing
        try:
            broker = BrokerCredential.get((BrokerCredential.id == broker_id) & (BrokerCredential.user == current_user))
            broker.name_tag = name_tag
            broker.redirect_uri = redirect_uri
            
            # Update secrets only if they are not the masked placeholders
            if api_key and not api_key.startswith("***"):
                broker.api_key = encrypt_value(api_key)  # Fix #6
            if api_secret and not api_secret.startswith("***"):
                broker.api_secret = encrypt_value(api_secret)  # Fix #6
                
            broker.save()
            return {"status": "success", "message": "Broker updated successfully", "id": broker.id}
        except BrokerCredential.DoesNotExist:
            raise HTTPException(status_code=404, detail="Broker not found")
    else:
        # Create new
        if not api_key or not api_secret:
            raise HTTPException(status_code=400, detail="API Key and API Secret are required")

        broker = BrokerCredential.create(
            user=current_user,
            broker_name=broker_name,
            name_tag=name_tag,
            api_key=encrypt_value(api_key),        # Fix #6
            api_secret=encrypt_value(api_secret),  # Fix #6
            redirect_uri=redirect_uri
        )
        return {"status": "success", "message": "Broker saved successfully", "id": broker.id}

@app.delete("/api/brokers/{broker_id}")
def delete_broker(broker_id: int, current_user: User = Depends(get_current_user)):
    """Deletes the specified broker credential."""
    try:
        broker = BrokerCredential.get((BrokerCredential.id == broker_id) & (BrokerCredential.user == current_user))
        broker.delete_instance()
        return {"status": "success", "message": "Broker deleted"}
    except BrokerCredential.DoesNotExist:
        raise HTTPException(status_code=404, detail="Broker not found")

@app.post("/api/brokers/generate-token/{broker_id}")
def generate_broker_token(broker_id: int, current_user: User = Depends(get_current_user)):
    """
    Returns the Upstox Auth URL to initiate manual login.
    """
    try:
        broker = BrokerCredential.get((BrokerCredential.id == broker_id) & (BrokerCredential.user == current_user))
        
        # Construct Upstox Auth URL
        # redirect_uri must match what's in Upstox Developer Portal
        # We use state to pass broker_id for the callback to identify the entry
        # Fix #6: Decrypt credentials before use in OAuth URL
        decrypted_key = decrypt_value(broker.api_key)
        # Fix #9: Sign the state parameter with HMAC to prevent IDOR enumeration
        import hmac as _hmac
        import hashlib as _hashlib
        from web_apps.oi_pro.auth import SECRET_KEY as _JWT_SECRET
        state_payload = str(broker.id)
        state_sig = _hmac.new(
            _JWT_SECRET.encode("utf-8"),
            state_payload.encode("utf-8"),
            _hashlib.sha256
        ).hexdigest()
        signed_state = f"{state_sig}:{state_payload}"
        auth_url = (
            f"https://api-v2.upstox.com/login/authorization/dialog"
            f"?response_type=code"
            f"&client_id={decrypted_key}"
            f"&redirect_uri={requests.utils.quote(broker.redirect_uri or 'http://127.0.0.1:8001/api/brokers/callback/upstox')}"
            f"&state={signed_state}"
        )
        
        return {"status": "success", "auth_url": auth_url}
    except BrokerCredential.DoesNotExist:
        raise HTTPException(status_code=404, detail="Broker not found")

@app.get("/api/brokers/callback/upstox")
def upstox_callback(request: Request, code: str, state: str):
    """
    OAuth Callback for Upstox.
    Exchanges authorization code for access token.
    Fix #9: Validates HMAC-signed state to prevent IDOR broker enumeration.
    """
    # --- Fix #9: Verify HMAC-signed state before looking up broker ---
    import hmac as _hmac
    import hashlib as _hashlib
    from web_apps.oi_pro.auth import SECRET_KEY as _JWT_SECRET

    try:
        sig, broker_id = state.split(":", 1)
        expected_sig = _hmac.new(
            _JWT_SECRET.encode("utf-8"),
            broker_id.encode("utf-8"),
            _hashlib.sha256
        ).hexdigest()
        if not _hmac.compare_digest(sig, expected_sig):
            raise ValueError("Invalid state signature")
    except (ValueError, AttributeError):
        return HTMLResponse(content="<h2>Invalid OAuth state. Possible CSRF attack.</h2>", status_code=400)

    try:
        broker = BrokerCredential.get_by_id(broker_id)
        
        # Token Exchange
        token_url = "https://api-v2.upstox.com/login/authorization/token"
        headers = {
            "accept": "application/json",
            "Api-Version": "2.0",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "code": code,
            "client_id": broker.api_key,
            "client_secret": broker.api_secret,
            "redirect_uri": broker.redirect_uri or 'http://127.0.0.1:8001/api/brokers/callback/upstox',
            "grant_type": "authorization_code",
        }
        
        response = requests.post(token_url, headers=headers, data=data)
        jsr = response.json()
        
        access_token = jsr.get("access_token")
        if not access_token:
            if "application/json" in request.headers.get("accept", ""):
                return {"status": "error", "message": "Auth failed", "details": jsr}
            return HTMLResponse(content=f"<h2>Auth Failed</h2><pre>{json.dumps(jsr, indent=2)}</pre>", status_code=400)
            
        # Update Broker entry — Fix #6: encrypt access token before storing
        broker.access_token = encrypt_value(access_token)
        broker.last_token_at = datetime.utcnow()
        broker.status = "Active"
        broker.save()
        
        # Return an HTML page that messages the parent and closes itself
        success_html = """
        <html>
            <head>
                <title>Authentication Successful</title>
                <style>
                    body { background: #0f172a; color: white; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; font-family: sans-serif; margin: 0; }
                    .spinner { border: 4px solid rgba(255,255,255,0.1); width: 40px; height: 40px; border-radius: 50%; border-left-color: #10b981; animation: spin 1s linear infinite; margin-bottom: 20px; }
                    @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
                </style>
            </head>
            <body>
                <div class="spinner"></div>
                <h2>Authentication Successful!</h2>
                <p style="color: #94a3b8;">Finalizing and closing window...</p>
                <script>
                    if (window.opener) {
                        window.opener.postMessage('upstox_auth_success', '*');
                        setTimeout(() => window.close(), 1000);
                    } else {
                        window.location.href = '/brokers?token_success=true';
                    }
                </script>
            </body>
        </html>
        """
        return HTMLResponse(content=success_html)
        
    except HTTPException as he:
        raise he
    except Exception as e:
        import traceback
        return HTMLResponse(content=f"<h2>Callback Error</h2><p>{str(e)}</p><pre>{traceback.format_exc()}</pre>", status_code=500)

# --- WebSocket Connection Manager ---
class ConnectionManager:
    def __init__(self):
        # Map instrument keys to list of WebSocket connections (for Straddle/Custom subs)
        self.subscriptions: Dict[str, List[WebSocket]] = {}
        # List of connections for the main Dashboard Market Watch (indices)
        self.market_watch_sockets: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()

    def disconnect(self, websocket: WebSocket):
        # Remove from subscriptions
        for key in list(self.subscriptions.keys()):
            if websocket in self.subscriptions[key]:
                self.subscriptions[key].remove(websocket)
                if not self.subscriptions[key]:
                    del self.subscriptions[key]
        
        # Remove from market watch
        if websocket in self.market_watch_sockets:
            self.market_watch_sockets.remove(websocket)

    async def connect_market_watch(self, websocket: WebSocket):
        """Connect a socket specifically for dashboard market watch"""
        await websocket.accept()
        self.market_watch_sockets.append(websocket)

    async def subscribe(self, websocket: WebSocket, instrument_keys: List[str], user_streamer=None, mode: str = "ltpc"):
        """
        Subscribe a websocket to specific instrument keys.
        mode: 'ltpc' for price-only ticks, 'full' to include OI, Greeks, OHLC in every tick.
        """
        normalized_keys = [k.replace(':', '|') for k in instrument_keys]
        logger.info(f"[UPSTOX] [WS] Subscribing socket to: {normalized_keys} (mode={mode})")
        for key in normalized_keys:
            if key not in self.subscriptions:
                self.subscriptions[key] = []
            if websocket not in self.subscriptions[key]:
                self.subscriptions[key].append(websocket)
        
        # Trigger subscription on the user's dedicated Upstox Streamer
        # (user_streamer injected by the WS endpoint that calls this method)
        if user_streamer:
            # Wait up to 5 seconds for the streamer to fully connect before subscribing.
            # This prevents the 'socket is already closed' race condition that occurs
            # when a fresh streamer is created but the WS handshake hasn't completed yet.
            max_wait = 5.0
            elapsed = 0.0
            while not user_streamer.market_data_connected and elapsed < max_wait:
                logger.info(f"[UPSTOX] [WS] Waiting for streamer to connect before subscribing... ({elapsed:.1f}s)")
                await asyncio.sleep(0.5)
                elapsed += 0.5
            
            if not user_streamer.market_data_connected:
                logger.error(f"[UPSTOX] [WS] Streamer did not connect within {max_wait}s. Subscription FAILED for: {normalized_keys}")
                return

            if user_streamer.market_streamer:
                try:
                    user_streamer.subscribe_market_data(normalized_keys, mode=mode)
                    logger.info(f"[UPSTOX] [WS] Successfully subscribed (mode={mode}) to: {normalized_keys}")
                except HTTPException as he:
                    raise he
                except Exception as e:
                    logger.error(f"[UPSTOX] [WS] Error subscribing to keys {normalized_keys}: {e}")

    async def broadcast(self, message: dict):
        """
        Broadcasts message to relevant subscribers based on instrument_key.
        Also broadcasts to Market Watch if the key is an index.
        This method must be called from an async loop.
        """
        instrument_key = message.get('instrument_key')
        if instrument_key:
            instrument_key = instrument_key.replace(':', '|')
        
        # 1. Targeted Subscriptions (Straddle Chart)
        if instrument_key and instrument_key in self.subscriptions:
            to_remove = []
            for connection in self.subscriptions[instrument_key]:
                try:
                    await connection.send_json(message)
                except HTTPException as he:
                    raise he
                except Exception as e:
                    logger.warning(f"[UPSTOX] [WS] Disconnecting broken pipe for {instrument_key}")
                    to_remove.append(connection)
            for conn in to_remove:
                self.disconnect(conn)

        # 2. Market Watch Broadcast (Dashboard Indices)
        # Check if this key is one of our indices
        if instrument_key and instrument_key in KEY_TO_SYMBOL:
            symbol = KEY_TO_SYMBOL[instrument_key]
            # Format message for dashboard: { type: "market_update", prices: { SYMBOL: { ltp: ... } } }
            # Note: Dashboard expects 'chg', but we might only have 'ltp' or 'ohlc'.
            # We will send what we have. API usually gives 'ltp'. 
            # If we want change, we need close.
            
            # Extract OHLC: On weekends/outside market hours, Upstox nests daily High/Low in 'ohlc_day'.
            # During market hours, it may be in 'ohlc' or at the top level. We check all for safety.
            dashboard_msg = {
                "type": "market_update",
                "prices": {
                    symbol: {
                        "ltp": message.get('ltp') or message.get('last_price'),
                        "high": message.get('ohlc_day', {}).get('high') or message.get('ohlc', {}).get('high') or message.get('high'),
                        "low": message.get('ohlc_day', {}).get('low') or message.get('ohlc', {}).get('low') or message.get('low'),
                        "chg": 0.0 # Placeholder, calculating change requires yesterday's close
                    }
                }
            }
            
            # Align calculation with Indices Dashboard logic:
            # Prioritize 'cp' (Yesterday Close) from feed, fallback to pre-fetched close
            close = message.get('cp') or float(redis_wrapper.hget_json("PREV_CLOSES", symbol) or 0.0)
            
            if close > 0:
                ltp = dashboard_msg['prices'][symbol]['ltp']
                if ltp:
                    dashboard_msg['prices'][symbol]['chg'] = round(((ltp - close) / close) * 100, 2)
                
            to_remove_mw = []
            for connection in self.market_watch_sockets:
                try:
                    await connection.send_json(dashboard_msg)
                except:
                    to_remove_mw.append(connection)
            
            for conn in to_remove_mw:
                if conn in self.market_watch_sockets:
                    self.market_watch_sockets.remove(conn)

manager = ConnectionManager()
loop = None # Global event loop reference

# --- Per-User Streamer Registry ---
# Replaces the single shared global streamer with one UpstoxStreamer per logged-in user.
# This ensures each user only consumes their own Upstox data entitlement (NSE compliance).
class StreamerRegistry:
    """Thread-safe registry mapping user_id -> (UpstoxStreamer, session_count)."""
    def __init__(self):
        self._lock = asyncio.Lock()
        self._streamers: Dict[int, UpstoxStreamer] = {}  # user_id -> streamer
        self._refcounts: Dict[int, int] = {}             # user_id -> active WS session count

    async def acquire(self, user_id: int, token: str) -> UpstoxStreamer:
        """Get or create the streamer for this user. Increments the session reference count."""
        async with self._lock:
            if user_id not in self._streamers:
                logger.info(f"[UPSTOX] [Registry] Creating new streamer for user_id={user_id}")
                s = UpstoxStreamer(token)
                # Reset any previous auth-failure state so this clean token gets a fresh start
                s._terminating = False
                s._reconnect_count = 0
                s.connect_market_data(
                    instrument_keys=list(SYMBOL_MAP.values()),
                    mode="ltpc",
                    on_message=lambda data: asyncio.run_coroutine_threadsafe(manager.broadcast(data), loop) if loop else None
                )
                self._streamers[user_id] = s
                self._refcounts[user_id] = 0
            else:
                # Existing streamer (e.g. user opened a second tab).
                # If it stopped due to auth failure, reset and try reconnecting with the fresh token.
                s = self._streamers[user_id]
                if getattr(s, '_terminating', False):
                    logger.info(f"[UPSTOX] [Registry] Reconnecting dead streamer with fresh token for user_id={user_id}")
                    s._terminating = False
                    s._reconnect_count = 0
                    s.access_token = token
                    s.configuration.access_token = token
                    s.connect_market_data(
                        instrument_keys=list(SYMBOL_MAP.values()),
                        mode="ltpc",
                        on_message=lambda data: asyncio.run_coroutine_threadsafe(manager.broadcast(data), loop) if loop else None
                    )
            self._refcounts[user_id] += 1
            logger.info(f"[UPSTOX] [Registry] user_id={user_id} sessions={self._refcounts[user_id]}")
            return self._streamers[user_id]


    async def release(self, user_id: int):
        """Decrement session count. Disconnect and remove streamer when last session closes."""
        async with self._lock:
            if user_id not in self._refcounts:
                return
            self._refcounts[user_id] -= 1
            logger.info(f"[UPSTOX] [Registry] user_id={user_id} sessions={self._refcounts[user_id]}")
            if self._refcounts[user_id] <= 0:
                # Use a grace period before tearing down — a page navigation rapidly
                # disconnects and reconnects, so we wait 10s to see if a new session arrives.
                logger.info(f"[UPSTOX] [Registry] Sessions=0 for user_id={user_id}. Will teardown in 10s if no reconnect.")
                asyncio.create_task(self._delayed_teardown(user_id))

    async def _delayed_teardown(self, user_id: int):
        """Tear down the streamer only if still at 0 sessions after a grace period."""
        await asyncio.sleep(10)
        async with self._lock:
            count = self._refcounts.get(user_id, 0)
            if count > 0:
                logger.info(f"[UPSTOX] [Registry] Grace period: user_id={user_id} reconnected (sessions={count}). Skipping teardown.")
                return
            s = self._streamers.pop(user_id, None)
            self._refcounts.pop(user_id, None)
            if s:
                logger.info(f"[UPSTOX] [Registry] No more sessions for user_id={user_id}. Closing streamer.")
                try:
                    s.disconnect_all()
                except Exception as e:
                    logger.warning(f"[UPSTOX] [Registry] Error closing streamer for user_id={user_id}: {e}")

    def get_any(self) -> Optional[UpstoxStreamer]:
        """Return any active streamer (used for background LTP lookups)."""
        return next(iter(self._streamers.values()), None)

    def shutdown_all(self):
        """Disconnect all streamers on server shutdown."""
        for uid, s in list(self._streamers.items()):
            try:
                s.disconnect_all()
            except Exception:
                pass
        self._streamers.clear()
        self._refcounts.clear()

streamer_registry = StreamerRegistry()

# --- WebSocket Authentication Helper ---

async def authenticate_websocket(websocket: WebSocket, token: str = None) -> Optional[object]:
    """
    Fix #4: Centralized WebSocket authentication.
    Validates the JWT from an initial auth message sent over the WS connection.
    Falls back to URL query param (deprecated — tokens in URLs appear in server logs).
    Closes with code 1008 (Policy Violation) if auth fails.

    Usage:
      1. Client connects to ws://host/ws/straddle
      2. Client immediately sends: {"action": "auth", "token": "<jwt>"}
      3. Server validates and stores current_user on the connection
    """
    from web_apps.oi_pro.auth import verify_jwt, get_user as _get_user

    try:
        if token:
            # Legacy: token in URL query param (deprecated — kept for backward compat)
            logger.warning(
                "[CORE] [WS] Received token via URL query param (deprecated). "
                "Send {action: 'auth', token: '...'} as first WS message instead."
            )
            email = verify_jwt(token)
            user = _get_user(email)
            if not user or not user.is_active:
                await websocket.close(code=1008)
                return None
            return user

        # Secure path: wait up to 5s for an auth message
        try:
            auth_raw = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
            auth_msg = json.loads(auth_raw)
        except (asyncio.TimeoutError, json.JSONDecodeError):
            logger.warning("[CORE] [WS] Auth timeout or invalid JSON — closing connection")
            await websocket.close(code=1008)
            return None

        if auth_msg.get("action") != "auth" or not auth_msg.get("token"):
            logger.warning("[CORE] [WS] First message must be {action:'auth', token:'...'}")
            await websocket.close(code=1008)
            return None

        email = verify_jwt(auth_msg["token"])
        user = _get_user(email)
        if not user or not user.is_active:
            await websocket.close(code=1008)
            return None
        return user

    except Exception as e:
        logger.warning(f"[CORE] [WS] Auth failed: {e}")
        await websocket.close(code=1008)
        return None

# --- WebSocket Endpoints ---

@app.websocket("/ws/straddle")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(None)):
    """
    Consolidated WebSocket endpoint for real-time Straddle updates.
    Each user gets their own dedicated Upstox streamer (NSE compliant).
    Fix #4: Auth via initial {action:'auth', token:'...'} message, not URL param.
    """
    await manager.connect(websocket)
    current_user = await authenticate_websocket(websocket, token)
    if current_user is None:
        return
    logger.info(f"[CORE] [WS] New Straddle WS Connection (user: {current_user.email})")
    user_token = await get_access_token(current_user)
    if not user_token:
        await websocket.send_json({"type": "error", "message": "No valid Upstox token. Please reconnect Upstox broker."})
        await websocket.close(code=1008)
        return
    user_streamer = await streamer_registry.acquire(current_user.id, user_token)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("action") == "subscribe" and msg.get("keys"):
                    keys = [k.replace(':', '|') for k in msg.get("keys", [])]
                    mode = msg.get("mode", "ltpc")  # 'full' provides OI, Greeks, OHLC per tick
                    await manager.subscribe(websocket, keys, user_streamer=user_streamer, mode=mode)
            except json.JSONDecodeError:
                logger.warning(f"[CORE] [WS] Invalid JSON received: {data}")
    except WebSocketDisconnect:
        logger.info("[CORE] [WS] Straddle WS Disconnected")
        manager.disconnect(websocket)
    finally:
        await streamer_registry.release(current_user.id)

@app.websocket("/ws/cumulative-prices")
async def websocket_cumulative_prices(websocket: WebSocket, token: str = Query(None)):
    """
    WebSocket endpoint for cumulative option prices.
    Each user gets their own dedicated Upstox streamer (NSE compliant).
    Fix #4: Auth via initial {action:'auth', token:'...'} message, not URL param.
    """
    await manager.connect(websocket)
    current_user = await authenticate_websocket(websocket, token)
    if current_user is None:
        return
    logger.info(f"[CORE] [WS] [CumulativePrices] New connection (user: {current_user.email})")
    user_token = await get_access_token(current_user)
    if not user_token:
        await websocket.send_json({"type": "error", "message": "No valid Upstox token. Please reconnect Upstox broker."})
        await websocket.close(code=1008)
        return
    user_streamer = await streamer_registry.acquire(current_user.id, user_token)

    ce_keys = []
    pe_keys = []
    index_key = None
    symbol = "NIFTY"
    ce_open = None
    pe_open = None

    try:
        while True:
            try:
                try:
                    data = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                    msg = json.loads(data)
                    if msg.get("action") == "subscribe":
                        symbol = msg.get("symbol", "NIFTY").upper()
                        expiry = msg.get("expiry")
                        if symbol and expiry:
                            logger.info(f"[UPSTOX] [WS] [CumulativePrices] Subscribing {symbol} {expiry}...")
                            await websocket.send_json({"type": "status", "status": "loading", "symbol": symbol})

                            user_token = await get_access_token(current_user)
                            index_key = SYMBOL_MAP.get(symbol)
                            if not index_key:
                                await websocket.send_json({"type": "error", "message": f"Unknown symbol: {symbol}"})
                                continue

                            df = await run_in_threadpool(get_option_chain_dataframe, user_token, index_key, expiry)
                            if df is not None and not df.empty:
                                ce_keys = [k for k in df['ce_key'].tolist() if k and isinstance(k, str)]
                                pe_keys = [k for k in df['pe_key'].tolist() if k and isinstance(k, str)]

                                all_option_keys = ce_keys + pe_keys
                                if user_streamer and all_option_keys:
                                    try:
                                        user_streamer.subscribe_market_data(all_option_keys, mode="ltpc")
                                    except Exception as sub_err:
                                        logger.error(f"[UPSTOX] [WS] [CumulativePrices] Subscription error: {sub_err}")

                                if user_streamer and index_key:
                                    try:
                                        user_streamer.subscribe_market_data([index_key], mode="ltpc")
                                    except Exception as idx_err:
                                        logger.error(f"[UPSTOX] [WS] [CumulativePrices] Index key subscription error: {idx_err}")

                                logger.info(f"[CORE] [WS] [CumulativePrices] {len(ce_keys)} CE + {len(pe_keys)} PE keys for {symbol}")
                                ce_open = None
                                pe_open = None
                                await websocket.send_json({
                                    "type": "status",
                                    "status": "ready",
                                    "symbol": symbol,
                                    "ce_count": len(ce_keys),
                                    "pe_count": len(pe_keys)
                                })
                            else:
                                await websocket.send_json({"type": "error", "message": "Could not fetch option chain."})
                except asyncio.TimeoutError:
                    pass

                if (ce_keys or pe_keys) and user_streamer:
                    ce_sum = 0.0
                    pe_sum = 0.0
                    ce_valid = 0
                    pe_valid = 0
                    spot = 0.0

                    for k in ce_keys:
                        f = user_streamer.get_latest_data(k)
                        if f:
                            ltp = f.get('ltp') or f.get('last_price') or 0
                            if ltp > 0:
                                ce_sum += ltp
                                ce_valid += 1

                    for k in pe_keys:
                        f = user_streamer.get_latest_data(k)
                        if f:
                            ltp = f.get('ltp') or f.get('last_price') or 0
                            if ltp > 0:
                                pe_sum += ltp
                                pe_valid += 1

                    if index_key:
                        idx_f = user_streamer.get_latest_data(index_key)
                        if idx_f:
                            spot = idx_f.get('ltp') or idx_f.get('last_price') or 0

                    diff = round(ce_sum - pe_sum, 2)
                    SENTIMENT_THRESHOLDS = {"NIFTY": 50, "BANKNIFTY": 150, "SENSEX": 200}
                    threshold = SENTIMENT_THRESHOLDS.get(symbol, 50)
                    if diff > threshold:
                        sentiment = "Bearish"
                    elif diff < -threshold:
                        sentiment = "Bullish"
                    else:
                        sentiment = "Neutral"

                    if ce_sum > 0 and ce_open is None:
                        ce_open = ce_sum
                    if pe_sum > 0 and pe_open is None:
                        pe_open = pe_sum

                    ce_chg = round(((ce_sum - ce_open) / ce_open) * 100, 3) if ce_open else 0.0
                    pe_chg = round(((pe_sum - pe_open) / pe_open) * 100, 3) if pe_open else 0.0
                    avg_ce = round(ce_sum / ce_valid, 2) if ce_valid > 0 else 0.0
                    avg_pe = round(pe_sum / pe_valid, 2) if pe_valid > 0 else 0.0

                    await websocket.send_json({
                        "type": "cumulative_update",
                        "ce_sum": round(ce_sum, 2),
                        "pe_sum": round(pe_sum, 2),
                        "ce_chg": ce_chg,
                        "pe_chg": pe_chg,
                        "avg_ce": avg_ce,
                        "avg_pe": avg_pe,
                        "diff": diff,
                        "spot": round(spot, 2),
                        "ce_count": ce_valid,
                        "pe_count": pe_valid,
                        "sentiment": sentiment,
                        "timestamp": datetime.now().strftime("%H:%M:%S")
                    })

            except WebSocketDisconnect:
                break
            except HTTPException as he:
                raise he
            except Exception as e:
                logger.error(f"[CORE] [WS] [CumulativePrices] Loop Error: {e}")
                import traceback; traceback.print_exc()
                await asyncio.sleep(1)
    finally:
        manager.disconnect(websocket)
        await streamer_registry.release(current_user.id)
        logger.info("[CORE] [WS] [CumulativePrices] Disconnected")

async def prefetch_prev_closes(token: str = None):
    """
    Pre-fetches previous day closes for all indices and caches them in Redis.
    Can be called at startup (token=None) or lazily (token provided).
    """
    if not token:
        token = await get_access_token()
        if not token:
            logger.warning("[UPSTOX] [WS] No access token available for startup prefetch. Skipping.")
            return

    logger.info("[UPSTOX] [WS] Pre-fetching previous closes for indices...")
    for sym, key in SYMBOL_MAP.items():
        try:
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
            hist_df = await run_in_threadpool(fetch_historical_data, token, key, "day", 1, start_date, end_date)
            if not hist_df.empty:
                last_row = hist_df.iloc[-1]
                last_date = last_row['timestamp'].date()
                today_date = datetime.now().date()
                if last_date == today_date and len(hist_df) > 1:
                    prev_close = hist_df.iloc[-2]['close']
                else:
                    prev_close = last_row['close']
                if prev_close > 0:
                    redis_wrapper.hset_json("PREV_CLOSES", sym, prev_close)
                    logger.info(f"[UPSTOX] [WS]    {sym}: Prev Close = {prev_close}")
            else:
                logger.warning(f"[UPSTOX] [WS]    {sym}: No historical data found")
        except Exception as e:
            logger.error(f"[UPSTOX] [WS]    {sym}: Failed to fetch history: {e}")

async def prefetch_option_master():
    """Fetches option chains for all indices to populate symbol_lookup in Redis."""  
    logger.info("[CORE] [Dashboard] Prefetching Option Master for LTP Lookup...")
    try:
        token = await get_access_token()
        if not token:
            logger.warning("[CORE] [Dashboard] [Warning] No access token available for prefetch_option_master. Skipping.")
            return
        
        for symbol, index_key in SYMBOL_MAP.items():
            try:
                # 1. Get Expiries
                expiries = await run_in_threadpool(get_expiries, token, index_key)
                if not expiries:
                    continue
                
                # Fetch only current and next expiry to save time/memory
                target_expiries = expiries[:2] 
                
                count = 0
                for expiry in target_expiries:
                    df = await run_in_threadpool(get_option_chain_dataframe, token, index_key, expiry)
                    if df is not None and not df.empty:
                        for _, row in df.iterrows():
                            strike = row.get('strike_price')
                            ce_k = row.get('ce_key')
                            pe_k = row.get('pe_key')
                            
                            if strike:
                                if ce_k:
                                    redis_wrapper.set_raw(f"symbol_lookup:CE {int(strike)}", ce_k)
                                    count += 1
                                if pe_k:
                                    redis_wrapper.set_raw(f"symbol_lookup:PE {int(strike)}", pe_k)
                                    count += 1

                logger.info(f"[CORE] [Dashboard]   Mapped {count} options for {symbol}")
            except HTTPException as he:
                raise he
            except Exception as e:
                logger.error(f"[CORE] [Dashboard]    Failed to prefetch {symbol}: {e}")
                
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"[CORE] [Dashboard] Prefetch failed: {e}")

async def load_todays_data():
    """
    Skipping memory cache load. Data is persisted to CSV and Redis by the poller.
    """
    pass

async def fetch_baseline_oi():
    """
    Fetches the previous session's OI and close prices ONCE at startup.
    Stores into BASELINE_OI  a static dict keyed by (symbol, expiry, strike).
    
    This feeds /api/delta-heatmap so all OI Change % shown on the heatmap
    are always relative to the previous session's closing OI regardless of
    when the server was started or restarted during the trading day.
    """
    logger.info("[CORE] [Baseline OI] Fetching previous session OI...")
    try:
        token = await get_access_token()
        if not token:
            logger.warning("[CORE] [Baseline OI] [Warning] No access token available for fetch_baseline_oi. Skipping.")
            return
        for symbol in SYMBOL_MAP.keys():
            index_key = SYMBOL_MAP.get(symbol)
            if not index_key:
                continue

            expiries = await run_in_threadpool(get_expiries, token, index_key)
            if not expiries:
                continue
            expiry = str(expiries[0])

            df = await run_in_threadpool(get_option_chain_dataframe, token, index_key, expiry)
            if df is None or df.empty:
                continue

            count = 0
            for _, row in df.iterrows():
                strike = float(row.get('strike_price', 0))
                key = f"{symbol.upper()}:{expiry}:{strike}"
                baseline_data = {
                    "ce_prev_oi": float(row.get('ce_prev_oi', 0) or 0),
                    "pe_prev_oi": float(row.get('pe_prev_oi', 0) or 0),
                    "ce_close":   float(row.get('ce_close', 0) or 0),
                    "pe_close":   float(row.get('pe_close', 0) or 0),
                }
                redis_wrapper.hset_json("BASELINE_OI", key, baseline_data)
                count += 1

            logger.info(f"[CORE] [Baseline OI] {symbol} {expiry}: Stored {count} strikes")

        logger.info("[CORE] [Baseline OI] Done.")
    except HTTPException as he:
        raise he
    except Exception as e:
        import traceback; traceback.print_exc()
        logger.error(f"[CORE] [Baseline OI] Failed: {e}")

async def unified_background_poller():
    """
    Unified background task: 
    1. Polls all indices for GEX/Greeks history.
    2. Polls NIFTY specifically for the Delta Heatmap.
    3. Handles daily cache rollover.
    This consolidation reduces concurrent tasks and simplifies logging.
    """
    logger.info("[CORE] Unified Background Poller started (1-min interval)")
    global LAST_CACHE_RESET_DATE
    from lib.utils.greeks_helper import LOT_SIZE_MAP
    
    cycle_count = 0
    is_baseline_fetched = False
    is_master_prefetched = False
    
    while True:
        try:
            # --- Daily Cache Reset ---
            today = datetime.now().date()
            if today > LAST_CACHE_RESET_DATE:
                logger.info(f"[CORE] New day detected ({today}). Resetting all caches.")
                keys = redis_wrapper.keys("greeks_chain:*") + redis_wrapper.keys("heatmap:*")
                for k in keys:
                    redis_wrapper.client.delete(k)
                LAST_CACHE_RESET_DATE = today

            token = await get_access_token()
            if not token:
                if cycle_count == 0 or cycle_count % 30 == 0:
                    logger.info("[CORE] [Poller] Waiting for an authorized user to log in...")
                await asyncio.sleep(60)
                continue

            # --- Lazy Initializations (once token available) ---
            if not is_baseline_fetched:
                await fetch_baseline_oi()
                is_baseline_fetched = True

            # Note: Streamers are no longer started globally here.
            # Each user gets a dedicated UpstoxStreamer via StreamerRegistry
            # when they first connect to any /ws/* endpoint.

            if not is_master_prefetched:
                asyncio.create_task(prefetch_option_master())
                is_master_prefetched = True

            cycle_count += 1
            is_nifty_heatmap_updated = False
            
            # --- Symbol Polling Loop ---
            for symbol in SYMBOL_MAP.keys():
                index_key = SYMBOL_MAP.get(symbol)
                if not index_key: continue
                
                # Fetch expiries once per symbol/cycle
                expiries = await run_in_threadpool(get_expiries, token, index_key)
                if not expiries: continue
                expiry = str(expiries[0]) 

                # Fetch Option Chain Dataframe
                df = await run_in_threadpool(get_option_chain_dataframe, token, index_key, expiry)
                if df is None or df.empty: continue

                # 1. Greeks/GEX Processing (for all symbols)
                df_gex = calculate_gex_for_chain(df.copy(), symbol)
                snapshot_df = prepare_snapshot(df_gex)
                
                # Replaced memory dictionary with direct push to Redis via greeks_storage.save_snapshot
                
                # Store to CSV (Thread-pooled to prevent blocking)
                try:
                    await run_in_threadpool(greeks_storage.save_snapshot, symbol, expiry, snapshot_df)
                except Exception as storage_err:
                    logger.error(f"[CORE] [Poller] {symbol} Storage error: {storage_err}")

                # 2. Delta Heatmap Processing (NIFTY Only)
                if symbol == "NIFTY":
                    lot_size = LOT_SIZE_MAP.get("NIFTY", 75)
                    spot_price = float(df['spot_price'].iloc[0]) if 'spot_price' in df.columns else 0.0

                    # Filter to ATM +/- 8 strikes
                    df_heatmap = df.copy()
                    if spot_price > 0 and 'strike_price' in df_heatmap.columns:
                        all_strikes = sorted(df_heatmap['strike_price'].unique())
                        atm = min(all_strikes, key=lambda s: abs(s - spot_price))
                        idx = all_strikes.index(atm)
                        df_heatmap = df_heatmap[df_heatmap['strike_price'].isin(all_strikes[max(0, idx - 8) : idx + 9])]

                    strike_deltas = []
                    for _, row in df_heatmap.iterrows():
                        ce_oi = float(row.get('ce_oi', 0) or 0)
                        pe_oi = float(row.get('pe_oi', 0) or 0)
                        ce_d  = float(row.get('ce_delta', 0) or 0)
                        pe_d  = float(row.get('pe_delta', 0) or 0)
                        net_d = (ce_d * ce_oi * lot_size) + (pe_d * pe_oi * lot_size)
                        strike_deltas.append({
                            "strike":     float(row.get('strike_price', 0)),
                            "net_delta":  round(net_d, 0),
                            "ce_oi":      ce_oi,
                            "pe_oi":      pe_oi,
                            "ce_ltp":     float(row.get('ce_ltp', 0) or 0),
                            "pe_ltp":     float(row.get('pe_ltp', 0) or 0),
                            "ce_prev_oi": float(row.get('ce_prev_oi', 0) or 0),
                            "pe_prev_oi": float(row.get('pe_prev_oi', 0) or 0),
                            "ce_close":   float(row.get('ce_close', 0) or 0),
                            "pe_close":   float(row.get('pe_close', 0) or 0),
                        })

                    heatmap_snap = {
                        "timestamp": datetime.now().strftime("%H:%M"),
                        "spot": spot_price,
                        "strikes": strike_deltas,
                    }

                    hm_cache_key = f"heatmap:NIFTY:{expiry}:{datetime.now().date()}"
                    redis_wrapper.push_json_list(hm_cache_key, heatmap_snap, max_len=400)
                    is_nifty_heatmap_updated = True

                # Small jitter to prevent API burst
                await asyncio.sleep(0.5)

            # --- Quiet Mode Logging (Every 5 cycles) ---
            if cycle_count % 5 == 0:
                logger.info(f"[CORE] Poller Cycle {cycle_count} completed successfully at {datetime.now().strftime('%H:%M:%S')}")
            elif is_nifty_heatmap_updated and cycle_count % 1 == 0:
                 # Even quieter: just a single line if user wants to see movement, else comment out.
                 # Let's keep it very quiet as requested.
                 pass

            await asyncio.sleep(60) 
        except Exception as e:
            import traceback
            logger.error(f"[CORE] Unified Poller Error: {e}")
            logger.error(traceback.format_exc())
            await asyncio.sleep(30)

@app.on_event("startup")
async def startup_event():
    """Consolidated startup sequence: Initialize DB, capture event loop, start background poller."""
    global loop
    loop = asyncio.get_event_loop()
    logger.info("[CORE] Dashboard Server Starting...")

    try:
        init_db()
        logger.info("[AUTH] Database initialized")
    except Exception as e:
        logger.error(f"[AUTH] [Error] Failed to init DB: {e}")

    logger.info("[CORE] Launching Background Poller...")
    asyncio.create_task(unified_background_poller())
    # Kick off prefetch option master lazily once a token becomes available
    asyncio.create_task(prefetch_option_master())
    # Pre-fetch previous closes for indices immediately
    asyncio.create_task(prefetch_prev_closes())
    
    # Start Indian Business News Scheduler (RSS Feeds)
    try:
        start_news_scheduler()
        logger.info("[NEWS] Indian Business News scheduler started")
    except Exception as e:
        logger.error(f"[NEWS] Failed to start news scheduler: {e}")

    logger.info("[CORE] Server standby mode active — streamers will start per-user on first WS connect.")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("[UPSTOX] [WS] Shutting down all user streamers...")
    streamer_registry.shutdown_all()

@app.websocket("/ws/market-watch")
async def websocket_market_watch(websocket: WebSocket, token: str = Query(None)):
    """
    WebSocket endpoint for the dashboard market watch (LTP updates).
    Each user gets their own dedicated Upstox streamer (NSE compliant).
    Fix #4: Auth via initial {action:'auth', token:'...'} message, not URL param.
    """
    await manager.connect_market_watch(websocket)
    current_user = await authenticate_websocket(websocket, token)
    if current_user is None:
        return
    user_token = await get_access_token(current_user)
    if not user_token:
        await websocket.send_json({"type": "error", "message": "No valid Upstox token. Please reconnect Upstox broker."})
        await websocket.close(code=1008)
        return
    user_streamer = await streamer_registry.acquire(current_user.id, user_token)
    # Pre-fetch previous closes the first time a user connects (non-blocking)
    if not redis_wrapper.hget_json("PREV_CLOSES", "NIFTY"):
        asyncio.create_task(prefetch_prev_closes(user_token))
    try:
        # Send latest data immediately if already cached in this user's streamer
        initial_prices = {}
        for symbol, key in SYMBOL_MAP.items():
            data = user_streamer.get_latest_data(key)
            if data:
                ltp = data.get('ltp') or data.get('last_price')
                # Prioritize 'cp' for consistency with Dashboard logic
                close = data.get('cp') or data.get('close') or data.get('ohlc_day', {}).get('close') or data.get('ohlc', {}).get('close')
                high = data.get('high') or data.get('ohlc_day', {}).get('high') or data.get('ohlc', {}).get('high')
                low = data.get('low') or data.get('ohlc_day', {}).get('low') or data.get('ohlc', {}).get('low')
                chg = 0.0
                if ltp and close:
                    chg = round(((ltp - close) / close) * 100, 2)
                if ltp:
                    initial_prices[symbol] = {"ltp": ltp, "chg": chg, "high": high, "low": low}
        if initial_prices:
            await websocket.send_json({"type": "market_update", "prices": initial_prices})

        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        pass
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"[CORE] Market Watch WS Error: {e}")
    finally:
        manager.disconnect(websocket)
        await streamer_registry.release(current_user.id)

@app.get("/stock-dashboard", response_class=HTMLResponse)
async def get_stock_dashboard(request: Request):
    """Serves the Unified HTML for the Nifty 50 Stock Dashboard"""
    try:
        html_path = Path(__file__).parent / "stock_dashboard.html"
        return HTMLResponse(content=html_path.read_text())
    except Exception as e:
        return HTMLResponse(content=f"Error loading dashboard: {e}", status_code=500)

@app.get("/indices-dashboard", response_class=HTMLResponse)
async def get_indices_dashboard(request: Request):
    """Serves the Unified HTML for the Indices Dashboard"""
    try:
        html_path = Path(__file__).parent / "indices_dashboard.html"
        return HTMLResponse(content=html_path.read_text())
    except Exception as e:
        return HTMLResponse(content=f"Error loading dashboard: {e}", status_code=500)

@app.get("/fii-dii", response_class=HTMLResponse)
async def get_fii_dii_page(request: Request):
    """Serves the Unified HTML for the FII/DII Analytics Dashboard"""
    try:
        html_path = Path(__file__).parent / "fii_dii.html"
        return HTMLResponse(content=html_path.read_text())
    except Exception as e:
        return HTMLResponse(content=f"Error loading dashboard: {e}", status_code=500)


@app.get("/api/fii-dii")
async def get_fii_dii_data(current_user: User = Depends(get_current_user)):
    """Reads FII/DII data from CSV and returns as JSON."""
    csv_path = Path("/home/sumit/upstox_kotak/fii_dii_data.csv")
    if not csv_path.exists():
        return {"data": []}
    
    try:
        import pandas as pd
        df = pd.read_csv(csv_path)
        # Ensure numeric columns are actually numeric
        for col in ["FII Net Cr.", "DII Net Cr.", "Nifty"]:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Replace NaN with 0 for JSON safety
        df = df.fillna(0)
        
        # Sort by date descending for the table, but the chart might need ascending
        # We'll return everything and let frontend handle sorting/flipping
        return {"data": df.to_dict(orient="records")}
    except Exception as e:
        logger.error(f"[CORE] Error reading FII/DII CSV: {e}")
        raise HTTPException(status_code=500, detail="Error reading data source")

@app.get("/news-pulse", response_class=HTMLResponse)
async def get_news_pulse_page(request: Request):
    """Serves the News Pulse aggregator page."""
    try:
        html_path = Path(__file__).parent / "news_pulse.html"
        return HTMLResponse(content=html_path.read_text())
    except Exception as e:
        return HTMLResponse(content=f"Error loading News Pulse: {e}", status_code=500)


@app.get("/api/news-pulse")
async def get_news_pulse_data(current_user: User = Depends(get_current_user)):
    """Reads pulse_highlights.csv and returns articles as JSON."""
    import pandas as pd
    csv_path = Path("/home/sumit/upstox_kotak/pulse_highlights.csv")
    if not csv_path.exists():
        return {"articles": [], "total": 0, "error": "CSV not found"}
    try:
        df = pd.read_csv(csv_path)
        df = df.where(pd.notnull(df), None)
        articles = df.to_dict(orient="records")
        return {
            "articles": articles,
            "total": len(articles),
            "last_updated": csv_path.stat().st_mtime
        }
    except Exception as e:
        logger.error(f"[CORE] Error reading pulse CSV: {e}")
        raise HTTPException(status_code=500, detail="Error reading news data")


@app.post("/api/news-pulse/scrape")
async def scrape_news_pulse(current_user: User = Depends(get_current_user)):
    """Triggers a fresh scrape of pulse.zerodha.com."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../pulse"))
    try:
        from web_apps.pulse.scraper import scrape_and_save
        count = await run_in_threadpool(scrape_and_save)
        return {"scraped": count, "status": "ok"}
    except Exception as e:
        logger.error(f"[CORE] Pulse scrape error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/market-watch", response_class=HTMLResponse)
async def get_market_watch(request: Request):
    """Serves the Unified HTML for the Market Watch Dashboard"""
    try:
        html_path = Path(__file__).parent / "market_watch.html"
        return HTMLResponse(content=html_path.read_text())
    except Exception as e:
        return HTMLResponse(content=f"Error loading dashboard: {e}", status_code=500)

@app.get("/market-calendar", response_class=HTMLResponse)
async def get_market_calendar(request: Request):
    """Serves the Unified HTML for the Market Calendar Dashboard"""
    try:
        html_path = Path(__file__).parent / "market_calendar.html"
        return HTMLResponse(content=html_path.read_text())
    except Exception as e:
        return HTMLResponse(content=f"Error loading dashboard: {e}", status_code=500)

@app.get("/api/market-calendar")
async def get_market_calendar_api(current_user: User = Depends(get_current_user)):
    """REST endpoint for fetching Upstox market holidays."""
    try:
        upstox_token = await get_access_token(current_user)
        if not upstox_token:
            return {"status": "error", "message": "No active broker connection"}
            
        from lib.api.market_data import get_market_holidays
        from datetime import datetime
        holidays_data = await run_in_threadpool(get_market_holidays, upstox_token)
        
        formatted_holidays = []
        if holidays_data:
            for h in holidays_data:
                if isinstance(h, dict):
                    h_date = h.get('date', h.get('_date'))
                    desc = h.get('description', h.get('_description', 'Unknown'))
                else:
                    h_date = getattr(h, 'date', getattr(h, '_date', None))
                    desc = getattr(h, 'description', getattr(h, '_description', 'Unknown'))
                    
                date_str = ""
                day_str = ""
                if h_date:
                    if isinstance(h_date, datetime):
                        date_str = h_date.strftime("%Y-%m-%d")
                        day_str = h_date.strftime("%A")
                    else:
                        date_str = str(h_date)
                        try:
                            # Assume ISO format or similar, extract just YYYY-MM-DD
                            dt_part = date_str.split("T")[0] if "T" in date_str else date_str.split(" ")[0]
                            dt = datetime.fromisoformat(dt_part)
                            date_str = dt.strftime("%Y-%m-%d")
                            day_str = dt.strftime("%A")
                        except Exception:
                            day_str = "Unknown"
                            
                formatted_holidays.append({
                    "date": date_str,
                    "day": day_str,
                    "description": str(desc)
                })
        return {"status": "success", "data": formatted_holidays}
    except Exception as e:
        import traceback
        logger.error(f"[UPSTOX] [API] Error fetching market calendar: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/future-intraday", response_class=HTMLResponse)
async def get_future_intraday(request: Request):
    """Serves the Unified HTML for the Future Intraday Buildup"""
    try:
        html_path = Path(__file__).parent / "future_intraday.html"
        return HTMLResponse(content=html_path.read_text())
    except Exception as e:
        return HTMLResponse(content=f"Error loading dashboard: {e}", status_code=500)

@app.get("/api/market-quote")
async def get_market_quote(
    current_user: User = Depends(get_current_user),
    index: str = Query("NIFTY", description="Index to fetch quotes for: NIFTY, BANKNIFTY, or INDICES")
):
    """REST endpoint for Index constituents real-time updates and daily changes.
    Fix #5: Requires JWT authentication via Authorization: Bearer header.
    """
    try:
        upstox_token = await get_access_token(current_user)
        if not upstox_token:
            return {"status": "error", "message": "No active broker connection"}
            
        # Determine Target Dictionary based on query param
        if index.upper() == "BANKNIFTY":
            target_keys = BANKNIFTY_KEYS
        elif index.upper() == "INDICES":
            target_keys = INDICES_KEYS
        else:
            target_keys = NIFTY_50_KEYS
            
        from lib.api.market_data import get_market_quotes
        quotes = await run_in_threadpool(get_market_quotes, upstox_token, list(target_keys.values()))
        
        # Transform the response into our dashboard format
        formatted_data = {}
        for symbol, key in target_keys.items():
            # The SDK often returns the keys as 'NSE_EQ:SYMBOL' or 'NSE_INDEX:SYMBOL'
            quote = quotes.get(f"NSE_EQ:{symbol}")
            if not quote:
                quote = quotes.get(f"NSE_INDEX:{symbol}")
            if not quote:
                # Fallback: search by actual instrument_token
                for q in quotes.values():
                    if q.get('instrument_token') == key:
                        quote = q
                        break
            
            if quote:
                ltp = quote.get('last_price', 0)
                net_change = quote.get('net_change', 0)
                # Calculate the percentage change using (net_change / (ltp - net_change)) * 100
                chg = 0.0
                prev_close = ltp - net_change
                if prev_close > 0:
                    chg = round((net_change / prev_close) * 100, 2)
                    
                formatted_data[symbol] = {
                    "ltp": ltp,
                    "chg": chg,
                    "prev": prev_close
                }
                
        return {"status": "success", "type": "stock_data", "data": formatted_data}
        
    except Exception as e:
        import traceback
        logger.error(f"[UPSTOX] [Dashboard] Error fetching market quote API: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/api/stock-analytics")
async def get_stock_analytics(
    current_user: User = Depends(get_current_user),
    index: str = Query("NIFTY", description="Index: NIFTY or BANKNIFTY")
):
    """
    Classifies each constituent stock into one of 4 OI-based categories using
    FUTURES (NSE_FO) contracts – where OI data is meaningful:
      - Long Buildup:   Price ↑ + OI ↑  (fresh longs)
      - Short Buildup:  Price ↓ + OI ↑  (fresh shorts)
      - Short Covering: Price ↑ + OI ↓  (shorts exiting)
      - Long Unwinding: Price ↓ + OI ↓  (longs exiting)

    Steps:
    1. Download NSE instrument master to resolve stock → futures key
    2. Batch-fetch full market quotes for all futures keys
    3. Use futures net_change (vs prev_close), oi, prev_oi for classification
    """
    try:
        # --- Cache Check ---
        cache_key = f"cache:stock_analytics:{index.upper()}"
        cached_res = redis_wrapper.get_json(cache_key)
        if cached_res:
            return cached_res

        upstox_token = await get_access_token(current_user)
        if not upstox_token:
            return {"status": "error", "message": "No active broker connection"}

        stocks = list(BANKNIFTY_KEYS.keys()) if index.upper() == "BANKNIFTY" else list(NIFTY_50_KEYS.keys())

        from lib.api.market_data import get_market_quotes, download_nse_market_data
        from lib.utils.instrument_utils import get_future_instrument_key

        # Step 1: Download NSE instrument master (needed to resolve futures keys)
        nse_data = await run_in_threadpool(download_nse_market_data)
        if nse_data is None or nse_data.empty:
            return {"status": "error", "message": "Failed to download NSE instrument master"}

        # Step 2: Resolve each stock's nearest futures key
        symbol_to_future_key = {}
        for symbol in stocks:
            fkey = get_future_instrument_key(symbol, nse_data)
            if fkey:
                symbol_to_future_key[symbol] = fkey

        if not symbol_to_future_key:
            return {"status": "error", "message": "No futures keys resolved – market may be closed or data unavailable"}

        # Step 3: Batch-fetch full market quotes for all futures keys
        all_future_keys = list(symbol_to_future_key.values())
        quotes = await run_in_threadpool(get_market_quotes, upstox_token, all_future_keys)

        # Build a reverse map: future_key → quote
        future_key_to_quote = {}
        for key, q in quotes.items():
            token = q.get('instrument_token', '')
            future_key_to_quote[token] = q
            future_key_to_quote[key] = q  # also index by response key

        results = []
        for symbol, fkey in symbol_to_future_key.items():
            quote = future_key_to_quote.get(fkey)
            if not quote:
                for q in quotes.values():
                    if q.get('instrument_token') == fkey:
                        quote = q
                        break
            if not quote:
                continue

            ltp        = quote.get('last_price', 0) or 0
            net_change = quote.get('net_change', 0) or 0
            prev_close = round(ltp - net_change, 2) if ltp else 0
            oi         = quote.get('oi', 0) or 0
            prev_oi    = quote.get('oi_day_low', 0) or 0  

            if oi == 0:
                continue

            if not prev_oi or prev_oi >= oi:
                prev_oi = quote.get('oi_day_high', 0) or 0

            if not prev_oi:
                prev_oi = oi  

            price_up   = net_change > 0
            oi_up      = oi > prev_oi
            oi_chg     = oi - prev_oi
            oi_chg_pct = round((oi_chg / prev_oi * 100), 2) if prev_oi else 0

            if price_up and oi_up:       category = "Long Buildup"
            elif not price_up and oi_up: category = "Short Buildup"
            elif price_up and not oi_up: category = "Short Covering"
            else:                        category = "Long Unwinding"

            results.append({
                "symbol":      symbol,
                "future_key":  fkey,
                "ltp":         round(ltp, 2),
                "prev_close":  prev_close,
                "chg":         round(net_change, 2),
                "chg_pct":     round(net_change / prev_close * 100, 2) if prev_close else 0,
                "oi":          int(oi),
                "prev_oi":     int(prev_oi),
                "oi_chg":      int(oi_chg),
                "oi_chg_pct":  oi_chg_pct,
                "category":    category,
            })

        cats = ["Long Buildup", "Short Buildup", "Short Covering", "Long Unwinding"]
        grouped = {}
        for cat in cats:
            subset = [r for r in results if r["category"] == cat]
            subset.sort(key=lambda x: abs(x["oi_chg_pct"]), reverse=True)
            grouped[cat] = subset

        final_res = {
            "status": "success",
            "data": grouped,
            "total": len(results),
            "resolved": len(symbol_to_future_key),
            "cached": False,
            "ts": datetime.now().strftime("%H:%M:%S")
        }

        # --- Cache Set ---
        # Set cache with 60s expiry
        redis_wrapper.set_json(cache_key, final_res, ex=60)
        
        return final_res

    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f"[CORE] [Stock Analytics] Error: {e}")
        return {"status": "error", "message": str(e)}

    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f"[CORE] [Stock Analytics] Error: {e}")
        return {"status": "error", "message": str(e)}


# Duplicate consolidated (see line 647)
pass

# (CORS middleware moved to the top of the file — after app = FastAPI())
# See "Middleware Block" section above for the definitive CORS config.

async def get_access_token(user: User = None):
    """
    Returns a valid access token. 
    1. If user provided: Prioritizes that user's database token.
    2. If no user: Tries to find ANY active user's token (User-Powered Background Polling).
    3. Fallback: Core .env authentication.
    """
    from web_apps.oi_pro.auth import BrokerCredential
    from lib.core.authentication import validate_token
    from starlette.concurrency import run_in_threadpool

    # --- Case 1: Specific User ---
    if user:
        try:
            broker = BrokerCredential.get(
                (BrokerCredential.user == user) & 
                (BrokerCredential.broker_name == "Upstox") &
                (BrokerCredential.access_token.is_null(False))
            )
            
            if broker.last_token_at and broker.last_token_at.date() == datetime.utcnow().date():
                token = broker.access_token
                is_valid = await run_in_threadpool(validate_token, token)
                if is_valid:
                    return token
                else:
                    logger.warning(f"[CORE] [Auth] Database token for {user.email} is invalid. Clearing.")
                    broker.access_token = None
                    broker.status = "Expired"
                    broker.save()
        except BrokerCredential.DoesNotExist:
            pass

    # --- Case 2: Background Task (User-Powered Polling) ---
    else:
        # Check global cache first
        cached_token = redis_wrapper.get_raw("token:admin")
        if cached_token:
            return cached_token

        try:
            # Look for ANY user token generated today
            today = datetime.utcnow().date()
            active_brokers = BrokerCredential.select().where(
                (BrokerCredential.broker_name == "Upstox") &
                (BrokerCredential.access_token.is_null(False)) &
                (BrokerCredential.last_token_at >= today)
            ).order_by(BrokerCredential.last_token_at.desc())

            for broker in active_brokers:
                token = broker.access_token
                is_valid = await run_in_threadpool(validate_token, token)
                if is_valid:
                    logger.info(f"[CORE] [Auth] [Background] Using token from active user: {broker.user.email}")
                    if token:
                        redis_wrapper.set_raw("token:admin", token, ex=300)
                    return token
                else:
                    logger.warning(f"[CORE] [Auth] [Background] Token for {broker.user.email} invalid. Clearing.")
                    broker.access_token = None
                    broker.status = "Expired"
                    broker.save()
        except Exception as e:
            logger.error(f"[CORE] [Auth] Error in User-Powered Background Polling: {e}")

    # --- Case 3: Fallback to .env ---
    try:
        token = await run_in_threadpool(auth_get_token, auto_refresh=True)
    except Exception as e:
        logger.error(f"[CORE] [Auth] .env Auth fallback failed: {e}")
        token = None
    if not token:
        # If specific user requested, we raise error
        if user:
            raise HTTPException(status_code=500, detail="Failed to retrieve or refresh access token. No active user tokens found and .env is missing or invalid.")
        else:
            # If background task, we just return None and let the poller handle it
            return None
    
    # Cache the .env token as well if we're in background mode
    if token and not user:
        redis_wrapper.set_raw("token:admin", token, ex=300)
        
    return token

def calculate_buildup(price_chg_pct, oi_chg_pct):
    if price_chg_pct > 0 and oi_chg_pct > 0: return "Long Buildup"
    if price_chg_pct < 0 and oi_chg_pct > 0: return "Short Buildup"
    if price_chg_pct > 0 and oi_chg_pct < 0: return "Short Covering"
    if price_chg_pct < 0 and oi_chg_pct < 0: return "Long Unwinding"
    return "Neutral"

@app.get("/login", response_class=HTMLResponse)
async def serve_login():
    """Serves the landing page (which now contains the login modal)."""
    html_path = os.path.join(os.path.dirname(__file__), "landing.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="Landing page not found")
    
    def read_file(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
            
    content = await run_in_threadpool(read_file, html_path)
    return HTMLResponse(content=content, media_type="text/html; charset=utf-8")

@app.get("/login.html", response_class=HTMLResponse)
async def serve_login_html():
    """Serves the actual landing page for login.html requests."""
    return await serve_login()

@app.get("/dashboard", response_class=HTMLResponse)
async def serve_dashboard():
    """Serves the analytical dashboard (index.html)."""
    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="index.html not found")
        
    def read_file(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
            
    content = await run_in_threadpool(read_file, html_path)
    return HTMLResponse(content=content, media_type="text/html; charset=utf-8")

@app.get("/brokers", response_class=HTMLResponse)
async def serve_brokers():
    """Serves the brokers management page (brokers.html)."""
    html_path = os.path.join(os.path.dirname(__file__), "brokers.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="brokers.html not found")
        
    def read_file(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
            
    content = await run_in_threadpool(read_file, html_path)
    return HTMLResponse(content=content, media_type="text/html; charset=utf-8")

@app.get("/users", response_class=HTMLResponse)
async def serve_users():
    """Serves the user management page (users.html)."""
    html_path = os.path.join(os.path.dirname(__file__), "users.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="users.html not found")
        
    def read_file(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
            
    content = await run_in_threadpool(read_file, html_path)
    return HTMLResponse(content=content, media_type="text/html; charset=utf-8")

@app.get("/", response_class=HTMLResponse)
async def serve_landing():
    """Serves the main landing page (landing.html)."""
    html_path = os.path.join(os.path.dirname(__file__), "landing.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="landing.html not found")
        
    def read_file(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
            
    content = await run_in_threadpool(read_file, html_path)
    return HTMLResponse(content=content, media_type="text/html; charset=utf-8")

@app.get("/pop", response_class=HTMLResponse)
async def serve_pop_page():
    """
    Serves the Seller's Probability Edge analytics page.
    """
    html_path = os.path.join(os.path.dirname(__file__), "pop.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="pop.html not found")
        
    def read_file(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
            
    content = await run_in_threadpool(read_file, html_path)
    return HTMLResponse(content=content, media_type="text/html; charset=utf-8")

@app.get("/pcr", response_class=HTMLResponse)
async def serve_pcr_page():
    html_path = os.path.join(os.path.dirname(__file__), "pcr.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="pcr.html not found")
        
    def read_file(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
            
    content = await run_in_threadpool(read_file, html_path)
    return HTMLResponse(content=content, media_type="text/html; charset=utf-8")

@app.get("/multi", response_class=HTMLResponse)
async def serve_multi_chart_page():
    """
    Serves the Multi-Option Chart page.
    Allows users to build custom strategies with multiple legs and view combined premium charts.
    """
    html_path = os.path.join(os.path.dirname(__file__), "multi_chart.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="multi_chart.html not found")
        
    def read_file(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
            
    content = await run_in_threadpool(read_file, html_path)
    return HTMLResponse(content=content, media_type="text/html; charset=utf-8")

@app.get("/straddle", response_class=HTMLResponse)
async def serve_straddle_page():
    """
    Serves the ATM Straddle Analysis dashboard page.
    """
    html_path = os.path.join(os.path.dirname(__file__), "straddle.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="straddle.html not found")
        
    def read_file(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
            
    content = await run_in_threadpool(read_file, html_path)
    return HTMLResponse(content=content, media_type="text/html; charset=utf-8")

@app.get("/cumulative", response_class=HTMLResponse)
async def serve_cumulative_page():
    """
    Serves the Cumulative OI Analysis dashboard page.
    """
    html_path = os.path.join(os.path.dirname(__file__), "cumulative_oi.html")
    if not os.path.exists(html_path):
        # Create it later or error out
        raise HTTPException(status_code=404, detail="cumulative_oi.html not found")
        
    def read_file(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
            
    content = await run_in_threadpool(read_file, html_path)
    return HTMLResponse(content=content, media_type="text/html; charset=utf-8")

@app.get("/strike", response_class=HTMLResponse)
async def serve_strike_page():
    """
    Serves the Strike Analysis page (Total OI & OI Change).
    """
    html_path = os.path.join(os.path.dirname(__file__), "strike.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="strike.html not found")
        
    def read_file(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
            
    content = await run_in_threadpool(read_file, html_path)
    return HTMLResponse(content=content, media_type="text/html; charset=utf-8")

@app.get("/greeks", response_class=HTMLResponse)
async def serve_greeks_page():
    """
    Serves the Greeks Exposure Analysis page.
    """
    html_path = os.path.join(os.path.dirname(__file__), "greeks.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="greeks.html not found")
        
    def read_file(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
            
    content = await run_in_threadpool(read_file, html_path)
    return HTMLResponse(content=content, media_type="text/html; charset=utf-8")

@app.get("/strike-greeks", response_class=HTMLResponse)
async def serve_strike_greeks_page():
    """
    Serves the Strike Greeks Analysis page (Historical plots).
    """
    html_path = os.path.join(os.path.dirname(__file__), "strike_greeks.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="strike_greeks.html not found")
        
    def read_file(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
            
    content = await run_in_threadpool(read_file, html_path)
    return HTMLResponse(content=content, media_type="text/html; charset=utf-8")

from fastapi.responses import Response

@app.get("/sidebar.js")
async def serve_sidebar_js():
    """
    Serves the shared sidebar navigation component (JS).
    All dashboard HTML pages load this to render a consistent nav.
    """
    js_path = os.path.join(os.path.dirname(__file__), "sidebar.js")
    if not os.path.exists(js_path):
        raise HTTPException(status_code=404, detail="sidebar.js not found")

    def read_file(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    content = await run_in_threadpool(read_file, js_path)
    return Response(content=content, media_type="application/javascript")


@app.get("/gex", response_class=HTMLResponse)
async def serve_gex_page():
    """
    Serves the Net GEX Regime Analysis page.
    """
    html_path = os.path.join(os.path.dirname(__file__), "gex.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="gex.html not found")
        
    def read_file(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
            
    content = await run_in_threadpool(read_file, html_path)
    return HTMLResponse(content=content, media_type="text/html; charset=utf-8")

@app.get("/max-pain", response_class=HTMLResponse)
async def serve_max_pain_page():
    """
    Serves the Max Pain & Volatility Smile Analysis page.
    """
    html_path = os.path.join(os.path.dirname(__file__), "max_pain.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="max_pain.html not found")
        
    def read_file(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
            
    content = await run_in_threadpool(read_file, html_path)
    return HTMLResponse(content=content, media_type="text/html; charset=utf-8")

@app.get("/multi-strike", response_class=HTMLResponse)
async def serve_multi_strike_page():
    """
    Serves the consolidated Multi-Strike Analysis page (Price + OI).
    """
    html_path = os.path.join(os.path.dirname(__file__), "multi_strike.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="multi_strike.html not found")
        
    def read_file(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
            
    content = await run_in_threadpool(read_file, html_path)
    return HTMLResponse(content=content, media_type="text/html; charset=utf-8")

@app.get("/multi-strike-oi", response_class=HTMLResponse)
async def serve_multi_strike_oi_page():
    """
    Serves the Multi-Strike Analysis page (Legacy route).
    """
    return await serve_multi_strike_page()

@app.get("/multi-strike-price", response_class=HTMLResponse)
async def serve_multi_strike_price_page():
    """
    Serves the Multi-Strike Analysis page (Legacy route).
    """
    return await serve_multi_strike_page()

@app.get("/cumulative-prices", response_class=HTMLResponse)
async def serve_cumulative_prices_page():
    """Serves the Cumulative Prices dashboard page."""
    html_path = os.path.join(os.path.dirname(__file__), "cumulative_prices.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="cumulative_prices.html not found")
        
    def read_file(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
            
    content = await run_in_threadpool(read_file, html_path)
    return HTMLResponse(content=content, media_type="text/html; charset=utf-8")

@app.get("/market-news", response_class=HTMLResponse)
async def market_news(request: Request):
    try:
        html_path = os.path.join(os.path.dirname(__file__), "market_news.html")
        
        def read_file(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
                
        content = await run_in_threadpool(read_file, html_path)
        return HTMLResponse(content=content, media_type="text/html; charset=utf-8")
    except Exception as e:
        logger.error(f"Error serving market news: {e}")
        return HTMLResponse("Internal Server Error", status_code=500)

@app.get("/strategies", response_class=HTMLResponse)
async def serve_strategies_page():
    """
    Serves the Strategy Command Center page.
    """
    html_path = os.path.join(os.path.dirname(__file__), "strategies.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="strategies.html not found")
        
    def read_file(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
            
    content = await run_in_threadpool(read_file, html_path)
    return HTMLResponse(content=content, media_type="text/html; charset=utf-8")

@app.get("/users", response_class=HTMLResponse)
async def serve_users_page():
    """
    Serves the User Management page.
    """
    html_path = os.path.join(os.path.dirname(__file__), "users.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="users.html not found")
        
    def read_file(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
            
    content = await run_in_threadpool(read_file, html_path)
    return HTMLResponse(content=content, media_type="text/html; charset=utf-8")

@app.get("/option-chain", response_class=HTMLResponse)
async def serve_option_chain_page():
    """
    Serves the Option Chain dashboard page.
    """
    html_path = os.path.join(os.path.dirname(__file__), "option_chain.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="option_chain.html not found")
        
    def read_file(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
            
    content = await run_in_threadpool(read_file, html_path)
    return HTMLResponse(content=content, media_type="text/html; charset=utf-8")

@app.get("/oi-buildup", response_class=HTMLResponse)
async def serve_oi_buildup_page():
    """
    Serves the OI Buildup Visualization page.
    """
    html_path = os.path.join(os.path.dirname(__file__), "oi_buildup.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="oi_buildup.html not found")
        
    def read_file(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
            
    content = await run_in_threadpool(read_file, html_path)
    return HTMLResponse(content=content, media_type="text/html; charset=utf-8")

@app.get("/privacy", response_class=HTMLResponse)
async def serve_privacy_page():
    """
    Serves the Privacy Policy page.
    """
    html_path = os.path.join(os.path.dirname(__file__), "privacy.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="privacy.html not found")
        
    def read_file(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
            
    content = await run_in_threadpool(read_file, html_path)
    return HTMLResponse(content=content, media_type="text/html; charset=utf-8")

@app.get("/privacy.html", response_class=HTMLResponse)
async def serve_privacy_page_html():
    return await serve_privacy_page()

@app.get("/pricing", response_class=HTMLResponse)
async def serve_pricing_page():
    """
    Serves the Pricing page.
    """
    html_path = os.path.join(os.path.dirname(__file__), "pricing.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="pricing.html not found")
        
    def read_file(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
            
    content = await run_in_threadpool(read_file, html_path)
    return HTMLResponse(content=content, media_type="text/html; charset=utf-8")

@app.get("/pricing.html", response_class=HTMLResponse)
async def serve_pricing_page_html():
    return await serve_pricing_page()

@app.get("/features", response_class=HTMLResponse)
async def serve_features_page():
    return await serve_static_page("features.html")

@app.get("/features.html", response_class=HTMLResponse)
async def serve_features_page_html():
    return await serve_features_page()

@app.get("/terms", response_class=HTMLResponse)
async def serve_terms_page():
    """
    Serves the Terms and Conditions page.
    """
    html_path = os.path.join(os.path.dirname(__file__), "terms.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="terms.html not found")
        
    def read_file(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
            
    content = await run_in_threadpool(read_file, html_path)
    return HTMLResponse(content=content, media_type="text/html; charset=utf-8")

@app.get("/terms.html", response_class=HTMLResponse)
async def serve_terms_page_html():
    return await serve_terms_page()

async def serve_static_page(filename):
    """Generic helper to serve HTML files from the current directory."""
    html_path = os.path.join(os.path.dirname(__file__), filename)
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail=f"{filename} not found")
        
    def read_file(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
            
    content = await run_in_threadpool(read_file, html_path)
    return HTMLResponse(content=content, media_type="text/html; charset=utf-8")

@app.get("/brokers", response_class=HTMLResponse)
async def serve_brokers_page():
    return await serve_static_page("brokers.html")

@app.get("/contact", response_class=HTMLResponse)
async def serve_contact_page():
    return await serve_static_page("contact.html")

@app.get("/contact.html", response_class=HTMLResponse)
async def serve_contact_page_html():
    return await serve_contact_page()

@app.get("/heatmap", response_class=HTMLResponse)
async def serve_heatmap_page():
    """
    Serves the Heatmap page.
    """
    html_path = os.path.join(os.path.dirname(__file__), "heatmap.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="heatmap.html not found")
        
    def read_file(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
            
    content = await run_in_threadpool(read_file, html_path)
    return HTMLResponse(content=content, media_type="text/html; charset=utf-8")

@app.get("/heatmap.html", response_class=HTMLResponse)
async def serve_heatmap_page_html():
    return await serve_heatmap_page()

@app.get("/api/greeks-data")
async def get_greeks_data(current_user: User = Depends(get_current_user),
                        symbol: str = Query(..., description="Symbol like NIFTY"), 
                        expiry: str = Query(..., description="Expiry Date")):
    """
    Get Greeks (Delta, Gamma) data per strike.
    Appends new data to a global cache history.
    """
    logger.info(f"[CORE] [Greeks API] Request received for {symbol} expiry {expiry}")
    try:
        instrument_key = SYMBOL_MAP.get(symbol.upper())
        if not instrument_key:
            raise HTTPException(status_code=400, detail="Invalid symbol")
            
        token = await get_access_token(current_user)
        
        # 1. Fetch Option Chain
        logger.info(f"[UPSTOX] [Greeks API] Fetching option chain for {instrument_key}...")
        df = await run_in_threadpool(get_option_chain_dataframe, token, instrument_key, expiry)
        
        if df is None or df.empty:
            return {"status": "error", "data": []}
            
        # Get Spot Price
        spot_price = df['spot_price'].iloc[0] if not df.empty else 0
        
        # Use standardized helper for GEX calculation
        df = calculate_gex_for_chain(df, symbol)
        total_gex = get_net_gex(df)
        total_notional_exposure = get_total_exposure(df)
        flip_point = calculate_flip_point(df)

        # 2. Process & Add to Cache
        snapshot_df = prepare_snapshot(df)
        timestamp = snapshot_df['timestamp'].iloc[0]
        
        # Extract relevant columns
        # ...
        cols_to_keep = ['strike_price', 'spot_price', 
                        'ce_delta', 'pe_delta', 'ce_gamma', 'pe_gamma', 
                        'ce_vega', 'pe_vega', 'ce_theta', 'pe_theta',
                        'ce_gex', 'pe_gex',
                        'ce_oi', 'pe_oi']
        
        # Ensure columns exist (fill 0 if missing)
        for col in cols_to_keep:
            if col not in df.columns:
                df[col] = 0
                
        snapshot_df = df[cols_to_keep].copy()
        snapshot_df['timestamp'] = timestamp
        
        # Update Global Cache
        # Replaced memory dictionary with direct push to Redis via greeks_storage.save_snapshot
        
        # Persistent storage (CSV) (Thread-pooled)
        try:
            await run_in_threadpool(greeks_storage.save_snapshot, symbol, expiry, snapshot_df)
        except Exception as storage_err:
            logger.error(f"[CORE] [Greeks API] Storage error: {storage_err}")
                
        logger.info(f"[CORE] [Greeks API] Storage complete for {symbol}")
        # 3. Prepare Response (Return LATEST snapshot for the chart)
        # Clean NaNs/Infs
        snapshot_df = snapshot_df.replace([float('inf'), float('-inf')], 0).fillna(0)
        
        # Rename 'strike_price' to 'strike' for frontend consistency
        snapshot_df = snapshot_df.rename(columns={'strike_price': 'strike'})
        
        spot = snapshot_df['spot_price'].iloc[0] if not snapshot_df.empty else 0
        
        return {
            "status": "success", 
            "metadata": {
                "symbol": symbol,
                "expiry": expiry,
                "spot": spot,
                "total_gex": total_gex,
                "total_exposure": total_notional_exposure,
                "flip_point": flip_point,
                "timestamp": timestamp.isoformat()
            },
            "data": snapshot_df.to_dict(orient="records")
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/debug-cache")
async def debug_cache(current_user: User = Depends(get_current_user)):
    heatmap_stats = len(redis_wrapper.keys("heatmap:*"))
    history_stats = len(redis_wrapper.keys("greeks_chain:*"))
    return {
        "heatmap_keys": heatmap_stats,
        "history_keys": history_stats
    }

@app.get("/api/gex-history")
async def get_gex_history(symbol: str = "NIFTY", expiry: str = None, current_user: User = Depends(get_current_user)):
    """
    Returns time-series data for Net GEX and Spot Price.
    Used for the Net GEX regime traffic light chart.
    """
    try:
        token = await get_access_token(current_user)
        index_key = SYMBOL_MAP.get(symbol.upper())
        if not expiry:
            expiries = await run_in_threadpool(get_expiries, token, index_key)
            if not expiries: return {"status": "error", "message": "No expiries found"}
            expiry = str(expiries[0])
        else:
            # Normalize: frontend sends '2026-02-24T00:00:00', poller stores '2026-02-24 00:00:00'
            expiry = str(expiry).replace('T', ' ')
            
        redis_key = f"greeks_chain:{symbol.upper()}:{expiry}:{datetime.now().date()}"
        cached_list = redis_wrapper.get_json_list(redis_key)
        
        df_history = None
        if cached_list:
            all_records = []
            for snapshot_records in cached_list:
                all_records.extend(snapshot_records)
            if all_records:
                df_history = pd.DataFrame(all_records)
                # Convert string timestamp back to datetime equivalent if necessary, but we can do it via pandas
                df_history['timestamp'] = pd.to_datetime(df_history['timestamp'])
        
        if df_history is None or df_history.empty:
            return {"status": "success", "data": []}
            
        history = []
        for ts, group in df_history.groupby('timestamp'):
            net_gex = float(group['ce_gex'].sum() + group['pe_gex'].sum())
            spot = float(group['spot_price'].mean())
            history.append({
                "timestamp": ts.strftime('%Y-%m-%d %H:%M:%S'),
                "net_gex": net_gex,
                "spot": spot,
                "total_exposure": get_total_exposure(group),
                "flip_point": calculate_flip_point(group)
            })
            
        history.sort(key=lambda x: x['timestamp'])
        
        return {
            "status": "success",
            "metadata": {"symbol": symbol, "expiry": expiry},
            "data": history
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"[CORE] Error fetching GEX history: {e}")
        return {"status": "error", "message": str(e)}

# Duplicate heatmap handler removed (already defined at line 1701)

@app.get("/api/delta-heatmap")
async def get_delta_heatmap(symbol: str = "NIFTY", expiry: str = None, resolution: int = 1, current_user: User = Depends(get_current_user)):
    """
    Returns the cached Net Delta heatmap snapshots.
    Supports sampling via the 'resolution' parameter (e.g. resolution=3 returns every 3rd snapshot).
    """
    try:
        index_key = SYMBOL_MAP.get(symbol.upper())
        if not index_key:
            raise HTTPException(status_code=400, detail="Invalid symbol")

        token = await get_access_token(current_user)
        if not expiry:
            expiries = await run_in_threadpool(get_expiries, token, index_key)
            if not expiries: return {"status": "error", "message": "No expiries"}
            expiry = str(expiries[0])
        else:
            expiry = str(expiry).replace('T', ' ')

        cache_key = (symbol.upper(), expiry)
        redis_cache_key = f"heatmap:{symbol.upper()}:{expiry}:{datetime.now().date()}"
        intervals = redis_wrapper.get_json_list(redis_cache_key)
        
        if intervals:
            intervals = list(intervals) # Copy for thread-safety during slicing/processing

        # Apply sampling based on resolution
        if resolution > 1:
            # Slicing creates a new list, ensures we don't modify the cache reference
            # intervals[::-resolution][::-1] correctly takes every Nth from the end and keeps chronological order
            intervals = intervals[::-resolution][::-1]

        if not intervals:
            return {"status": "success", "is_demo": True, "message": "First poll in progress. Loading demo...", "timestamps": [], "strikes": []}

        # Pin displayed strikes to CURRENT ATM ± 8 (from the latest snapshot).
        # Using a union of all historical snapshots would grow as spot drifts —
        # keeping a fixed grid around current ATM makes the heatmap much cleaner.
        latest = intervals[-1]
        spot   = latest['spot']
        open_spot  = intervals[0]['spot']
        prev_close = float(redis_wrapper.hget_json("PREV_CLOSES", symbol.upper()) or open_spot)
        day_chg = spot - prev_close
        # Round spot to nearest 50-point interval -> ATM, then show ATM ± 8 strikes.
        # This gives exactly 17 rows no matter where spot was earlier in the day.
        strike_step = 50  # NIFTY strikes are at 50-point intervals
        atm = round(spot / strike_step) * strike_step
        all_strikes = sorted(
            [atm + (i * strike_step) for i in range(-8, 9)],
            reverse=True
        )

        timestamps = [snap['timestamp'] for snap in intervals]
        
        # Build 3D heatmap data matrix [strike][time] -> {ce_data, pe_data}
        # In a UI table, rows are strikes, columns are timestamps
        heatmap_data = [] # List of strikes with timeline data
        
        for strike in all_strikes:
            strike_timeline = []
            
            #  Baseline lookup  fetched once at startup from the live option chain 
            # BASELINE_OI is the single source of truth for day-start (9:15 AM) comparisons.
            # Redis strikes are saved as floats in neo_api format (e.g., 24900.0)
            baseline_key = f"{symbol.upper()}:{expiry}:{float(strike)}"
            baseline = redis_wrapper.hget_json("BASELINE_OI", baseline_key) or {}
            
            valid_ce_prev_oi = baseline.get("ce_prev_oi", 0) or 0
            valid_pe_prev_oi = baseline.get("pe_prev_oi", 0) or 0
            valid_ce_close   = baseline.get("ce_close", 0) or 0
            valid_pe_close   = baseline.get("pe_close", 0) or 0

            
            for snap in intervals:
                match = next((s for s in snap['strikes'] if s['strike'] == strike), None)
                
                if match:
                    # ALWAYS compare against the static baseline for day-start buildup
                    curr_ce_prev_oi = valid_ce_prev_oi
                    curr_pe_prev_oi = valid_pe_prev_oi
                    curr_ce_close   = valid_ce_close
                    curr_pe_close   = valid_pe_close

                    ce_oi_chg_pct = ((match['ce_oi'] - curr_ce_prev_oi) / curr_ce_prev_oi * 100) if curr_ce_prev_oi else 0
                    pe_oi_chg_pct = ((match['pe_oi'] - curr_pe_prev_oi) / curr_pe_prev_oi * 100) if curr_pe_prev_oi else 0
                    
                    # Fallback for historical snapshots (approximate price change via Spot)
                    spot_chg_pct = ((snap['spot'] - prev_close) / prev_close * 100) if prev_close else 0
                    
                    if curr_ce_close and match.get('ce_ltp', 0):
                        ce_price_chg_pct = ((match['ce_ltp'] - curr_ce_close) / curr_ce_close * 100)
                    else:
                        ce_price_chg_pct = spot_chg_pct * 3  # Leverage approx
                        
                    if curr_pe_close and match.get('pe_ltp', 0):
                        pe_price_chg_pct = ((match['pe_ltp'] - curr_pe_close) / curr_pe_close * 100)
                    else:
                        pe_price_chg_pct = -spot_chg_pct * 3 # Inverse for Puts
                    
                    ce_buildup = calculate_buildup(ce_price_chg_pct, ce_oi_chg_pct)
                    pe_buildup = calculate_buildup(pe_price_chg_pct, pe_oi_chg_pct)
                    
                    strike_timeline.append({
                        "ce": {
                            "oi": match['ce_oi'],
                            "prev_oi": curr_ce_prev_oi,
                            "ltp": match.get('ce_ltp', 0),
                            "oi_chg_pct": round(ce_oi_chg_pct, 2),
                            "price_chg_pct": round(ce_price_chg_pct, 2),
                            "buildup": ce_buildup
                        },
                        "pe": {
                            "oi": match['pe_oi'],
                            "prev_oi": curr_pe_prev_oi,
                            "ltp": match.get('pe_ltp', 0),
                            "oi_chg_pct": round(pe_oi_chg_pct, 2),
                            "price_chg_pct": round(pe_price_chg_pct, 2),
                            "buildup": pe_buildup
                        },
                        "net_delta": match['net_delta']
                    })
                else:
                    # Empty filler if missing
                    strike_timeline.append(None)
                    
            heatmap_data.append({
                "strike": strike,
                "timeline": strike_timeline,
                "latest_net_delta": strike_timeline[-1]['net_delta'] if strike_timeline[-1] else 0
            })
            
        # Calculate max intensity for color scaling across ALL time periods for Calls and Puts separately
        max_ce_oi_chg_pct = []
        max_pe_oi_chg_pct = []
        
        for ti in range(len(timestamps)):
            ce_col_vals = [abs(data['timeline'][ti]['ce']['oi_chg_pct']) for data in heatmap_data if data['timeline'][ti]]
            pe_col_vals = [abs(data['timeline'][ti]['pe']['oi_chg_pct']) for data in heatmap_data if data['timeline'][ti]]
            max_ce_oi_chg_pct.append(max(ce_col_vals) if ce_col_vals else 1)
            max_pe_oi_chg_pct.append(max(pe_col_vals) if pe_col_vals else 1)

        return {
            "status": "success",
            "symbol": symbol,
            "expiry": expiry,
            "spot": float(spot),
            "open_spot": float(prev_close), 
            "prev_close": float(prev_close),
            "timestamps": timestamps,
            "data": heatmap_data,
            "max_ce_oi_chg_pct": max_ce_oi_chg_pct,
            "max_pe_oi_chg_pct": max_pe_oi_chg_pct,
            "is_demo": False
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        import traceback
        err_msg = traceback.format_exc()
        logger.error(err_msg)
        return {"status": "error", "message": str(e)}

@app.get("/api/strike-greeks-history")
async def get_strike_greeks_history(symbol: str = Query(..., description="Symbol like NIFTY"), 
                                   expiry: str = Query(..., description="Expiry Date"),
                                   strike: float = Query(..., description="Strike Price")):
    """
    Returns time-series data for a specific strike's Greeks from persistent storage.
    """
    try:
        # Normalize expiry string (if coming from frontend with T)
        expiry = str(expiry).replace('T', ' ')
        
        # Load from CSV storage
        df = greeks_storage.get_strike_history(symbol, expiry, strike)
        
        if df.empty:
            return {"status": "success", "data": []}
            
        # Select and format columns for frontend
        df = df.replace([float('inf'), float('-inf')], 0).fillna(0)
        
        # Convert timestamp to string if it's not already
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')
            
        data = df.to_dict(orient="records")
        return {
            "status": "success",
            "metadata": {"symbol": symbol, "expiry": expiry, "strike": strike},
            "data": data
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"[CORE] Error fetching strike greeks history: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/api/pcr-data")
async def get_pcr_data(current_user: User = Depends(get_current_user),
                      symbol: str = Query(..., description="Symbol like NIFTY"), 
                      expiry: str = Query(..., description="Expiry Date")):
    """
    Get data for PCR by Strike Grid.
    Returns list of {strike, pcr, sentiment, ce_oi, pe_oi, call_writer_domination, put_writer_domination}
    """
    logger.info(f"[CORE] [PCR API] Request received for {symbol} expiry {expiry}")
    try:
        instrument_key = SYMBOL_MAP.get(symbol.upper())
        if not instrument_key:
            raise HTTPException(status_code=400, detail="Invalid symbol")
            
        token = await get_access_token(current_user)
        
        logger.info(f"[UPSTOX] [PCR API] Fetching option chain for {instrument_key}...")
        df = await run_in_threadpool(get_option_chain_dataframe, token, instrument_key, expiry)
        
        if df is None or df.empty:
            return {"data": []}
            
        # Extract spot price from underlying_spot_price or spot_price column if available
        # Extraction must happen BEFORE the loop to avoid UnboundLocalError
        spot_price = 0.0
        if 'underlying_spot_price' in df.columns:
            spot_vals = df['underlying_spot_price'].dropna()
            if not spot_vals.empty:
                spot_price = float(spot_vals.iloc[0])
        elif 'spot_price' in df.columns:
             spot_vals = df['spot_price'].dropna()
             if not spot_vals.empty:
                 spot_price = float(spot_vals.iloc[0])
            
        # Process DataFrame for PCR Grid
        grid_data = []
        
        for _, row in df.iterrows():
            strike = row['strike_price']
            ce_oi = row.get('ce_oi') or 0
            pe_oi = row.get('pe_oi') or 0
            
            # Relax filter for strikes near the spot price to ensure ATM is not missed
            is_near_spot = spot_price > 0 and abs(strike - spot_price) <= 200
            if ce_oi < 500 and pe_oi < 500 and not is_near_spot:
                continue
                
            # PCR Calculation
            # Handle division by zero
            if ce_oi == 0:
                pcr = 10.0 if pe_oi > 0 else 0.0 # Cap max PCR
            else:
                pcr = pe_oi / ce_oi
                
            # Sentiment Logic
            # PCR > 1 => More Puts Sold => Bullish (Support)
            # PCR < 1 => More Calls Sold => Bearish (Resistance)
            if pcr >= 1.0:
                sentiment = "BULLISH"
                color = "green"
                desc = "Put Writers Dominating (Support)"
            else:
                sentiment = "BEARISH"
                color = "red"
                desc = "Call Writers Dominating (Resistance)"
                
            grid_data.append({
                "strike": strike,
                "pcr": round(pcr, 2),
                "sentiment": sentiment,
                "color": color,
                "ce_oi": ce_oi,
                "pe_oi": pe_oi,
                "desc": desc
            })
            
        # Sort by Strike
        grid_data.sort(key=lambda x: x['strike'])
        
        logger.info(f"[CORE] [PCR API] Returning {len(grid_data)} rows, spot={spot_price}")
        return {"data": grid_data, "spot_price": spot_price}
        
    except HTTPException as he:
        raise he
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/max-pain-data")
async def get_max_pain_data(symbol: str = Query(..., description="Symbol like NIFTY"), 
                          expiry: str = Query(..., description="Expiry Date"),
                          current_user: User = Depends(get_current_user)):
    """
    Get Max Pain and Volatility Smile data.
    Returns:
    - max_pain_strike: The strike with minimum total pain
    - pain_data: Array of {strike, total_pain, ce_pain, pe_pain}
    - iv_data: Array of {strike, ce_iv, pe_iv}
    - spot_price: Current spot price
    """
    logger.info(f"[CORE] [Max Pain API] Request received for {symbol} expiry {expiry}")
    try:
        instrument_key = SYMBOL_MAP.get(symbol.upper())
        if not instrument_key:
            raise HTTPException(status_code=400, detail="Invalid symbol")
            
        token = await get_access_token(current_user)
        
        logger.info(f"[UPSTOX] [Max Pain API] Fetching option chain for {instrument_key}...")
        df = await run_in_threadpool(get_option_chain_dataframe, token, instrument_key, expiry)
        
        if df is None or df.empty:
            return {"status": "error", "data": {}}
            
        # 1. Calculate Max Pain
        max_pain_result = calculate_max_pain(df)
        
        # 2. Extract IV Data for Volatility Smile
        iv_data = []
        for _, row in df.iterrows():
            strike = row['strike_price']
            ce_iv = row.get('ce_iv') or 0
            pe_iv = row.get('pe_iv') or 0
            
            # Include all strikes; filtering will be done on the frontend to allow more flexibility
            iv_data.append({
                "strike": strike,
                "ce_iv": round(ce_iv, 2) if ce_iv else 0,
                "pe_iv": round(pe_iv, 2) if pe_iv else 0,
                "ce_oi": row.get('ce_oi') or 0,
                "pe_oi": row.get('pe_oi') or 0,
                "ce_volume": row.get('ce_volume') or 0,
                "pe_volume": row.get('pe_volume') or 0
            })
        
        # Sort by strike
        iv_data.sort(key=lambda x: x['strike'])
        
        # Get spot price
        spot_price = df['spot_price'].iloc[0] if not df.empty else 0
        
        logger.info(f"[CORE] [Max Pain API] Max Pain Strike: {max_pain_result['max_pain_strike']}, IV Data Points: {len(iv_data)}")
        
        return {
            "status": "success",
            "data": {
                "max_pain_strike": max_pain_result['max_pain_strike'],
                "pain_data": max_pain_result['pain_data'],
                "iv_data": iv_data,
                "spot_price": spot_price,
                "symbol": symbol,
                "expiry": expiry
            }
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# NOTE: SYMBOL_MAP is defined at the top of the file (line ~29). This duplicate has been removed.

@app.websocket("/ws/price/{symbol}")
async def price_websocket(websocket: WebSocket, symbol: str, token: str = Query(None)):
    current_user = None
    try:
        if token:
            from web_apps.oi_pro.auth import verify_jwt, get_user
            email = verify_jwt(token)
            current_user = get_user(email)
    except:
        await websocket.close(code=1008)
        return
    await manager.connect(websocket)
    user_token = await get_access_token(current_user)
    user_streamer = await streamer_registry.acquire(current_user.id, user_token)
    try:
        while True:
            await asyncio.sleep(0.5)
            key = SYMBOL_MAP.get(symbol.upper())
            if key and user_streamer:
                latest = user_streamer.get_latest_data(key)
                if latest and 'ltp' in latest:
                    await websocket.send_json({"type": "price", "ltp": latest['ltp']})
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        manager.disconnect(websocket)
        await streamer_registry.release(current_user.id)
@app.get("/api/debug/ws-state")
async def debug_ws_state(current_user: User = Depends(get_current_user)):
    """Debug endpoint: shows live WS subscriptions, streamer status, and latest cached feeds."""
    streamer = streamer_registry._streamers.get(current_user.id)
    streamer_info = {}
    if streamer:
        streamer_info = {
            "market_data_connected": streamer.market_data_connected,
            "market_connecting": streamer.market_connecting,
            "terminating": getattr(streamer, '_terminating', False),
            "reconnect_count": getattr(streamer, '_reconnect_count', 0),
            "cached_feed_keys": list(streamer.latest_feeds.keys()),
            "market_callbacks_count": len(streamer.market_callbacks),
        }
    active_subs = {k: len(v) for k, v in manager.subscriptions.items()}
    return {
        "user_id": current_user.id,
        "streamer": streamer_info,
        "active_ws_subscriptions": active_subs,
        "market_watch_sockets": len(manager.market_watch_sockets),
        "global_loop_set": loop is not None,
    }

@app.get("/api/expiries")
async def fetch_expiries(symbol: str = "NIFTY", current_user: User = Depends(get_current_user)):
    token = await get_access_token(current_user)
    key = SYMBOL_MAP.get(symbol.upper())
    if not key:
        raise HTTPException(status_code=400, detail="Invalid symbol")
    
    expiries = await run_in_threadpool(get_expiries, token, key)
    return {"status": "success", "expiries": expiries}

@app.get("/api/option-chain")
async def fetch_option_chain(current_user: User = Depends(get_current_user), 
                             symbol: str = "NIFTY", expiry: str = None, count: int = 6):
    """
    Fetch option chain data and return analytics.
    
    Args:
        symbol: Market symbol (e.g., NIFTY).
        expiry: Expiry date.
        count: Number of strikes to return around ATM (default: 6). 
               Use a higher number (e.g., 50) for full analysis pages.
    """
    token = await get_access_token(current_user)
    key = SYMBOL_MAP.get(symbol.upper())
    if not key:
        raise HTTPException(status_code=400, detail="Invalid symbol")
    
    if not expiry:
        expiries = await run_in_threadpool(get_expiries, token, key)
        if not expiries:
            return {
                "status": "success",
                "metadata": {
                    "symbol": symbol,
                    "expiry": None,
                    "expiries": [],
                    "spot": 0,
                    "pcr": {"oi": 0, "vol": 0, "oi_chg": 0}
                },
                "data": []
            }
        expiry = expiries[0]

    df = await run_in_threadpool(get_option_chain_dataframe, token, key, expiry)
    if df is None or df.empty:
        return {
            "status": "success",
            "metadata": {
                "symbol": symbol,
                "expiry": expiry,
                "expiries": expiries if 'expiries' in locals() else [],
                "spot": 0,
                "pcr": {"oi": 0, "vol": 0, "oi_chg": 0}
            },
            "data": []
        }

    # Add Buildup and Analytics
    df['ce_chg_pct'] = ((df['ce_ltp'] - df['ce_close']) / df['ce_close'] * 100).replace([float('inf'), float('-inf')], 0).fillna(0)
    df['pe_chg_pct'] = ((df['pe_ltp'] - df['pe_close']) / df['pe_close'] * 100).replace([float('inf'), float('-inf')], 0).fillna(0)
    df['ce_oi_pct'] = ((df['ce_oi'] - df['ce_prev_oi']) / df['ce_prev_oi'] * 100).replace([float('inf'), float('-inf')], 0).fillna(0)
    df['pe_oi_pct'] = ((df['pe_oi'] - df['pe_prev_oi']) / df['pe_prev_oi'] * 100).replace([float('inf'), float('-inf')], 0).fillna(0)
    df['ce_oi_chg'] = df['ce_oi'] - df['ce_prev_oi']
    df['pe_oi_chg'] = df['pe_oi'] - df['pe_prev_oi']
    
    # Apply Buildup Logic
    df['ce_buildup'] = df.apply(lambda x: calculate_buildup(x['ce_chg_pct'], x['ce_oi_pct']), axis=1)
    df['pe_buildup'] = df.apply(lambda x: calculate_buildup(x['pe_chg_pct'], x['pe_oi_pct']), axis=1)

    # ATM Strike Filtering (+/- count strikes)
    spot = df['spot_price'].iloc[0] if not df.empty else 0
    if spot > 0:
        # Find ATM strike
        df['strike_diff'] = (df['strike_price'] - spot).abs()
        atm_idx = df['strike_diff'].idxmin()
        
        # Get range of indices
        start_idx = max(0, atm_idx - count)
        end_idx = min(len(df) - 1, atm_idx + count)
        
        # Filter for display but keep full df for PCR
        oi_pcr = calculate_pcr(df)
        vol_pcr = calculate_volume_pcr(df)
        oi_chg_pcr = calculate_oi_change_pcr(df)
        
        df_filtered = df.iloc[start_idx:end_idx+1].copy()
        
        # Clean Inf/NaN
        df_filtered = df_filtered.replace([float('inf'), float('-inf')], 0).fillna(0)
        data = df_filtered.to_dict(orient="records")
        pcr_meta = {
            "oi": float(oi_pcr) if not pd.isna(oi_pcr) else 0,
            "vol": float(vol_pcr) if not pd.isna(vol_pcr) else 0,
            "oi_chg": float(oi_chg_pcr) if not pd.isna(oi_chg_pcr) else 0
        }
    else:
        df = df.replace([float('inf'), float('-inf')], 0).fillna(0)
        data = df.to_dict(orient="records")
        pcr_meta = {
            "oi": float(calculate_pcr(df)),
            "vol": float(calculate_volume_pcr(df)),
            "oi_chg": float(calculate_oi_change_pcr(df))
        }

    # Fetch all expiries for the metadata dropdown
    expiries = await run_in_threadpool(get_expiries, token, key) if key else []

    # Convert to JSON friendly format
    return {
        "status": "success",
        "metadata": {
            "symbol": symbol,
            "expiry": expiry,
            "expiries": expiries,
            "spot": float(spot) if not pd.isna(spot) else 0,
            "pcr": pcr_meta
        },
        "data": df_filtered.replace([float('inf'), float('-inf')], 0).fillna(0).to_dict(orient="records")
    }

@app.get("/api/straddle-data")
async def get_straddle_data(symbol: str = "NIFTY", expiry: str = None, strike: float = None, current_user: User = Depends(get_current_user)):
    """
    Fetches intraday data for ATM or custom straddle legs, calculates combined premium and VWAP,
    and returns KPI metrics for the dashboard.
    
    Args:
        symbol: The underlying symbol (e.g., NIFTY, BANKNIFTY).
        expiry: Target expiry date (optional, defaults to current).
        strike: Custom strike price (optional, defaults to ATM).
        
    Returns:
        JSON containing time-series data for chart and KPI metrics.
    """
    logger.info(f"[CORE] [Straddle API] Request for {symbol} expiry {expiry}")
    try:
        token = await get_access_token(current_user)
        key = SYMBOL_MAP.get(symbol.upper())
        if not key:
            raise HTTPException(status_code=400, detail="Invalid symbol")
            
        if not expiry:
            expiries = get_expiries(token, key)
            if not expiries:
                raise HTTPException(status_code=404, detail="No expiries found")
            expiry = expiries[0]
            
        # 1. Get Option Chain to find current ATM
        df = await run_in_threadpool(get_option_chain_dataframe, token, key, expiry)
        if df is None or df.empty:
            raise HTTPException(status_code=404, detail="No option chain data")
            
        spot = df['spot_price'].iloc[0]
        
        # Determine target strike
        if strike:
            df['strike_diff'] = (df['strike_price'] - strike).abs()
            target_row = df.loc[df['strike_diff'].idxmin()]
            target_strike = target_row['strike_price']
        else:
            df['strike_diff'] = (df['strike_price'] - spot).abs()
            target_row = df.loc[df['strike_diff'].idxmin()]
            target_strike = target_row['strike_price']
            
        ce_key = target_row['ce_key']
        pe_key = target_row['pe_key']
        
        def _to_float(val):
            try:
                if pd.isna(val): return 0.0
                return float(val)
            except:
                return 0.0

        greeks_metadata = {
            "ce_delta": _to_float(target_row.get('ce_delta', 0)),
            "pe_delta": _to_float(target_row.get('pe_delta', 0)),
            "ce_gamma": _to_float(target_row.get('ce_gamma', 0)),
            "pe_gamma": _to_float(target_row.get('pe_gamma', 0)),
            "ce_theta": _to_float(target_row.get('ce_theta', 0)),
            "pe_theta": _to_float(target_row.get('pe_theta', 0)),
            "ce_vega": _to_float(target_row.get('ce_vega', 0)),
            "pe_vega": _to_float(target_row.get('pe_vega', 0)),
            "ce_iv": _to_float(target_row.get('ce_iv', 0)),
            "pe_iv": _to_float(target_row.get('pe_iv', 0))
        }
        
        # Get list of all strikes for the dropdown
        all_strikes = sorted(df['strike_price'].unique().tolist())
        
        logger.info(f"[CORE] [Straddle API] Target Strike: {target_strike} | CE: {ce_key} | PE: {pe_key}")
        
        # 2. Fetch Intraday Data for both legs
        ce_candles = await run_in_threadpool(get_intraday_data_v3, token, ce_key, "minute", 1)
        pe_candles = await run_in_threadpool(get_intraday_data_v3, token, pe_key, "minute", 1)
        
        if not ce_candles or not pe_candles:
            return {
                "status": "success",
                "metadata": {
                    "symbol": symbol,
                    "expiry": expiry,
                    "target_strike": target_strike,
                    "ce_key": ce_key,
                    "pe_key": pe_key,
                    "index_key": key,
                    "all_strikes": all_strikes,
                    "spot": spot,
                    "greeks": greeks_metadata,
                    "kpis": {}
                },
                "data": []
            }
            
        # 3. Merge and Calculate
        ce_df = pd.DataFrame(ce_candles)
        pe_df = pd.DataFrame(pe_candles)
        
        # Merge on timestamp
        merged = pd.merge(ce_df, pe_df, on='timestamp', suffixes=('_ce', '_pe'))
        
        if merged.empty:
            return {
                "status": "success",
                "metadata": {
                    "symbol": symbol,
                    "expiry": expiry,
                    "target_strike": target_strike,
                    "ce_key": ce_key,
                    "pe_key": pe_key,
                    "index_key": key,
                    "all_strikes": all_strikes,
                    "spot": spot,
                    "greeks": greeks_metadata,
                    "kpis": {}
                },
                "data": []
            }
        
        # Combined Premium
        merged['combined_premium'] = merged['close_ce'] + merged['close_pe']
        
        # Calculate Day High/Low for KPIs
        day_high = merged['combined_premium'].max()
        day_low = merged['combined_premium'].min()
        current_val = merged['combined_premium'].iloc[-1]
        open_val = merged['combined_premium'].iloc[0]
        change = current_val - open_val
        change_pct = (change / open_val * 100) if open_val > 0 else 0
        
        # Straddle VWAP calculation (Individual Leg VWAPs summed)
        merged['ce_cum_val'] = (merged['close_ce'] * merged['volume_ce']).cumsum()
        merged['ce_cum_vol'] = merged['volume_ce'].cumsum()
        merged['pe_cum_val'] = (merged['close_pe'] * merged['volume_pe']).cumsum()
        merged['pe_cum_vol'] = merged['volume_pe'].cumsum()
        
        merged['ce_vwap'] = merged.apply(lambda x: x['ce_cum_val'] / x['ce_cum_vol'] if x['ce_cum_vol'] > 0 else x['close_ce'], axis=1)
        merged['pe_vwap'] = merged.apply(lambda x: x['pe_cum_val'] / x['pe_cum_vol'] if x['pe_cum_vol'] > 0 else x['close_pe'], axis=1)
        
        merged['vwap'] = merged['ce_vwap'] + merged['pe_vwap']
        
        # Clean data for JSON
        merged = merged.replace([float('inf'), float('-inf')], 0).fillna(0)
        
        chart_data = merged[['timestamp', 'combined_premium', 'vwap']].to_dict(orient="records")
        
        return {
            "status": "success",
            "metadata": {
                "symbol": symbol,
                "expiry": expiry,
                "target_strike": target_strike,
                "ce_key": ce_key,
                "pe_key": pe_key,
                "index_key": key,
                "all_strikes": all_strikes,
                "spot": spot,
                "greeks": greeks_metadata,
                "kpis": {
                    "current": round(float(current_val), 2),
                    "high": round(float(day_high), 2),
                    "low": round(float(day_low), 2),
                    "change": round(float(change), 2),
                    "change_pct": round(float(change_pct), 2),
                    "open": round(float(open_val), 2),
                    "vwap": round(float(merged['vwap'].iloc[-1]), 2),
                    "ce_ltp": round(float(merged['close_ce'].iloc[-1]), 2),
                    "pe_ltp": round(float(merged['close_pe'].iloc[-1]), 2)
                }
            },
            "data": chart_data
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/strike-data")
async def get_strike_data(symbol: str = "NIFTY", expiry: str = None, strike: float = None, current_user: User = Depends(get_current_user)):
    """
    Fetches intraday data for a specific strike's CE and PE legs.
    Returns: {ce_oi, pe_oi, ce_ltp, pe_ltp} time-series.
    """
    logger.info(f"[CORE] [Strike API] Request for {symbol} {strike} {expiry}")
    try:
        token = await get_access_token(current_user)
        key = SYMBOL_MAP.get(symbol.upper())
        if not key:
            raise HTTPException(status_code=400, detail="Invalid symbol")
            
        if not expiry:
            expiries = get_expiries(token, key)
            if not expiries:
                raise HTTPException(status_code=404, detail="No expiries found")
            expiry = expiries[0]
            
        # 1. Get Option Chain to find specific leg keys
        df = await run_in_threadpool(get_option_chain_dataframe, token, key, expiry)
        if df is None or df.empty:
            raise HTTPException(status_code=404, detail="No option chain data")
            
        spot = df['spot_price'].iloc[0]
        
        # Select target strike
        if strike:
            df['strike_diff'] = (df['strike_price'] - strike).abs()
            target_row = df.loc[df['strike_diff'].idxmin()]
            target_strike = target_row['strike_price']
        else:
            # Default to ATM
            df['strike_diff'] = (df['strike_price'] - spot).abs()
            target_row = df.loc[df['strike_diff'].idxmin()]
            target_strike = target_row['strike_price']
            
        ce_key = target_row['ce_key']
        pe_key = target_row['pe_key']
        
        # 2. Fetch Intraday Data
        ce_candles = await run_in_threadpool(get_intraday_data_v3, token, ce_key, "minute", 1)
        pe_candles = await run_in_threadpool(get_intraday_data_v3, token, pe_key, "minute", 1)
        
        all_strikes = sorted(df['strike_price'].unique().tolist())
        
        if not ce_candles or not pe_candles:
            return {
                "status": "success",
                "metadata": {
                    "symbol": symbol,
                    "target_strike": target_strike,
                    "all_strikes": all_strikes,
                    "spot": spot,
                    "latest": {}
                },
                "data": []
            }
            
        # 3. Merge and formatting
        ce_df = pd.DataFrame(ce_candles).rename(columns={'close': 'ce_ltp', 'oi': 'ce_oi'})[['timestamp', 'ce_ltp', 'ce_oi']]
        pe_df = pd.DataFrame(pe_candles).rename(columns={'close': 'pe_ltp', 'oi': 'pe_oi'})[['timestamp', 'pe_ltp', 'pe_oi']]
        
        merged = pd.merge(ce_df, pe_df, on='timestamp', how='inner')
        if merged.empty:
            return {
                "status": "success",
                "metadata": {
                    "symbol": symbol,
                    "target_strike": target_strike,
                    "all_strikes": all_strikes,
                    "spot": spot,
                    "latest": {}
                },
                "data": []
            }

        merged['timestamp'] = pd.to_datetime(merged['timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # Calculate changes vs Yesterday Close if available in candles (using first candle as proxy for open)
        # But for professional charts, we usually show absolute values or change from 09:15
        
        chart_data = merged.to_dict(orient="records")
        latest = merged.iloc[-1] if not merged.empty else {}
        
        return {
            "status": "success",
            "metadata": {
                "symbol": symbol,
                "expiry": expiry,
                "strike": target_strike,
                "all_strikes": all_strikes,
                "spot": spot,
                "kpis": {
                    "ce_oi": round(float(latest.get('ce_oi', 0)), 0),
                    "pe_oi": round(float(latest.get('pe_oi', 0)), 0),
                    "ce_ltp": round(float(latest.get('ce_ltp', 0)), 2),
                    "pe_ltp": round(float(latest.get('pe_ltp', 0)), 2)
                }
            },
            "data": chart_data
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# Request Model for Multi-Strike History
class LegRequest(BaseModel):
    instrument_key: str
    direction: str  # "BUY" or "SELL"
    lot: int = 1

@app.post("/api/multi-strike-history")
async def get_multi_strike_history(legs: List[LegRequest], current_user: User = Depends(get_current_user)):
    """
    Fetches historical 1-minute data for multiple legs, aligns them on timestamp,
    and calculates the Combined Premium and Running VWAP.
    """
    if not legs:
        return {"status": "success", "data": []}

    token = await get_access_token(current_user)
    
    # 1. Fetch Data for all legs (Throttled)
    _sem = asyncio.Semaphore(3)

    async def fetch_candle(leg):
        async with _sem:
            try:
                # Fetch only last 1 day (current day intraday)
                result = await run_in_threadpool(get_intraday_data_v3, token, leg.instrument_key, "minute", 1)
                await asyncio.sleep(0.1) # Debounce
                return {"leg": leg, "data": result}
            except HTTPException as he:
                raise he
            except Exception as e:
                logger.error(f"[CORE] Error fetching {leg.instrument_key}: {e}")
                return {"leg": leg, "data": None}

    tasks = [fetch_candle(leg) for leg in legs]
    results = await asyncio.gather(*tasks)

    # 2. Process Data — credit-first premium sum (SELL=+1, BUY=-1) + per-leg OI
    price_dfs = []
    vol_dfs = []
    oi_dfs = []   # per-leg OI timeseries
    for res in results:
        data = res['data']
        leg = res['leg']
        if data:
            raw_cols = [c for c in ['timestamp', 'close', 'volume', 'oi'] if c in pd.DataFrame(data).columns]
            df = pd.DataFrame(data)[raw_cols]
            # Convert to IST naive timestamps (strip +05:30 offset)
            df['timestamp'] = pd.to_datetime(df['timestamp'], utc=False)
            if df['timestamp'].dt.tz is not None:
                df['timestamp'] = df['timestamp'].dt.tz_convert('Asia/Kolkata').dt.tz_localize(None)
            col = f'price_{leg.instrument_key}'
            vcol = f'vol_{leg.instrument_key}'
            oicol = f'oi_{leg.instrument_key}'
            # Apply direction and lot multiplier (Credit-first: SELL=+1, BUY=-1)
            mult = 1 if leg.direction == "SELL" else -1
            df[col] = df['close'] * mult * leg.lot
            df[vcol] = df['volume']
            df.set_index('timestamp', inplace=True)
            price_dfs.append(df[[col]])
            vol_dfs.append(df[[vcol]])
            # Track OI per-leg (not direction-adjusted — raw OI)
            if 'oi' in df.columns:
                df[oicol] = df['oi']
                oi_dfs.append(df[[oicol]])

    if not price_dfs:
        return {"status": "error", "message": "No data found for any legs", "data": []}

    # 3. Align and Sum
    price_combined = pd.concat(price_dfs, axis=1, join='outer').sort_index()
    vol_combined = pd.concat(vol_dfs, axis=1, join='outer').sort_index()
    oi_combined = pd.concat(oi_dfs, axis=1, join='outer').sort_index() if oi_dfs else pd.DataFrame(index=price_combined.index)

    # Filter: Today's date + Market hours (09:15 - 15:30) in IST (tz-naive)
    today = datetime.now().strftime('%Y-%m-%d')
    price_combined = price_combined[price_combined.index.strftime('%Y-%m-%d') == today]
    price_combined = price_combined.between_time('09:15', '15:30')
    vol_combined = vol_combined[vol_combined.index.strftime('%Y-%m-%d') == today]
    vol_combined = vol_combined.between_time('09:15', '15:30')
    if not oi_combined.empty:
        oi_combined = oi_combined[oi_combined.index.strftime('%Y-%m-%d') == today]
        oi_combined = oi_combined.between_time('09:15', '15:30')

    if price_combined.empty:
        return {"status": "success", "data": []}

    # Forward fill prices/OI, fill volume NaN with 0
    price_combined = price_combined.ffill().fillna(0)
    vol_combined = vol_combined.fillna(0)
    if not oi_combined.empty:
        oi_combined = oi_combined.ffill().fillna(0)
        oi_combined = oi_combined.reindex(price_combined.index).ffill().fillna(0)

    # Combined Premium = sum of all signed leg prices
    combined_df = pd.DataFrame(index=price_combined.index)
    combined_df['premium'] = price_combined.sum(axis=1)

    # Volume-Weighted VWAP: sum(price * total_volume) / sum(total_volume)
    total_vol = vol_combined.sum(axis=1)
    combined_df['pv'] = combined_df['premium'] * total_vol
    combined_df['cum_pv'] = combined_df['pv'].cumsum()
    combined_df['cum_vol'] = total_vol.cumsum()
    # Avoid division by zero at start; fall back to simple running average
    combined_df['vwap'] = combined_df.apply(
        lambda r: r['cum_pv'] / r['cum_vol'] if r['cum_vol'] > 0 else r['premium'], axis=1
    )

    # Attach per-leg OI columns
    if not oi_combined.empty:
        for oicol in oi_combined.columns:
            combined_df[oicol] = oi_combined[oicol].values

    # Format timestamps as IST strings
    combined_df.reset_index(inplace=True)
    combined_df['timestamp'] = combined_df['timestamp'].dt.strftime('%Y-%m-%dT%H:%M:%S+05:30')

    chart_data = combined_df.to_dict(orient='records')

    # Build leg metadata for frontend (instrument_key, label, direction per leg)
    legs_meta = [
        {"instrument_key": leg.instrument_key, "direction": leg.direction, "lot": leg.lot}
        for leg in legs
    ]

    return {
        "status": "success",
        "legs": legs_meta,
        "data": chart_data
    }

@app.get("/api/cumulative-oi")
async def get_cumulative_oi(symbol: str = "NIFTY", expiry: str = None, strike_range: int = 4, current_user: User = Depends(get_current_user)):
    """
    Fetches intraday data for ATM +/- strike_range strikes, aggregates OI, 
    and returns time-series for cumulative OI charts.
    
    Logic:
    1. Identifies relevant strikes based on current ATM.
    2. Fetches 1-minute intraday snapshots for all Call/Put legs and index LTP.
    3. Aggregates OI across all legs using robust Outer Merge to handle data gaps.
    4. Calculates cumulative change using Yesterday's close (prev_oi) as baseline.
    5. Computes momentum (Direction of Change) and PCR metrics.
    """
    logger.info(f"[CORE] [Cumulative OI] Fetching data for {symbol} expiry {expiry}")
    try:
        token = await get_access_token(current_user)
        key = SYMBOL_MAP.get(symbol.upper())
        if not key:
            raise HTTPException(status_code=400, detail="Invalid symbol")
            
        if not expiry:
            expiries = await run_in_threadpool(get_expiries, token, key)
            if not expiries:
                raise HTTPException(status_code=404, detail="No expiries found")
            expiry = expiries[0]
            
        # 1. Get Option Chain to find current ATM and relevant strikes
        df = await run_in_threadpool(get_option_chain_dataframe, token, key, expiry)
        if df is None or df.empty:
            raise HTTPException(status_code=404, detail="No option chain data")
            
        spot = df['spot_price'].iloc[0]
        step = 100 if symbol == "BANKNIFTY" else 50
        atm = round(spot / step) * step
        
        # Select strikes (ATM +/- strike_range)
        target_strikes = [atm + (i * step) for i in range(-strike_range, strike_range + 1)]
        df_subset = df[df['strike_price'].isin(target_strikes)].copy()
        
        if df_subset.empty:
            raise HTTPException(status_code=404, detail="No strikes found in range")
            
        # 2. Fetch Intraday Data for all legs  throttled to avoid SSL connection flooding
        # Upstox API cannot handle 18+ simultaneous HTTPS connections; limit to 3 concurrent.
        _sem = asyncio.Semaphore(3)

        async def fetch_candle(instr_key):
            async with _sem:
                result = await run_in_threadpool(get_intraday_data_v3, token, instr_key, "minute", 1)
                # Small delay between releases to avoid burst re-triggering
                await asyncio.sleep(0.2)
                return result

        tasks = []
        for _, row in df_subset.iterrows():
            tasks.append(fetch_candle(row['ce_key']))
            tasks.append(fetch_candle(row['pe_key']))
            
        # Also fetch index data for the LTP line
        tasks.append(fetch_candle(key))
        
        results = await asyncio.gather(*tasks)
        
        # 3. Process and Aggregate
        index_candles = results[-1]
        leg_results = results[:-1]
        
        if not index_candles:
            return {
                "status": "success",
                "data": [],
                "metadata": {
                    "symbol": symbol,
                    "expiry": expiry,
                    "spot": spot,
                    "atm": atm,
                    "strikes_used": sorted(target_strikes),
                    "kpis": {}
                }
            }
            
        index_df = pd.DataFrame(index_candles).rename(columns={'close': 'ltp'})[['timestamp', 'ltp']]
        index_df['timestamp'] = pd.to_datetime(index_df['timestamp'])
        
        ce_dfs = []
        pe_dfs = []
        
        # Leg results are in pairs: (CE, PE)
        for i in range(0, len(leg_results), 2):
            ce_candles = leg_results[i]
            pe_candles = leg_results[i+1]
            
            if ce_candles:
                cdf = pd.DataFrame(ce_candles)[['timestamp', 'oi']].rename(columns={'oi': 'ce_oi'})
                cdf['timestamp'] = pd.to_datetime(cdf['timestamp'])
                ce_dfs.append(cdf)

            if pe_candles:
                pdf = pd.DataFrame(pe_candles)[['timestamp', 'oi']].rename(columns={'oi': 'pe_oi'})
                pdf['timestamp'] = pd.to_datetime(pdf['timestamp'])
                pe_dfs.append(pdf)

        # Calculate yesterday's closing OI baseline from the option chain
        # df columns: ce_key, pe_key (or keys like NSE_FO|...), ce_oi, pe_oi, ce_oi_chg, pe_oi_chg
        # Note: the df passed into run_in_threadpool has 'ce_oi' and 'ce_oi_chg'.
        
        # Calculate yesterday's closing OI baseline from the option chain (Prev OI)
        total_yest_ce = df_subset['ce_prev_oi'].sum()
        total_yest_pe = df_subset['pe_prev_oi'].sum()

        # Robust aggregation using pivot to ensure alignment
        # ce_dfs is a list of DataFrames with ['timestamp', 'ce_oi']
        # We want to merge them all on timestamp and handle missing data
        
        # 1. Align CE Data
        if ce_dfs:
            ce_combined = ce_dfs[0]
            for i in range(1, len(ce_dfs)):
                ce_combined = pd.merge(ce_combined, ce_dfs[i], on='timestamp', how='outer', suffixes=(f'_{i-1}', f'_{i}'))
            
            # Sum all ce_oi columns
            oi_cols = [c for c in ce_combined.columns if 'ce_oi' in c]
            ce_combined['ce_oi_total'] = ce_combined[oi_cols].sum(axis=1)
            ce_total_df = ce_combined[['timestamp', 'ce_oi_total']].rename(columns={'ce_oi_total': 'ce_oi'})
        else:
            return {
                "status": "success",
                "data": [],
                "metadata": {
                    "symbol": symbol,
                    "expiry": expiry,
                    "spot": spot,
                    "atm": atm,
                    "strikes_used": sorted(target_strikes),
                    "kpis": {}
                }
            }

        # 2. Align PE Data
        if pe_dfs:
            pe_combined = pe_dfs[0]
            for i in range(1, len(pe_dfs)):
                pe_combined = pd.merge(pe_combined, pe_dfs[i], on='timestamp', how='outer', suffixes=(f'_{i-1}', f'_{i}'))
            
            oi_cols = [c for c in pe_combined.columns if 'pe_oi' in c]
            pe_combined['pe_oi_total'] = pe_combined[oi_cols].sum(axis=1)
            pe_total_df = pe_combined[['timestamp', 'pe_oi_total']].rename(columns={'pe_oi_total': 'pe_oi'})
        else:
            return {
                "status": "success",
                "data": [],
                "metadata": {
                    "symbol": symbol,
                    "expiry": expiry,
                    "spot": spot,
                    "atm": atm,
                    "strikes_used": sorted(target_strikes),
                    "kpis": {}
                }
            }
        
        # Merge all
        merged = pd.merge(ce_total_df, pe_total_df, on='timestamp', how='inner')
        merged = pd.merge(merged, index_df, on='timestamp', how='inner')
        
        # Sort by timestamp to ensure correct calculation of diff and latest
        merged = merged.sort_values('timestamp').reset_index(drop=True)
        
        # Calculate changes vs Yesterday's Close
        merged['ce_chg'] = merged['ce_oi'] - total_yest_ce
        merged['pe_chg'] = merged['pe_oi'] - total_yest_pe
        merged['net_chg'] = merged['pe_chg'] - merged['ce_chg']
        
        # Direction and Momentum (Match Streamlit formulas)
        merged['direction_chg'] = merged['net_chg'].diff().fillna(0)
        merged['direction_chg_pct'] = (merged['direction_chg'] / merged['net_chg'].shift().abs() * 100).replace([float('inf'), float('-inf')], 0).fillna(0)
        merged['direction'] = merged['net_chg'].apply(lambda x: "BUY " if x > 0 else "SELL ")
        
        # PCR
        merged['pcr'] = merged['pe_oi'] / merged['ce_oi']
        
        # Metadata for KPIs (Before string formatting)
        latest = merged.iloc[-1]
        
        # Final formatting
        merged = merged.replace([float('inf'), float('-inf')], 0).fillna(0)
        merged['timestamp'] = merged['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
        
        chart_data = merged[['timestamp', 'ce_oi', 'pe_oi', 'ce_chg', 'pe_chg', 'net_chg', 'direction', 'direction_chg', 'direction_chg_pct', 'ltp', 'pcr']].to_dict(orient="records")
        
        return {
            "status": "success",
            "metadata": {
                "symbol": symbol,
                "expiry": expiry,
                "spot": spot,
                "atm": atm,
                "strikes_used": sorted(target_strikes),
                "kpis": {
                    "net_chg": round(float(latest['net_chg']), 0),
                    "ce_chg": round(float(latest['ce_chg']), 0),
                    "pe_chg": round(float(latest['pe_chg']), 0),
                    "total_ce": round(float(latest['ce_oi']), 0),
                    "total_pe": round(float(latest['pe_oi']), 0),
                    "pcr": round(float(latest['pcr']), 2),
                    "ltp": round(float(latest['ltp']), 2)
                }
            },
            "data": chart_data
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/option-chain/{symbol}")
async def get_full_chain(symbol: str, expiry: str, current_user: User = Depends(get_current_user)):
    """
    Get Complete Option Chain with Build Up & Top OI.
    """
    try:
        token = await get_access_token(current_user)
        underlying_key = SYMBOL_MAP.get(symbol.upper())
        if not underlying_key:
             raise HTTPException(status_code=400, detail="Invalid Symbol")

        # Fetch Data
        df = await run_in_threadpool(get_full_option_chain, token, underlying_key, expiry)
        
        if df.empty:
             return {"chain": [], "spot": 0}

        _spot_raw = df['underlying_spot'].iloc[0] if not df.empty else 0
        spot = float(_spot_raw) if not pd.isna(_spot_raw) else 0

        # --- Top 3 OI Logic ---
        # Sort by OI desc
        top_ce = df[df['type'] == 'call'].nlargest(3, 'oi')['strike_price'].tolist()
        top_pe = df[df['type'] == 'put'].nlargest(3, 'oi')['strike_price'].tolist()
        
        # Add flags to dataframe
        def check_top_oi(row):
            if row['type'] == 'call' and row['strike_price'] in top_ce:
                rank = top_ce.index(row['strike_price']) + 1 # 1, 2, 3
                return rank
            if row['type'] == 'put' and row['strike_price'] in top_pe:
                rank = top_pe.index(row['strike_price']) + 1
                return rank
            return 0

        df['oi_rank'] = df.apply(check_top_oi, axis=1)

        # Convert to list of dicts for JSON
        chain_data = df.replace([float('inf'), float('-inf')], 0).fillna(0).to_dict(orient='records')
        
        # Ensure no NaNs in lists
        top_ce = [float(x) for x in top_ce if not pd.isna(x)]
        top_pe = [float(x) for x in top_pe if not pd.isna(x)]
        
        return {
            "chain": chain_data,
            "spot": spot,
            "top_ce": top_ce,
            "top_pe": top_pe
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/multi-strike-oi-data")
async def get_multi_strike_oi_data(
    current_user: User = Depends(get_current_user),
    symbol: str = Query(..., description="Symbol like NIFTY"),
    expiry: str = Query(..., description="Expiry Date"),
    strikes: str = Query(..., description="Comma-separated strikes")
):
    """
    Fetches intraday OI history for multiple selected strikes (CE and PE).
    """
    logger.info(f"[CORE] [Multi-Strike OI] Request: {symbol} | {expiry} | Strikes: {strikes}")
    try:
        token = await get_access_token(current_user)
        underlying_key = SYMBOL_MAP.get(symbol.upper())
        if not underlying_key:
            logger.warning(f"[CORE] [Multi-Strike OI] Invalid symbol: {symbol}")
            raise HTTPException(status_code=400, detail="Invalid symbol")
            
        strike_list = [float(s.strip()) for s in strikes.split(",") if s.strip()]
        if not strike_list:
            raise HTTPException(status_code=400, detail="No strikes provided")

        # 1. Get Option Chain to find keys for all strikes
        logger.info(f"[UPSTOX] [Multi-Strike OI] Fetching chain for {symbol} {expiry}...")
        df = await run_in_threadpool(get_option_chain_dataframe, token, underlying_key, expiry)
        if df is None or df.empty:
            logger.warning("[UPSTOX] [Multi-Strike OI] No option chain found")
            raise HTTPException(status_code=404, detail="No option chain data")
            
        df_subset = df[df['strike_price'].isin(strike_list)].copy()
        if df_subset.empty:
            logger.warning(f"[UPSTOX] [Multi-Strike OI] Strikes {strike_list} not found in chain")
            raise HTTPException(status_code=404, detail="Selected strikes not found in chain")
            
        # 2. Fetch Intraday data for all selected legs
        _sem = asyncio.Semaphore(5)
        async def fetch_candle(instr_key, strike, type):
            async with _sem:
                logger.info(f"[UPSTOX] [Multi-Strike OI] Fetching {strike} {type} ({instr_key})")
                res = await run_in_threadpool(get_intraday_data_v3, token, instr_key, "minute", 1)
                await asyncio.sleep(0.05)
                return res

        tasks = []
        mapping = [] # List of {strike, type, key}
        for _, row in df_subset.iterrows():
            # CE
            mapping.append({"strike": row['strike_price'], "type": "CE", "key": row['ce_key']})
            tasks.append(fetch_candle(row['ce_key'], row['strike_price'], "CE"))
            # PE
            mapping.append({"strike": row['strike_price'], "type": "PE", "key": row['pe_key']})
            tasks.append(fetch_candle(row['pe_key'], row['strike_price'], "PE"))
            
        results = await asyncio.gather(*tasks)
        logger.info(f"[UPSTOX] [Multi-Strike OI] Gathered {len(results)} legs")
        
        # 3. Process and Align
        all_dfs = []
        for i, candles in enumerate(results):
            m = mapping[i]
            col_name = f"{int(m['strike'])}_{m['type']}"
            
            if not candles: 
                logger.warning(f"[UPSTOX] [Multi-Strike OI] No data for {col_name}")
                continue
            
            df_leg = pd.DataFrame(candles)[['timestamp', 'oi']].rename(columns={'oi': col_name})
            df_leg['timestamp'] = pd.to_datetime(df_leg['timestamp'])
            all_dfs.append(df_leg)
            
        if not all_dfs:
            logger.warning("[UPSTOX] [Multi-Strike OI] All legs returned empty")
            return {"status": "success", "data": [], "metadata": {"strikes": strike_list}}
            
        # Outer merge all dataframes on timestamp
        merged = all_dfs[0]
        for i in range(1, len(all_dfs)):
            merged = pd.merge(merged, all_dfs[i], on='timestamp', how='outer')
            
        # Sort and fill gaps
        merged = merged.sort_values('timestamp').ffill().fillna(0)
        merged['timestamp'] = merged['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
        
        logger.info(f"[UPSTOX] [Multi-Strike OI] Success. Rows: {len(merged)}")
        return {
            "status": "success",
            "metadata": {
                "symbol": symbol,
                "expiry": expiry,
                "strikes": sorted(strike_list),
                "columns": [c for c in merged.columns if c != 'timestamp']
            },
            "data": merged.to_dict(orient="records")
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f"[UPSTOX] [Multi-Strike OI] Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/multi-strike-price-data")
async def get_multi_strike_price_data(
    current_user: User = Depends(get_current_user),
    symbol: str = Query(..., description="Symbol like NIFTY"),
    expiry: str = Query(..., description="Expiry Date"),
    strikes: str = Query(..., description="Comma-separated strikes")
):
    """
    Fetches intraday Price history for multiple selected strikes (CE and PE).
    """
    logger.info(f"[UPSTOX] [Multi-Strike Price] Request: {symbol} | {expiry} | Strikes: {strikes}")
    try:
        token = await get_access_token(current_user)
        underlying_key = SYMBOL_MAP.get(symbol.upper())
        if not underlying_key:
            logger.warning(f"[UPSTOX] [Multi-Strike Price] Invalid symbol: {symbol}")
            raise HTTPException(status_code=400, detail="Invalid symbol")
            
        strike_list = [float(s.strip()) for s in strikes.split(",") if s.strip()]
        if not strike_list:
            raise HTTPException(status_code=400, detail="No strikes provided")

        # 1. Get Option Chain to find keys for all strikes
        logger.info(f"[UPSTOX] [Multi-Strike Price] Fetching chain for {symbol} {expiry}...")
        df = await run_in_threadpool(get_option_chain_dataframe, token, underlying_key, expiry)
        if df is None or df.empty:
            logger.warning("[UPSTOX] [Multi-Strike Price] No option chain found")
            raise HTTPException(status_code=404, detail="No option chain data")
            
        df_subset = df[df['strike_price'].isin(strike_list)].copy()
        if df_subset.empty:
            logger.warning(f"[UPSTOX] [Multi-Strike Price] Strikes {strike_list} not found in chain")
            raise HTTPException(status_code=404, detail="Selected strikes not found in chain")
            
        # 2. Fetch Intraday data for all selected legs
        _sem = asyncio.Semaphore(5)
        async def fetch_candle(instr_key, strike, type):
            async with _sem:
                logger.info(f"[UPSTOX] [Multi-Strike Price] Fetching {strike} {type} ({instr_key})")
                res = await run_in_threadpool(get_intraday_data_v3, token, instr_key, "minute", 1)
                await asyncio.sleep(0.05)
                return res

        tasks = []
        mapping = [] # List of {strike, type, key}
        for _, row in df_subset.iterrows():
            # CE
            mapping.append({"strike": row['strike_price'], "type": "CE", "key": row['ce_key']})
            tasks.append(fetch_candle(row['ce_key'], row['strike_price'], "CE"))
            # PE
            mapping.append({"strike": row['strike_price'], "type": "PE", "key": row['pe_key']})
            tasks.append(fetch_candle(row['pe_key'], row['strike_price'], "PE"))
            
        results = await asyncio.gather(*tasks)
        logger.info(f"[UPSTOX] [Multi-Strike Price] Gathered {len(results)} legs")
        
        # 3. Process and Align
        all_dfs = []
        for i, candles in enumerate(results):
            m = mapping[i]
            col_name = f"{int(m['strike'])}_{m['type']}"
            
            if not candles: 
                logger.warning(f"[UPSTOX] [Multi-Strike Price] No data for {col_name}")
                continue
            
            df_leg = pd.DataFrame(candles)[['timestamp', 'close']].rename(columns={'close': col_name})
            df_leg['timestamp'] = pd.to_datetime(df_leg['timestamp'])
            all_dfs.append(df_leg)
            
        if not all_dfs:
            logger.warning("[UPSTOX] [Multi-Strike Price] All legs returned empty")
            return {"status": "success", "data": [], "metadata": {"strikes": strike_list}}
            
        # Outer merge all dataframes on timestamp
        merged = all_dfs[0]
        for i in range(1, len(all_dfs)):
            merged = pd.merge(merged, all_dfs[i], on='timestamp', how='outer')
            
        # Sort and fill gaps
        merged = merged.sort_values('timestamp').ffill().fillna(0)
        merged['timestamp'] = merged['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
        
        logger.info(f"[UPSTOX] [Multi-Strike Price] Success. Rows: {len(merged)}")
        return {
            "status": "success",
            "metadata": {
                "symbol": symbol,
                "expiry": expiry,
                "strikes": sorted(strike_list),
                "columns": [c for c in merged.columns if c != 'timestamp']
            },
            "data": merged.to_dict(orient="records")
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f"[UPSTOX] [Multi-Strike Price] Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/future-intraday")
async def get_future_intraday_api(
    symbol: str = Query("NIFTY"),
    timeframe: int = Query(3)
):
    """Fetch intraday future buildup data"""
    try:
        from lib.api.historical import get_intraday_data_v3
        from lib.utils.instrument_utils import get_future_instrument_key
        # get_access_token and calculate_buildup are in the global scope of main.py
        
        access_token = await get_access_token()
        if not access_token:
            return {"status": "error", "message": "Access token not found"}
            
        from lib.api.market_data import download_nse_market_data
        nse_data = await run_in_threadpool(download_nse_market_data)
        
        instrument_key = get_future_instrument_key(symbol, nse_data)
        if not instrument_key:
            return {"status": "error", "message": f"Future key not found for {symbol}"}
            
        # Fetch Intraday Data
        candles = await run_in_threadpool(get_intraday_data_v3, access_token, instrument_key, "minute", timeframe)
        if not candles:
            # Fallback to daily data if intraday fails or market hasn't opened?
            return {"status": "error", "message": f"No intraday data found for {symbol} {timeframe}m"}
            
        # Process Buildup
        processed = []
        for i in range(1, len(candles)):
            curr = candles[i]
            prev = candles[i-1]
            
            # Use close-to-close for buildup
            price_chg = curr['close'] - prev['close']
            price_chg_pct = (price_chg / prev['close']) * 100 if prev['close'] != 0 else 0
            oi_chg = curr['oi'] - prev['oi']
            oi_chg_pct = (oi_chg / prev['oi']) * 100 if prev['oi'] != 0 else 0
            
            sentiment = calculate_buildup(price_chg_pct, oi_chg_pct)
            
            processed.append({
                "time": curr['timestamp'], 
                "price": curr['close'],
                "price_chg": round(price_chg, 2),
                "oi": curr['oi'],
                "oi_chg": oi_chg,
                "sentiment": sentiment
            })
            
        # Sort by time descending (latest first)
        processed.sort(key=lambda x: x['time'], reverse=True)
        
        return {
            "status": "success",
            "symbol": symbol,
            "timeframe": timeframe,
            "data": processed
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

@app.get("/future-price-oi", response_class=HTMLResponse)
async def future_price_oi_page():
    try:
        html_path = Path(__file__).parent / "future_price_oi.html"
        return HTMLResponse(content=html_path.read_text())
    except Exception as e:
        return HTMLResponse(content=f"Error loading dashboard: {e}", status_code=500)

@app.get("/api/future-price-oi-history")
async def get_future_price_oi_history(symbol: str = Query("NIFTY")):
    """Fetch 1m intraday historical data for Future Price vs OI chart"""
    try:
        from lib.api.historical import get_intraday_data_v3
        from lib.utils.instrument_utils import get_future_instrument_key
        
        access_token = await get_access_token()
        if not access_token:
            return {"status": "error", "message": "Access token not found"}
            
        from lib.api.market_data import download_nse_market_data
        nse_data = await run_in_threadpool(download_nse_market_data)
        
        instrument_key = get_future_instrument_key(symbol, nse_data)
        if not instrument_key:
            return {"status": "error", "message": f"Future key not found for {symbol}"}
            
        # Fetch Intraday 1-minute Data
        candles = await run_in_threadpool(get_intraday_data_v3, access_token, instrument_key, "minute", 1)
        if not candles:
            return {"status": "error", "message": f"No intraday data found for {symbol}"}
            
        # 2. Get Spot Price for Header
        index_key = SYMBOL_MAP.get(symbol, f"NSE_INDEX|{symbol}")
        spot_price = 0
        try:
            from lib.api.market_data import get_full_market_quote
            quotes = await run_in_threadpool(get_full_market_quote, access_token, [index_key])
            if quotes and index_key in quotes:
                spot_price = quotes[index_key].get('last_price', 0)
        except:
            pass

        processed = []
        for curr in candles:
            processed.append({
                "time": curr['timestamp'], 
                "price": curr['close'],
                "oi": curr['oi']
            })
            
        return {
            "status": "success",
            "symbol": symbol,
            "instrument_key": instrument_key,
            "index_key": index_key,
            "spot_price": spot_price,
            "data": processed
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

@app.websocket("/ws/future-price-oi/{symbol}")
async def future_price_oi_websocket(websocket: WebSocket, symbol: str, token: str = Query(None)):
    current_user = None
    try:
        if token:
            from web_apps.oi_pro.auth import verify_jwt, get_user
            email = verify_jwt(token)
            current_user = get_user(email)
    except:
         await websocket.close(code=1008)
         return
         
    user_token = await get_access_token(current_user)
    user_streamer = await streamer_registry.acquire(current_user.id, user_token)
    await manager.connect(websocket)

    try:
        from lib.utils.instrument_utils import get_future_instrument_key
        from lib.api.market_data import download_nse_market_data
        nse_data = await run_in_threadpool(download_nse_market_data)
        future_key = get_future_instrument_key(symbol, nse_data)
        index_key = SYMBOL_MAP.get(symbol, f"NSE_INDEX|{symbol}")

        if not future_key:
            raise Exception("Future key not found")

        user_streamer.connect_market_data(instrument_keys=[future_key], mode="full")
        user_streamer.subscribe_market_data([future_key], mode="full")
        user_streamer.subscribe_market_data([index_key], mode="ltpc")

        while True:
            await asyncio.sleep(1)
            if user_streamer:
                f_data = user_streamer.get_latest_data(future_key)
                s_data = user_streamer.get_latest_data(index_key)

                if f_data and 'ltp' in f_data and 'oi' in f_data:
                    import time
                    ts = int(time.time() * 1000)
                    await websocket.send_json({
                        "type": "future-price-oi",
                        "time": ts,
                        "price": f_data['ltp'],
                        "spot": s_data.get('ltp', 0) if s_data else 0,
                        "oi": f_data['oi']
                    })
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception as e:
        import traceback
        traceback.print_exc()
    finally:
        manager.disconnect(websocket)
        await streamer_registry.release(current_user.id)

@app.get("/surface-3d", response_class=HTMLResponse)
async def surface_3d_page():
    try:
        html_path = Path("web_apps/oi_pro/surface_3d.html")
        return HTMLResponse(content=html_path.read_text())
    except Exception as e:
        return HTMLResponse(content=f"Error loading surface: {e}", status_code=500)

@app.get("/api/option-chain-3d")
async def api_option_chain_3d(
    symbol: str = "NIFTY", 
    surface_type: str = "both",
    metric: str = "open_interest",
    use_log_scale: bool = False,
    min_oi: int = 100,
    strike_window: float = 20.0,
    min_dte: int = 0,
    max_dte: int = 90,
    theme: str = "dark",
    user_token: str = Depends(get_token)
):
    try:
        # Use the Upstox access token for actual API calls, not the user JWT
        upstox_token = auth_get_token()
        from lib.api.option_chain import get_option_chain, get_expiries
        from lib.utils.plotting import create_option_3d_surface
        import json
        
        index_key = SYMBOL_MAP.get(symbol, f"NSE_INDEX|{symbol}")
        if not upstox_token:
            return {"status": "error", "message": "Upstox access token not found"}
            
        # index_key is already set from SYMBOL_MAP or default f"NSE_INDEX|{symbol}"
        
        # 2. Fetch all expiries
        # get_expiries is no longer imported, assuming it's handled internally by get_option_chain or not needed directly.
        # If get_expiries is still needed, it should be re-imported.
        # For now, I'll assume the logic for fetching expiries is integrated or simplified.
        # Re-adding get_expiries as it was used before to get the list of expiries.
        from lib.api.option_chain import get_expiries

        expiries = await run_in_threadpool(get_expiries, upstox_token, index_key)
        if not expiries:
            return {"status": "error", "message": f"No expiries found for {symbol}"}
            
        # Limit expiries to those within a 90-day window
        from datetime import datetime
        today = datetime.now().date()
        
        target_expiries = []
        for exp in expiries:
            try:
                if isinstance(exp, str):
                    exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
                elif hasattr(exp, 'date'):
                    exp_date = exp.date()
                else:
                    exp_date = exp
                
                if (exp_date - today).days <= 90:
                    target_expiries.append(exp)
            except:
                continue
        
        if not target_expiries:
            target_expiries = expiries[:5] # Fallback to first few if none in 90d window
        
        # 3. Parallelize chain fetching
        async def fetch_one_expiry(exp):
            try:
                # Handle various expiry formats (string, date, datetime)
                if isinstance(exp, str):
                    # Robust parsing for "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS"
                    try:
                        exp_date = datetime.strptime(exp.split(' ')[0], "%Y-%m-%d").date()
                    except:
                        # Fallback for other formats
                        import dateutil.parser
                        exp_date = dateutil.parser.parse(exp).date()
                elif hasattr(exp, 'date'):
                    exp_date = exp.date()
                else:
                    exp_date = exp
                
                exp_str = exp_date.strftime("%Y-%m-%d")
                dte = max(0, (exp_date - today).days)
                
                chain = await run_in_threadpool(get_option_chain, upstox_token, index_key, exp_str)
                if not chain or 'data' not in chain or not chain['data']: return []
                
                # Extract underlying price from the response (it might be in root or per strike)
                up = chain.get('underlying_price') or 0
                if up == 0 and len(chain['data']) > 0:
                    up = chain['data'][0].get('underlying_spot_price') or 0
                
                rows = []
                for strike_data in chain['data']:
                    strike = strike_data.get('strike_price')
                    
                    # Process Call Option
                    ce = strike_data.get('call_options')
                    if ce:
                        ce_market = ce.get('market_data', {})
                        ce_greeks = ce.get('option_greeks', {})
                        rows.append({
                            "strike": strike,
                            "dte": dte,
                            "iv": ce_greeks.get('iv', 0) or 0,
                            "volume": ce_market.get('volume', 0) or 0,
                            "open_interest": ce_market.get('oi', 0) or 0,
                            "option_type": "call",
                            "underlying_price": up
                        })
                        
                    # Process Put Option
                    pe = strike_data.get('put_options')
                    if pe:
                        pe_market = pe.get('market_data', {})
                        pe_greeks = pe.get('option_greeks', {})
                        rows.append({
                            "strike": strike,
                            "dte": dte,
                            "iv": pe_greeks.get('iv', 0) or 0,
                            "volume": pe_market.get('volume', 0) or 0,
                            "open_interest": pe_market.get('oi', 0) or 0,
                            "option_type": "put",
                            "underlying_price": up
                        })
                return rows
            except Exception as e:
                logger.error(f"[UPSTOX] [Master Data] Error fetching expiry {exp}: {e}")
                return []

        tasks = [fetch_one_expiry(exp) for exp in target_expiries]
        results = await asyncio.gather(*tasks)
        
        all_data = []
        underlying_price = 0
        for res in results:
            if not res: continue
            if underlying_price == 0:
                # Find the first valid underlying price from any expiry data
                for row in res:
                    if row.get('underlying_price', 0) > 0:
                        underlying_price = row['underlying_price']
                        break
            all_data.extend(res)

        # Fallback: Fetch index LTP directly if still 0 (common during weekends/holidays)
        if underlying_price == 0:
            from lib.api.market_data import get_ltp
            try:
                underlying_price = await run_in_threadpool(get_ltp, upstox_token, index_key)
            except:
                pass
                
        # 4. Filter data before plotting
        # Apply the user's interactive filters (DTE, OI, Strike Window)
        plot_data = [d for d in all_data if 
                         (min_dte <= d['dte'] <= max_dte) and 
                         (d['open_interest'] >= min_oi) and
                         (underlying_price == 0 or abs(d['strike'] - underlying_price) / underlying_price * 100 <= strike_window)]
        
        # Prepare Figure using plotly.graph_objects
        try:
            fig = create_option_3d_surface(
                plot_data, 
                underlying_price, 
                surface_type=surface_type, 
                metric=metric, 
                use_log_scale=use_log_scale, 
                theme=theme
            )
            
            return {
                "status": "success",
                "underlying_price": underlying_price,
                "data": plot_data, 
                "figure": json.loads(fig.to_json()) if fig else None
            }
        except Exception as e:
            logger.error(f"Error creating 3D surface figure: {e}")
            return {
                "status": "success",
                "underlying_price": underlying_price,
                "data": all_data,
                "figure": None,
                "error": str(e)
            }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=False)

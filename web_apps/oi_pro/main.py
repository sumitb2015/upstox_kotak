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

# Force UTF-8 output so Windows cp1252 doesn't crash on any emoji/unicode in logs
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
import json
import asyncio
import requests
from typing import Dict, List, Optional, Any
from pydantic import BaseModel
from fastapi.responses import HTMLResponse, RedirectResponse
import uvicorn
import subprocess
import signal
import psutil
from pathlib import Path
import re

# Import custom authentication module
from auth import router as auth_router, init_db, get_current_user, check_admin, User, BrokerCredential

# Add project root to path for lib imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from lib.api.option_chain import get_expiries, get_option_chain_dataframe, calculate_pcr, calculate_volume_pcr, calculate_oi_change_pcr, calculate_max_pain
from lib.api.market_data import get_full_option_chain, fetch_historical_data
from lib.utils.instrument_utils import get_option_instrument_key
from lib.api.streaming import UpstoxStreamer
from lib.api.historical import get_intraday_data_v3
from lib.core.authentication import get_access_token as auth_get_token
from lib.utils.greeks_helper import calculate_gex_for_chain, get_net_gex, prepare_snapshot, get_total_exposure, calculate_flip_point
from lib.utils.greeks_storage import greeks_storage
import pandas as pd
from datetime import datetime

# --- Instrument Map for Dashboard ---
SYMBOL_MAP = {
    "NIFTY": "NSE_INDEX|Nifty 50",
    "BANKNIFTY": "NSE_INDEX|Nifty Bank",
    "SENSEX": "BSE_INDEX|SENSEX"
}
# Reverse map for broadcasting
KEY_TO_SYMBOL = {v: k for k, v in SYMBOL_MAP.items()}

# Lookup for fetching LTP by symbol (Dynamic)
TRADING_SYMBOL_LOOKUP = {}

# --- Global Cache for Greeks History ---
# Structure: {(symbol, expiry): pd.DataFrame}
# Columns: [timestamp, strike, ce_delta, pe_delta, ce_gamma, pe_gamma, ce_oi, pe_oi, ...]
GREEKS_HISTORY_CACHE: Dict[tuple, pd.DataFrame] = {}
DELTA_HEATMAP_CACHE: Dict[tuple, List[dict]] = {}
GREEKS_LOCK = asyncio.Lock()
HEATMAP_LOCK = asyncio.Lock()
LAST_CACHE_RESET_DATE = datetime.now().date()

# --- Global Cache for Previous Closes (Indices) ---
PREV_CLOSES: Dict[str, float] = {}

# --- Baseline OI for Heatmap (fetched once at startup, static for the day) ---
# Structure: {(symbol, expiry, strike_float): {"ce_prev_oi": x, "pe_prev_oi": x, "ce_close": x, "pe_close": x}}
BASELINE_OI: Dict[tuple, dict] = {}

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
    except Exception as e:
        return f"Error tailing log: {str(e)}"


# --- Strategy Management ---

STRATEGIES_BASE_PATH = Path("c:/upstox_kotak/upstox_kotak/strategies")

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
    def __init__(self):
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
                        key = TRADING_SYMBOL_LOOKUP.get(sym)
                        if key and 'streamer' in globals() and streamer:
                            data = streamer.get_latest_data(key)
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
        env["PYTHONPATH"] = "c:/upstox_kotak/upstox_kotak"
        
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
                except Exception as e:
                    print(f"Error sending stop signal: {e}")

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
    Get data for Premium vs PoP Scatter Plot.
    """
    print(f" [CORE] [PoP API] Request received for {symbol} expiry {expiry}")
    try:
        instrument_key = SYMBOL_MAP.get(symbol.upper())
        if not instrument_key:
            raise HTTPException(status_code=400, detail="Invalid symbol")
            
        token = await get_access_token()
        
        # Run blocking call in threadpool to prevent freezing the server
        print(f" [PoP API] Fetching option chain for {instrument_key}...")
        df = await run_in_threadpool(get_option_chain_dataframe, token, instrument_key, expiry)
        
        if df is None or df.empty:
            print(f" [PoP API] No data found for {symbol}")
            return {"data": []}
            
        print(f" [PoP API] Processing {len(df)} rows...")
        
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
        
        print(f" [PoP API] Returning {len(points)} data points")
        return {"data": points}
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update config: {str(e)}")

# --- Broker Management API ---

@app.get("/api/brokers")
async def list_brokers(current_user: User = Depends(get_current_user)):
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
async def add_broker(broker_data: dict, current_user: User = Depends(get_current_user)):
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
                broker.api_key = api_key
            if api_secret and not api_secret.startswith("***"):
                broker.api_secret = api_secret
                
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
            api_key=api_key,
            api_secret=api_secret,
            redirect_uri=redirect_uri
        )
        return {"status": "success", "message": "Broker saved successfully", "id": broker.id}

@app.delete("/api/brokers/{broker_id}")
async def delete_broker(broker_id: int, current_user: User = Depends(get_current_user)):
    """Deletes the specified broker credential."""
    try:
        broker = BrokerCredential.get((BrokerCredential.id == broker_id) & (BrokerCredential.user == current_user))
        broker.delete_instance()
        return {"status": "success", "message": "Broker deleted"}
    except BrokerCredential.DoesNotExist:
        raise HTTPException(status_code=404, detail="Broker not found")

@app.post("/api/brokers/generate-token/{broker_id}")
async def generate_broker_token(broker_id: int, current_user: User = Depends(get_current_user)):
    """
    Returns the Upstox Auth URL to initiate manual login.
    """
    try:
        broker = BrokerCredential.get((BrokerCredential.id == broker_id) & (BrokerCredential.user == current_user))
        
        # Construct Upstox Auth URL
        # redirect_uri must match what's in Upstox Developer Portal
        # We use state to pass broker_id for the callback to identify the entry
        auth_url = (
            f"https://api-v2.upstox.com/login/authorization/dialog"
            f"?response_type=code"
            f"&client_id={broker.api_key}"
            f"&redirect_uri={requests.utils.quote(broker.redirect_uri or 'http://127.0.0.1:8001/api/brokers/callback/upstox')}"
            f"&state={broker.id}"
        )
        
        return {"status": "success", "auth_url": auth_url}
    except BrokerCredential.DoesNotExist:
        raise HTTPException(status_code=404, detail="Broker not found")

@app.get("/api/brokers/callback/upstox")
async def upstox_callback(request: Request, code: str, state: str):
    """
    OAuth Callback for Upstox.
    Exchanges authorization code for access token.
    Supports both direct navigation (redirect) and popup fetch API (JSON response).
    """
    broker_id = state
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
            
        # Update Broker entry
        broker.access_token = access_token
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

    async def subscribe(self, websocket: WebSocket, instrument_keys: List[str]):
        """Subscribe a websocket to specific instrument keys"""
        normalized_keys = [k.replace(':', '|') for k in instrument_keys]
        print(f" [WS] Subscribing socket to: {normalized_keys}")
        for key in normalized_keys:
            if key not in self.subscriptions:
                self.subscriptions[key] = []
            if websocket not in self.subscriptions[key]:
                self.subscriptions[key].append(websocket)
        
        # Trigger subscription on Upstox Streamer
        if streamer and streamer.market_streamer:
            try:
                streamer.subscribe_market_data(normalized_keys)
            except Exception as e:
                print(f" [WS] Error subscribing to keys {normalized_keys}: {e}")

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
                except Exception as e:
                    print(f" [WS] Disconnecting broken pipe for {instrument_key}")
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
            
            dashboard_msg = {
                "type": "market_update",
                "prices": {
                    symbol: {
                        "ltp": message.get('ltp') or message.get('last_price'),
                        "chg": 0.0 # Placeholder, calculating change requires yesterday's close
                    }
                }
            }
            
            # Try to calculate change if 'ohlc' or 'close' is present
            close = message.get('close') or message.get('ohlc', {}).get('close')
            
            # Fallback to pre-fetched close if live feed misses it
            if not close or close == 0:
                close = PREV_CLOSES.get(symbol, 0.0)

            if close:
                 ltp = dashboard_msg['prices'][symbol]['ltp']
                 if ltp and close > 0:
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
streamer: Optional[UpstoxStreamer] = None
loop = None # Global event loop reference

# --- WebSocket Endpoints ---

@app.websocket("/ws/straddle")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(None)):
    """
    Consolidated WebSocket endpoint for real-time Straddle updates.
    Client sends JSON subscribe request.
    """
    # Manual token check for WS (FastAPI Depends can sometimes be tricky with WS handshakes in some clients)
    try:
        if token:
            from auth import verify_jwt
            verify_jwt(token)
    except:
         await websocket.close(code=1008) # Policy Violation
         return

    await manager.connect(websocket)
    print(" [WS] New Straddle WS Connection")
    try:
        while True:
            # Flexible: accept text or json
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("action") == "subscribe" and msg.get("keys"):
                    # Normalize keys
                    keys = [k.replace(':', '|') for k in msg.get("keys", [])]
                    await manager.subscribe(websocket, keys)
            except json.JSONDecodeError:
                print(f" [WS] Invalid JSON received: {data}")
    except WebSocketDisconnect:
        print(" [WS] Straddle WS Disconnected")
        manager.disconnect(websocket)

@app.websocket("/ws/cumulative-prices")
async def websocket_cumulative_prices(websocket: WebSocket, token: str = Query(None)):
    """
    WebSocket endpoint for cumulative option prices.
    Authenticates via token query parameter and broadcasts live price updates.
    """
    # Manual token check
    try:
        if token:
            from auth import verify_jwt
            verify_jwt(token)
    except:
         await websocket.close(code=1008)
         return
    await manager.connect(websocket)
    print(" [WS] [CumulativePrices] New connection")

    ce_keys = []
    pe_keys = []
    index_key = None
    symbol = "NIFTY"  # track current symbol for threshold lookup
    # Session-open baseline for % change calculation (set on first valid tick)
    ce_open = None
    pe_open = None

    try:
        while True:
            try:
                # Non-blocking receive: wait 1s for a message, then broadcast update
                try:
                    data = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                    msg = json.loads(data)
                    if msg.get("action") == "subscribe":
                        symbol = msg.get("symbol", "NIFTY").upper()
                        expiry = msg.get("expiry")
                        if symbol and expiry:
                            print(f" [WS] [CumulativePrices] Subscribing {symbol} {expiry}...")
                            await websocket.send_json({"type": "status", "status": "loading", "symbol": symbol})

                            token = await get_access_token()
                            index_key = SYMBOL_MAP.get(symbol)
                            if not index_key:
                                await websocket.send_json({"type": "error", "message": f"Unknown symbol: {symbol}"})
                                continue

                            df = await run_in_threadpool(get_option_chain_dataframe, token, index_key, expiry)
                            if df is not None and not df.empty:
                                ce_keys = [k for k in df['ce_key'].tolist() if k and isinstance(k, str)]
                                pe_keys = [k for k in df['pe_key'].tolist() if k and isinstance(k, str)]

                                # Subscribe all option keys + the index key to real-time streamer
                                all_option_keys = ce_keys + pe_keys
                                if streamer and all_option_keys:
                                    try:
                                        streamer.subscribe_market_data(all_option_keys, mode="ltpc")
                                    except Exception as sub_err:
                                        print(f" [WS] [CumulativePrices] Subscription error: {sub_err}")

                                # Also subscribe the index key so Spot price is always available
                                if streamer and index_key:
                                    try:
                                        streamer.subscribe_market_data([index_key], mode="ltpc")
                                    except Exception as idx_err:
                                        print(f" [WS] [CumulativePrices] Index key subscription error: {idx_err}")

                                print(f" [WS] [CumulativePrices] {len(ce_keys)} CE + {len(pe_keys)} PE keys for {symbol}")
                                # Reset open baseline whenever user re-subscribes
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
                    pass  # 1-second elapsed — compute and broadcast

                # Compute and send cumulative update
                if (ce_keys or pe_keys) and streamer:
                    ce_sum = 0.0
                    pe_sum = 0.0
                    ce_valid = 0
                    pe_valid = 0
                    spot = 0.0

                    for k in ce_keys:
                        f = streamer.get_latest_data(k)
                        if f:
                            ltp = f.get('ltp') or f.get('last_price') or 0
                            if ltp > 0:
                                ce_sum += ltp
                                ce_valid += 1

                    for k in pe_keys:
                        f = streamer.get_latest_data(k)
                        if f:
                            ltp = f.get('ltp') or f.get('last_price') or 0
                            if ltp > 0:
                                pe_sum += ltp
                                pe_valid += 1

                    if index_key:
                        idx_f = streamer.get_latest_data(index_key)
                        if idx_f:
                            spot = idx_f.get('ltp') or idx_f.get('last_price') or 0

                    diff = round(ce_sum - pe_sum, 2)
                    # CE > PE => more call premium => bearish (resistance)
                    # PE > CE => more put premium => bullish (support)
                    # Adaptive thresholds per symbol (premiums scale with index level)
                    SENTIMENT_THRESHOLDS = {
                        "NIFTY": 50, "BANKNIFTY": 150, "SENSEX": 200
                    }
                    threshold = SENTIMENT_THRESHOLDS.get(symbol, 50)
                    if diff > threshold:
                        sentiment = "Bearish"
                    elif diff < -threshold:
                        sentiment = "Bullish"
                    else:
                        sentiment = "Neutral"

                    # --- % Change from session open (set on first valid tick) ---
                    if ce_sum > 0 and ce_open is None:
                        ce_open = ce_sum
                    if pe_sum > 0 and pe_open is None:
                        pe_open = pe_sum

                    ce_chg = round(((ce_sum - ce_open) / ce_open) * 100, 3) if ce_open else 0.0
                    pe_chg = round(((pe_sum - pe_open) / pe_open) * 100, 3) if pe_open else 0.0

                    # Per-strike average premiums (more meaningful than total sum)
                    avg_ce = round(ce_sum / ce_valid, 2) if ce_valid > 0 else 0.0
                    avg_pe = round(pe_sum / pe_valid, 2) if pe_valid > 0 else 0.0

                    await websocket.send_json({
                        "type": "cumulative_update",
                        "ce_sum": round(ce_sum, 2),
                        "pe_sum": round(pe_sum, 2),
                        "ce_chg": ce_chg,       # % change from session open
                        "pe_chg": pe_chg,       # % change from session open
                        "avg_ce": avg_ce,        # avg CE premium per strike
                        "avg_pe": avg_pe,        # avg PE premium per strike
                        "diff": diff,
                        "spot": round(spot, 2),
                        "ce_count": ce_valid,
                        "pe_count": pe_valid,
                        "sentiment": sentiment,
                        "timestamp": datetime.now().strftime("%H:%M:%S")
                    })

            except WebSocketDisconnect:
                break
            except Exception as e:
                print(f" [WS] [CumulativePrices] Loop Error: {e}")
                import traceback; traceback.print_exc()
                await asyncio.sleep(1)
    finally:
        manager.disconnect(websocket)
        print(" [WS] [CumulativePrices] Disconnected")

@app.on_event("startup")
async def startup_event_ws():
    """
    Initializes the Upstox WebSocket bridge on application startup.
    Sets up the market watch streamer and pre-fetches historical data for indices.
    """
    global streamer, loop
    loop = asyncio.get_event_loop()
    print(" Starting Upstox WebSocket Bridge...")
    try:
        # Initialize streamer with access token
        token = await get_access_token()
        streamer = UpstoxStreamer(token)
        
        # Define callback that bridges Thread -> Async
        def on_market_update(data):
            if loop and manager:
                asyncio.run_coroutine_threadsafe(manager.broadcast(data), loop)
                
        # Connect streamer
        indices_keys = list(SYMBOL_MAP.values())
        print(f" Subscribing to Dashboard Indices: {indices_keys}")

        # --- Pre-fetch Previous Closes for Indices ---
        print(" Pre-fetching previous closes for indices...")
        for sym, key in SYMBOL_MAP.items():
            try:
                # Fetch last 5 days daily candles
                end_date = datetime.now().strftime("%Y-%m-%d")
                start_date = (datetime.now() - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
                
                # We need to run this in threadpool as it's blocking
                hist_df = await run_in_threadpool(fetch_historical_data, token, key, "day", 1, start_date, end_date)
                
                if not hist_df.empty:
                    # Get the last row. 
                    # If today is a trading day and market is open/closed, the last candle MIGHT be today.
                    # We want the PREVIOUS day's close.
                    # Upstox Historical API usually includes today's candle if query covers it.
                    
                    # Logic: If last candle date is today, take the one before it. 
                    # If last candle date is before today, take it.
                    last_row = hist_df.iloc[-1]
                    last_date = last_row['timestamp'].date()
                    today_date = datetime.now().date()
                    
                    if last_date == today_date and len(hist_df) > 1:
                        prev_close = hist_df.iloc[-2]['close']
                    else:
                        prev_close = last_row['close']
                        
                    PREV_CLOSES[sym] = prev_close
                    print(f"    {sym}: Prev Close = {prev_close}")
                else:
                    print(f"    {sym}: No historical data found")
            except Exception as e:
                print(f"    {sym}: Failed to fetch history: {e}")

        # --- Prefetch Option Master for LTP Lookup ---
        asyncio.create_task(prefetch_option_master())
        
        # --- Start Greeks Poller (1-min interval) ---
        # Note: redundant as unified_background_poller is started in startup_event
        # asyncio.create_task(unified_background_poller())

        # Start Streamer
        streamer.connect_market_data(
            instrument_keys=indices_keys, 
            mode="ltpc", 
            on_message=on_market_update
        )
        print(" Upstox Streamer Connected & Listening")
        
    except Exception as e:
        print(f" Failed to initialize Upstox Streamer: {e}")

async def prefetch_option_master():
    """Fetches option chains for all indices to populate TRADING_SYMBOL_LOOKUP."""
    print(" [Dashboard] Prefetching Option Master for LTP Lookup...")
    try:
        token = await get_access_token()
        
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
                                    TRADING_SYMBOL_LOOKUP[f"CE {int(strike)}"] = ce_k
                                    count += 1
                                if pe_k:
                                    TRADING_SYMBOL_LOOKUP[f"PE {int(strike)}"] = pe_k
                                    count += 1

                print(f"   Mapped {count} options for {symbol}")
            except Exception as e:
                print(f"    Failed to prefetch {symbol}: {e}")
                
    except Exception as e:
        print(f" Prefetch failed: {e}")

async def load_todays_data():
    """
    Loads today's NIFTY Greeks snapshots from CSV into DELTA_HEATMAP_CACHE.
    This ensures that if the server is restarted mid-day, the full day
    history from 9:15 AM is available immediately.
    """
    print("[CORE] Loading today's NIFTY data from CSV...")
    try:
        token = await get_access_token()
        from lib.utils.greeks_helper import LOT_SIZE_MAP
        today = datetime.now().date()
        file_path = greeks_storage._get_file_path("NIFTY", today)
        if not file_path.exists():
            print(f"[CORE] No CSV found for today ({file_path.name}). Starting fresh.")
            return

        print(f"[CORE] Reading {file_path.name}...")
        df = pd.read_csv(file_path)
        if df.empty:
            print("[CORE] CSV is empty.")
            return

        # Parse timestamps, drop any corrupted rows
        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
        df = df.dropna(subset=['timestamp'])
        if df.empty:
            print("[CORE] No valid rows after timestamp parsing.")
            return

        lot_size = LOT_SIZE_MAP.get("NIFTY", 75)
        GREEKS_HISTORY_CACHE_LOCAL = {}

        for expiry, exp_group in df.groupby('expiry'):
            # Normalize expiry key: "YYYY-MM-DD" -> "YYYY-MM-DD 00:00:00"
            exp_str = str(expiry).strip()
            if len(exp_str) == 10:
                exp_str += " 00:00:00"

            cache_key = ("NIFTY", exp_str)
            GREEKS_HISTORY_CACHE[cache_key] = exp_group.copy()

            # Reconstruct per-minute snapshots for the heatmap
            snapshots = []
            df_copy = exp_group.copy()
            df_copy['time_key'] = df_copy['timestamp'].dt.strftime("%H:%M")

            for time_key, time_group in df_copy.groupby('time_key'):
                spot = float(time_group['spot_price'].iloc[0])

                # Filter to ATM +/- 8 strikes
                all_snaps_strikes = sorted(time_group['strike_price'].unique())
                if all_snaps_strikes:
                    atm = min(all_snaps_strikes, key=lambda s: abs(s - spot))
                    atm_idx = all_snaps_strikes.index(atm)
                    selected = set(all_snaps_strikes[max(0, atm_idx - 8) : atm_idx + 9])
                    time_group = time_group[time_group['strike_price'].isin(selected)]

                strike_deltas = []
                for _, row in time_group.iterrows():
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

                snapshots.append({"timestamp": time_key, "spot": spot, "strikes": strike_deltas})

            # Keep max 400 snapshots (covers full 09:15-15:30 trading day)
            async with HEATMAP_LOCK:
                DELTA_HEATMAP_CACHE[cache_key] = snapshots[-400:]
            print(f"[CORE] NIFTY {exp_str}: Loaded {len(DELTA_HEATMAP_CACHE[cache_key])} intervals from CSV.")

    except Exception as e:
        import traceback
        print(f"[CORE] load_todays_data failed: {e}")
        print(traceback.format_exc())

async def fetch_baseline_oi():
    """
    Fetches the previous session's OI and close prices ONCE at startup.
    Stores into BASELINE_OI  a static dict keyed by (symbol, expiry, strike).
    
    This feeds /api/delta-heatmap so all OI Change % shown on the heatmap
    are always relative to the previous session's closing OI regardless of
    when the server was started or restarted during the trading day.
    """
    global BASELINE_OI
    print("IN [CORE] [Baseline OI] Fetching previous session OI...")
    try:
        token = await get_access_token()
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
                key = (symbol.upper(), expiry, strike)
                BASELINE_OI[key] = {
                    "ce_prev_oi": float(row.get('ce_prev_oi', 0) or 0),
                    "pe_prev_oi": float(row.get('pe_prev_oi', 0) or 0),
                    "ce_close":   float(row.get('ce_close', 0) or 0),
                    "pe_close":   float(row.get('pe_close', 0) or 0),
                }
                count += 1

            print(f"    [Baseline OI] {symbol} {expiry}: Stored {count} strikes")

        print(f" [CORE] [Baseline OI] Done. Total keys: {len(BASELINE_OI)}")
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f" [CORE] [Baseline OI] Failed: {e}")

async def unified_background_poller():
    """
    Unified background task: 
    1. Polls all indices for GEX/Greeks history.
    2. Polls NIFTY specifically for the Delta Heatmap.
    3. Handles daily cache rollover.
    This consolidation reduces concurrent tasks and simplifies logging.
    """
    print(" [CORE] Unified Background Poller started (1-min interval)")
    global LAST_CACHE_RESET_DATE
    from lib.utils.greeks_helper import LOT_SIZE_MAP
    
    cycle_count = 0
    
    while True:
        try:
            # --- Daily Cache Reset ---
            today = datetime.now().date()
            if today > LAST_CACHE_RESET_DATE:
                print(f" [CORE] New day detected ({today}). Resetting all caches.")
                GREEKS_HISTORY_CACHE.clear()
                async with HEATMAP_LOCK:
                    DELTA_HEATMAP_CACHE.clear()
                async with GREEKS_LOCK:
                    GREEKS_HISTORY_CACHE.clear()
                LAST_CACHE_RESET_DATE = today

            token = await get_access_token()
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
                
                cache_key = (symbol, expiry)
                if cache_key not in GREEKS_HISTORY_CACHE:
                    GREEKS_HISTORY_CACHE[cache_key] = snapshot_df
                else:
                    GREEKS_HISTORY_CACHE[cache_key] = pd.concat([GREEKS_HISTORY_CACHE[cache_key], snapshot_df], ignore_index=True)
                
                # Store to CSV (Thread-pooled to prevent blocking)
                try:
                    await run_in_threadpool(greeks_storage.save_snapshot, symbol, expiry, snapshot_df)
                except Exception as storage_err:
                    print(f" [Poller] {symbol} Storage error: {storage_err}")

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

                    hm_cache_key = ("NIFTY", expiry)
                    async with HEATMAP_LOCK:
                        if hm_cache_key not in DELTA_HEATMAP_CACHE:
                            DELTA_HEATMAP_CACHE[hm_cache_key] = []
                        DELTA_HEATMAP_CACHE[hm_cache_key].append(heatmap_snap)
                        DELTA_HEATMAP_CACHE[hm_cache_key] = DELTA_HEATMAP_CACHE[hm_cache_key][-400:]
                    is_nifty_heatmap_updated = True

                # Small jitter to prevent API burst
                await asyncio.sleep(0.5)

            # --- Quiet Mode Logging (Every 5 cycles) ---
            if cycle_count % 5 == 0:
                print(f" [CORE] Poller Cycle {cycle_count} completed successfully at {datetime.now().strftime('%H:%M:%S')}")
            elif is_nifty_heatmap_updated and cycle_count % 1 == 0:
                 # Even quieter: just a single line if user wants to see movement, else comment out.
                 # Let's keep it very quiet as requested.
                 pass

            await asyncio.sleep(60) 
        except Exception as e:
            import traceback
            print(f" [CORE] Unified Poller Error: {e}")
            print(traceback.format_exc())
            await asyncio.sleep(30)

@app.on_event("startup")
async def startup_event():
    """Initialize background tasks and load state from disk."""
    print("START [CORE] Dashboard Server Starting...")
    try:
        # Initialize the authentication database
        init_db()
        print("[AUTH] Database initialized")
    except Exception as e:
        print(f"[AUTH] Failed to init DB: {e}")

    try:
        # 1. Recover persistent state
        await load_todays_data()
        
        # 2. Fetch yesterday's OI/Close as static baseline  do this BEFORE pollers start
        await fetch_baseline_oi()
        
        # 3. Launch Background Pollers
        print("[CORE] Starting background tasks...")
        asyncio.create_task(prefetch_option_master())
        asyncio.create_task(unified_background_poller())
        print("[CORE] Background processes initialized.")
    except Exception as e:
        print(f"[CORE] Startup Failure: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    global streamer
    if streamer:
        print(" Disconnecting Upstox Streamer...")
        streamer.disconnect_all()

@app.websocket("/ws/market-watch")
async def websocket_market_watch(websocket: WebSocket, token: str = Query(None)):
    """
    WebSocket endpoint for the dashboard market watch (LTP updates).
    Authenticates via token and subscribes the user to real-time index updates.
    """
    # Manual token check
    try:
        if token:
            from auth import verify_jwt
            verify_jwt(token)
    except:
         await websocket.close(code=1008)
         return
    """
    WebSocket endpoint for Dashboard Indices (NIFTY, BANKNIFTY, etc.)
    Broadcasts in format: { type: "market_update", prices: { SYMBOL: { ltp: ..., chg: ... } } }
    """
    await manager.connect_market_watch(websocket)
    try:
        # Send latest data immediately if available
        if streamer:
            initial_prices = {}
            for symbol, key in SYMBOL_MAP.items():
                data = streamer.get_latest_data(key)
                if data:
                    ltp = data.get('ltp') or data.get('last_price')
                    close = data.get('close') or data.get('ohlc', {}).get('close')
                    chg = 0.0
                    if ltp and close:
                        chg = round(((ltp - close) / close) * 100, 2)
                    
                    if ltp:
                        initial_prices[symbol] = {"ltp": ltp, "chg": chg}
            
            if initial_prices:
                await websocket.send_json({
                    "type": "market_update",
                    "prices": initial_prices
                })

        while True:
            # Keep connection alive
            await websocket.receive_text()
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"Market Watch WS Error: {e}")
        manager.disconnect(websocket)

# Duplicate consolidated (see line 647)
pass

# CORS Configuration for React Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def get_access_token():
    """
    Returns a valid access token using the core authentication library.
    Offloads the synchronous validation/refresh to a thread pool.
    """
    from starlette.concurrency import run_in_threadpool
    token = await run_in_threadpool(auth_get_token, auto_refresh=True)
    if not token:
        raise HTTPException(status_code=500, detail="Failed to retrieve or refresh access token. Please check .env credentials.")
    return token

def calculate_buildup(price_chg_pct, oi_chg_pct):
    if price_chg_pct > 0 and oi_chg_pct > 0: return "Long Buildup"
    if price_chg_pct < 0 and oi_chg_pct > 0: return "Short Buildup"
    if price_chg_pct > 0 and oi_chg_pct < 0: return "Short Covering"
    if price_chg_pct < 0 and oi_chg_pct < 0: return "Long Unwinding"
    return "Neutral"

@app.get("/login", response_class=HTMLResponse)
async def serve_login():
    """Serves the login page (index.html, but intended as a login barrier)."""
    html_path = os.path.join(os.path.dirname(__file__), "login.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="Login page not found")
    
    def read_file(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
            
    content = await run_in_threadpool(read_file, html_path)
    return HTMLResponse(content=content, media_type="text/html; charset=utf-8")

@app.get("/login.html", response_class=HTMLResponse)
async def serve_login_html():
    """Serves the actual login.html file."""
    return await serve_login()

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Serves the main dashboard (index.html)."""
    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="Index.html not found")
        
    def read_file(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
            
    content = await run_in_threadpool(read_file, html_path)
    return HTMLResponse(content=content, media_type="text/html; charset=utf-8")

@app.get("/pop", response_class=HTMLResponse)
async def serve_pop_page():
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
    print(f" [CORE] [Greeks API] Request received for {symbol} expiry {expiry}")
    try:
        instrument_key = SYMBOL_MAP.get(symbol.upper())
        if not instrument_key:
            raise HTTPException(status_code=400, detail="Invalid symbol")
            
        token = await get_access_token()
        
        # 1. Fetch Option Chain
        print(f" [Greeks API] Fetching option chain for {instrument_key}...")
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
        cache_key = (symbol, expiry)
        async with GREEKS_LOCK:
            if cache_key not in GREEKS_HISTORY_CACHE:
                GREEKS_HISTORY_CACHE[cache_key] = snapshot_df
            else:
                # Append new snapshot
                GREEKS_HISTORY_CACHE[cache_key] = pd.concat([GREEKS_HISTORY_CACHE[cache_key], snapshot_df], ignore_index=True)
        
        # Persistent storage (CSV) (Thread-pooled)
        try:
            await run_in_threadpool(greeks_storage.save_snapshot, symbol, expiry, snapshot_df)
        except Exception as storage_err:
            print(f" [Greeks API] Storage error: {storage_err}")
                
        print(f" [Greeks API] Cache updated. Total rows for {symbol}: {len(GREEKS_HISTORY_CACHE[cache_key])}")
        
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
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/debug-cache")
async def debug_cache(current_user: User = Depends(get_current_user)):
    async with HEATMAP_LOCK:
        heatmap_stats = {str(k): len(v) for k, v in DELTA_HEATMAP_CACHE.items()}
    async with GREEKS_LOCK:
        history_stats = {str(k): len(v) for k, v in GREEKS_HISTORY_CACHE.items()}
    return {
        "heatmap": heatmap_stats,
        "history": history_stats
    }

@app.get("/api/gex-history")
async def get_gex_history(symbol: str = "NIFTY", expiry: str = None, current_user: User = Depends(get_current_user)):
    """
    Returns time-series data for Net GEX and Spot Price.
    Used for the Net GEX regime traffic light chart.
    """
    try:
        token = await get_access_token()
        index_key = SYMBOL_MAP.get(symbol.upper())
        if not expiry:
            expiries = await run_in_threadpool(get_expiries, token, index_key)
            if not expiries: return {"status": "error", "message": "No expiries found"}
            expiry = str(expiries[0])
        else:
            # Normalize: frontend sends '2026-02-24T00:00:00', poller stores '2026-02-24 00:00:00'
            expiry = str(expiry).replace('T', ' ')
            
        cache_key = (symbol.upper(), expiry)
        async with GREEKS_LOCK:
            df_history = GREEKS_HISTORY_CACHE.get(cache_key)
            if df_history is not None:
                 df_history = df_history.copy() # Return a copy for thread-safety during processing
        
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
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"Error fetching GEX history: {e}")
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

        token = await get_access_token()
        if not expiry:
            expiries = await run_in_threadpool(get_expiries, token, index_key)
            if not expiries: return {"status": "error", "message": "No expiries"}
            expiry = str(expiries[0])
        else:
            expiry = str(expiry).replace('T', ' ')

        cache_key = (symbol.upper(), expiry)
        async with HEATMAP_LOCK:
            intervals = DELTA_HEATMAP_CACHE.get(cache_key, [])
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
        prev_close = PREV_CLOSES.get(symbol.upper(), open_spot)

        # Compute displayed strikes mathematically from current spot.
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
            baseline_key = (symbol.upper(), expiry, strike)
            baseline = BASELINE_OI.get(baseline_key, {})
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
    except Exception as e:
        import traceback
        err_msg = traceback.format_exc()
        print(err_msg, file=sys.stderr)
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
    except Exception as e:
        print(f"Error fetching strike greeks history: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/api/pcr-data")
async def get_pcr_data(current_user: User = Depends(get_current_user),
                      symbol: str = Query(..., description="Symbol like NIFTY"), 
                      expiry: str = Query(..., description="Expiry Date")):
    """
    Get data for PCR by Strike Grid.
    Returns list of {strike, pcr, sentiment, ce_oi, pe_oi, call_writer_domination, put_writer_domination}
    """
    print(f" [CORE] [PCR API] Request received for {symbol} expiry {expiry}")
    try:
        instrument_key = SYMBOL_MAP.get(symbol.upper())
        if not instrument_key:
            raise HTTPException(status_code=400, detail="Invalid symbol")
            
        token = await get_access_token()
        
        print(f" [UPSTOX] [PCR API] Fetching option chain for {instrument_key}...")
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
        
        print(f" [CORE] [PCR API] Returning {len(grid_data)} rows, spot={spot_price}")
        return {"data": grid_data, "spot_price": spot_price}
        
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
    print(f" [CORE] [Max Pain API] Request received for {symbol} expiry {expiry}")
    try:
        instrument_key = SYMBOL_MAP.get(symbol.upper())
        if not instrument_key:
            raise HTTPException(status_code=400, detail="Invalid symbol")
            
        token = await get_access_token()
        
        print(f" [Max Pain API] Fetching option chain for {instrument_key}...")
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
            
            # Only include strikes with valid IV data
            if ce_iv > 0 or pe_iv > 0:
                iv_data.append({
                    "strike": strike,
                    "ce_iv": round(ce_iv, 2) if ce_iv else 0,
                    "pe_iv": round(pe_iv, 2) if pe_iv else 0
                })
        
        # Sort by strike
        iv_data.sort(key=lambda x: x['strike'])
        
        # Get spot price
        spot_price = df['spot_price'].iloc[0] if not df.empty else 0
        
        print(f" [Max Pain API] Max Pain Strike: {max_pain_result['max_pain_strike']}, IV Data Points: {len(iv_data)}")
        
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
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# NOTE: SYMBOL_MAP is defined at the top of the file (line ~29). This duplicate has been removed.

@app.websocket("/ws/price/{symbol}")
async def price_websocket(websocket: WebSocket, symbol: str, token: str = Query(None)):
    # Manual token check
    try:
        if token:
            from auth import verify_jwt
            verify_jwt(token)
    except:
         await websocket.close(code=1008)
         return
    global streamer
    await manager.connect(websocket)
    
    if streamer is None:
        token = await get_access_token()
        streamer = UpstoxStreamer(token)
        streamer.connect_market_data(
            instrument_keys=list(SYMBOL_MAP.values()),
            mode="ltpc"
        )

    try:
        while True:
            await asyncio.sleep(0.5)
            key = SYMBOL_MAP.get(symbol.upper())
            if key and streamer:
                latest = streamer.get_latest_data(key)
                if latest and 'ltp' in latest:
                    await websocket.send_json({"type": "price", "ltp": latest['ltp']})
    except (WebSocketDisconnect, asyncio.CancelledError):
        manager.disconnect(websocket)

@app.get("/api/expiries")
async def fetch_expiries(symbol: str = "NIFTY"):
    token = await get_access_token()
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
    token = await get_access_token()
    key = SYMBOL_MAP.get(symbol.upper())
    if not key:
        raise HTTPException(status_code=400, detail="Invalid symbol")
    
    if not expiry:
        expiries = await run_in_threadpool(get_expiries, token, key)
        if not expiries:
            raise HTTPException(status_code=404, detail="No expiries found")
        expiry = expiries[0]

    df = await run_in_threadpool(get_option_chain_dataframe, token, key, expiry)
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail="Data not found")

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
            "oi": oi_pcr,
            "vol": vol_pcr,
            "oi_chg": oi_chg_pcr
        }
    else:
        df = df.replace([float('inf'), float('-inf')], 0).fillna(0)
        data = df.to_dict(orient="records")
        pcr_meta = {
            "oi": calculate_pcr(df),
            "vol": calculate_volume_pcr(df),
            "oi_chg": calculate_oi_change_pcr(df)
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
            "spot": spot,
            "pcr": pcr_meta
        },
        "data": data
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
    print(f" [CORE] [Straddle API] Request for {symbol} expiry {expiry}")
    try:
        token = await get_access_token()
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
        
        # Get list of all strikes for the dropdown
        all_strikes = sorted(df['strike_price'].unique().tolist())
        
        print(f" Target Strike: {target_strike} | CE: {ce_key} | PE: {pe_key}")
        
        # 2. Fetch Intraday Data for both legs
        ce_candles = await run_in_threadpool(get_intraday_data_v3, token, ce_key, "minute", 1)
        pe_candles = await run_in_threadpool(get_intraday_data_v3, token, pe_key, "minute", 1)
        
        if not ce_candles or not pe_candles:
            raise HTTPException(status_code=404, detail="Intraday data not found for one or more legs")
            
        # 3. Merge and Calculate
        ce_df = pd.DataFrame(ce_candles)
        pe_df = pd.DataFrame(pe_candles)
        
        # Merge on timestamp
        merged = pd.merge(ce_df, pe_df, on='timestamp', suffixes=('_ce', '_pe'))
        
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
    print(f" [UPSTOX] [Strike API] Request for {symbol} {strike} {expiry}")
    try:
        token = await get_access_token()
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
        
        if not ce_candles or not pe_candles:
            raise HTTPException(status_code=404, detail="Intraday data not found for legs")
            
        # 3. Merge and formatting
        ce_df = pd.DataFrame(ce_candles).rename(columns={'close': 'ce_ltp', 'oi': 'ce_oi'})[['timestamp', 'ce_ltp', 'ce_oi']]
        pe_df = pd.DataFrame(pe_candles).rename(columns={'close': 'pe_ltp', 'oi': 'pe_oi'})[['timestamp', 'pe_ltp', 'pe_oi']]
        
        merged = pd.merge(ce_df, pe_df, on='timestamp', how='inner')
        merged['timestamp'] = pd.to_datetime(merged['timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # Calculate changes vs Yesterday Close if available in candles (using first candle as proxy for open)
        # But for professional charts, we usually show absolute values or change from 09:15
        
        chart_data = merged.to_dict(orient="records")
        latest = merged.iloc[-1] if not merged.empty else {}
        
        all_strikes = sorted(df['strike_price'].unique().tolist())
        
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

    token = await get_access_token()
    
    # 1. Fetch Data for all legs (Throttled)
    _sem = asyncio.Semaphore(3)

    async def fetch_candle(leg):
        async with _sem:
            try:
                # Fetch only last 1 day (current day intraday)
                result = await run_in_threadpool(get_intraday_data_v3, token, leg.instrument_key, "minute", 1)
                await asyncio.sleep(0.1) # Debounce
                return {"leg": leg, "data": result}
            except Exception as e:
                print(f"Error fetching {leg.instrument_key}: {e}")
                return {"leg": leg, "data": None}

    tasks = [fetch_candle(leg) for leg in legs]
    results = await asyncio.gather(*tasks)

    # 2. Process Data  credit-first premium sum (SELL=+1, BUY=-1)
    price_dfs = []
    vol_dfs = []
    for res in results:
        data = res['data']
        leg = res['leg']
        if data:
            df = pd.DataFrame(data)[['timestamp', 'close', 'volume']]
            # Convert to IST naive timestamps (strip +05:30 offset)
            df['timestamp'] = pd.to_datetime(df['timestamp'], utc=False)
            if df['timestamp'].dt.tz is not None:
                df['timestamp'] = df['timestamp'].dt.tz_convert('Asia/Kolkata').dt.tz_localize(None)
            col = f'price_{leg.instrument_key}'
            vcol = f'vol_{leg.instrument_key}'
            # Apply direction and lot multiplier (Credit-first: SELL=+1, BUY=-1)
            mult = 1 if leg.direction == "SELL" else -1
            df[col] = df['close'] * mult * leg.lot
            df[vcol] = df['volume']
            df.set_index('timestamp', inplace=True)
            price_dfs.append(df[[col]])
            vol_dfs.append(df[[vcol]])

    if not price_dfs:
        return {"status": "error", "message": "No data found for any legs", "data": []}

    # 3. Align and Sum
    price_combined = pd.concat(price_dfs, axis=1, join='outer').sort_index()
    vol_combined = pd.concat(vol_dfs, axis=1, join='outer').sort_index()

    # Filter: Today's date + Market hours (09:15 - 15:30) in IST (tz-naive)
    today = datetime.now().strftime('%Y-%m-%d')
    price_combined = price_combined[price_combined.index.strftime('%Y-%m-%d') == today]
    price_combined = price_combined.between_time('09:15', '15:30')
    vol_combined = vol_combined[vol_combined.index.strftime('%Y-%m-%d') == today]
    vol_combined = vol_combined.between_time('09:15', '15:30')

    if price_combined.empty:
        return {"status": "success", "data": []}

    # Forward fill prices, fill volume NaN with 0
    price_combined = price_combined.ffill().fillna(0)
    vol_combined = vol_combined.fillna(0)

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

    # Format timestamps as IST strings
    combined_df.reset_index(inplace=True)
    combined_df['timestamp'] = combined_df['timestamp'].dt.strftime('%Y-%m-%dT%H:%M:%S+05:30')

    chart_data = combined_df[['timestamp', 'premium', 'vwap']].to_dict(orient='records')

    return {
        "status": "success",
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
    print(f" [UPSTOX] [Cumulative OI] Fetching data for {symbol} expiry {expiry}")
    try:
        token = await get_access_token()
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
            raise HTTPException(status_code=404, detail="Index intraday data not found")
            
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
            raise HTTPException(status_code=404, detail="No CE data found")

        # 2. Align PE Data
        if pe_dfs:
            pe_combined = pe_dfs[0]
            for i in range(1, len(pe_dfs)):
                pe_combined = pd.merge(pe_combined, pe_dfs[i], on='timestamp', how='outer', suffixes=(f'_{i-1}', f'_{i}'))
            
            oi_cols = [c for c in pe_combined.columns if 'pe_oi' in c]
            pe_combined['pe_oi_total'] = pe_combined[oi_cols].sum(axis=1)
            pe_total_df = pe_combined[['timestamp', 'pe_oi_total']].rename(columns={'pe_oi_total': 'pe_oi'})
        else:
            raise HTTPException(status_code=404, detail="No PE data found")
        
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
        token = await get_access_token()
        underlying_key = SYMBOL_MAP.get(symbol.upper())
        if not underlying_key:
             raise HTTPException(status_code=400, detail="Invalid Symbol")

        # Fetch Data
        df = await run_in_threadpool(get_full_option_chain, token, underlying_key, expiry)
        
        if df.empty:
             return {"chain": [], "spot": 0}

        spot = df['underlying_spot'].iloc[0] if not df.empty else 0

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
        chain_data = df.to_dict(orient='records')
        
        return {
            "chain": chain_data,
            "spot": spot,
            "top_ce": top_ce,
            "top_pe": top_pe
        }

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
    print(f" [UPSTOX] [Multi-Strike OI] Request: {symbol} | {expiry} | Strikes: {strikes}")
    try:
        token = await get_access_token()
        underlying_key = SYMBOL_MAP.get(symbol.upper())
        if not underlying_key:
            print(f" [UPSTOX] [Multi-Strike OI] Invalid symbol: {symbol}")
            raise HTTPException(status_code=400, detail="Invalid symbol")
            
        strike_list = [float(s.strip()) for s in strikes.split(",") if s.strip()]
        if not strike_list:
            raise HTTPException(status_code=400, detail="No strikes provided")

        # 1. Get Option Chain to find keys for all strikes
        print(f" [UPSTOX] [Multi-Strike OI] Fetching chain for {symbol} {expiry}...")
        df = await run_in_threadpool(get_option_chain_dataframe, token, underlying_key, expiry)
        if df is None or df.empty:
            print(f" [UPSTOX] [Multi-Strike OI] No option chain found")
            raise HTTPException(status_code=404, detail="No option chain data")
            
        df_subset = df[df['strike_price'].isin(strike_list)].copy()
        if df_subset.empty:
            print(f" [UPSTOX] [Multi-Strike OI] Strikes {strike_list} not found in chain")
            raise HTTPException(status_code=404, detail="Selected strikes not found in chain")
            
        # 2. Fetch Intraday data for all selected legs
        _sem = asyncio.Semaphore(5)
        async def fetch_candle(instr_key, strike, type):
            async with _sem:
                print(f" [UPSTOX] [Multi-Strike OI] Fetching {strike} {type} ({instr_key})")
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
        print(f" [UPSTOX] [Multi-Strike OI] Gathered {len(results)} legs")
        
        # 3. Process and Align
        all_dfs = []
        for i, candles in enumerate(results):
            m = mapping[i]
            col_name = f"{int(m['strike'])}_{m['type']}"
            
            if not candles: 
                print(f" [UPSTOX] [Multi-Strike OI] No data for {col_name}")
                continue
            
            df_leg = pd.DataFrame(candles)[['timestamp', 'oi']].rename(columns={'oi': col_name})
            df_leg['timestamp'] = pd.to_datetime(df_leg['timestamp'])
            all_dfs.append(df_leg)
            
        if not all_dfs:
            print(f" [UPSTOX] [Multi-Strike OI] All legs returned empty")
            return {"status": "success", "data": [], "metadata": {"strikes": strike_list}}
            
        # Outer merge all dataframes on timestamp
        merged = all_dfs[0]
        for i in range(1, len(all_dfs)):
            merged = pd.merge(merged, all_dfs[i], on='timestamp', how='outer')
            
        # Sort and fill gaps
        merged = merged.sort_values('timestamp').ffill().fillna(0)
        merged['timestamp'] = merged['timestamp'].dt.strftime('%H:%M')
        
        print(f" [UPSTOX] [Multi-Strike OI] Success. Rows: {len(merged)}")
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

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f" [UPSTOX] [Multi-Strike OI] Error: {str(e)}")
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
    print(f" [UPSTOX] [Multi-Strike Price] Request: {symbol} | {expiry} | Strikes: {strikes}")
    try:
        token = await get_access_token()
        underlying_key = SYMBOL_MAP.get(symbol.upper())
        if not underlying_key:
            print(f" [UPSTOX] [Multi-Strike Price] Invalid symbol: {symbol}")
            raise HTTPException(status_code=400, detail="Invalid symbol")
            
        strike_list = [float(s.strip()) for s in strikes.split(",") if s.strip()]
        if not strike_list:
            raise HTTPException(status_code=400, detail="No strikes provided")

        # 1. Get Option Chain to find keys for all strikes
        print(f" [UPSTOX] [Multi-Strike Price] Fetching chain for {symbol} {expiry}...")
        df = await run_in_threadpool(get_option_chain_dataframe, token, underlying_key, expiry)
        if df is None or df.empty:
            print(f" [UPSTOX] [Multi-Strike Price] No option chain found")
            raise HTTPException(status_code=404, detail="No option chain data")
            
        df_subset = df[df['strike_price'].isin(strike_list)].copy()
        if df_subset.empty:
            print(f" [UPSTOX] [Multi-Strike Price] Strikes {strike_list} not found in chain")
            raise HTTPException(status_code=404, detail="Selected strikes not found in chain")
            
        # 2. Fetch Intraday data for all selected legs
        _sem = asyncio.Semaphore(5)
        async def fetch_candle(instr_key, strike, type):
            async with _sem:
                print(f" [UPSTOX] [Multi-Strike Price] Fetching {strike} {type} ({instr_key})")
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
        print(f" [UPSTOX] [Multi-Strike Price] Gathered {len(results)} legs")
        
        # 3. Process and Align
        all_dfs = []
        for i, candles in enumerate(results):
            m = mapping[i]
            col_name = f"{int(m['strike'])}_{m['type']}"
            
            if not candles: 
                print(f" [UPSTOX] [Multi-Strike Price] No data for {col_name}")
                continue
            
            df_leg = pd.DataFrame(candles)[['timestamp', 'close']].rename(columns={'close': col_name})
            df_leg['timestamp'] = pd.to_datetime(df_leg['timestamp'])
            all_dfs.append(df_leg)
            
        if not all_dfs:
            print(f" [UPSTOX] [Multi-Strike Price] All legs returned empty")
            return {"status": "success", "data": [], "metadata": {"strikes": strike_list}}
            
        # Outer merge all dataframes on timestamp
        merged = all_dfs[0]
        for i in range(1, len(all_dfs)):
            merged = pd.merge(merged, all_dfs[i], on='timestamp', how='outer')
            
        # Sort and fill gaps
        merged = merged.sort_values('timestamp').ffill().fillna(0)
        merged['timestamp'] = merged['timestamp'].dt.strftime('%H:%M')
        
        print(f" [UPSTOX] [Multi-Strike Price] Success. Rows: {len(merged)}")
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

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f" [UPSTOX] [Multi-Strike Price] Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)

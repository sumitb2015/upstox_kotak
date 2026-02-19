import sys
import os
import time
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional, Dict
from pydantic import BaseModel
from fastapi.responses import HTMLResponse
import uvicorn
import json
import asyncio
import subprocess
import signal
import psutil
from pathlib import Path
import re

# Add project root to path for lib imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from lib.api.option_chain import get_expiries, get_option_chain_dataframe, calculate_pcr, calculate_volume_pcr, calculate_oi_change_pcr, calculate_max_pain
from lib.api.market_data import get_full_option_chain, fetch_historical_data
from lib.utils.instrument_utils import get_option_instrument_key
from lib.api.streaming import UpstoxStreamer
from lib.api.historical import get_intraday_data_v3
from lib.core.authentication import get_access_token as auth_get_token
from lib.utils.greeks_helper import calculate_gex_for_chain, get_net_gex, prepare_snapshot
from lib.utils.greeks_storage import greeks_storage
import pandas as pd
from datetime import datetime

# --- Instrument Map for Dashboard ---
SYMBOL_MAP = {
    "NIFTY": "NSE_INDEX|Nifty 50",
    "BANKNIFTY": "NSE_INDEX|Nifty Bank",
    "FINNIFTY": "NSE_INDEX|Nifty Fin Service", 
    "NIFTYIT": "NSE_INDEX|Nifty IT",
    "MIDCPNIFTY": "NSE_INDEX|NIFTY MID SELECT",
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

# --- Global Cache for Previous Closes (Indices) ---
PREV_CLOSES: Dict[str, float] = {}

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

    def get_strategy_status(self, strategy_id: str) -> Dict:
        """Checks if a strategy process is running and returns its metadata."""
        is_running = self._check_is_running(strategy_id)
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
             for p in psutil.process_iter(['pid', 'cmdline']):
                try:
                    cmdline = p.info['cmdline']
                    if cmdline and "live.py" in cmdline[-1] and strategy_id in "".join(cmdline):
                        pid = p.info['pid']
                        # Recover start time from process info
                        try:
                            create_time = datetime.fromtimestamp(p.create_time())
                            self.start_times[strategy_id] = create_time
                            uptime_delta = datetime.now() - create_time
                            uptime = str(uptime_delta).split('.')[0]
                        except:
                            pass
                        break
                except:
                    pass

        # Get PnL from state file if it exists AND strategy is running
        pnl = 0.0
        state_details = {}
        
        if is_running:
            info = STRATEGIES_INFO.get(strategy_id)
            if info:
                state_file = info['path'] / "strategy_state.json"
                if state_file.exists():
                    try:
                        with open(state_file, 'r') as f:
                            state = json.load(f)
                            pnl = state.get('pnl', 0.0) or state.get('total_pnl', 0.0)
                            
                            # Extract additional details
                            state_details['entry_state'] = state.get('entry_state', 'UNKNOWN')
                            state_details['total_qty'] = state.get('total_qty', 0)
                            
                            # Enhance positions with LTP if available
                            raw_positions = state.get('active_positions', {})
                            enhanced_positions = {}
                            
                            for sym, qty in raw_positions.items():
                                ltp = None
                                # 1. Try to get key from lookup
                                key = TRADING_SYMBOL_LOOKUP.get(sym)
                                
                                # 2. If streamer available, get price
                                if key and streamer:
                                    data = streamer.get_latest_data(key)
                                    if data:
                                        ltp = data.get('ltp')
                                        
                                # 3. Fallback: Check if streamer has data by symbol (expensive iteration, skipping for now)
                                enhanced_positions[sym] = {"qty": qty, "ltp": ltp}

                            state_details['positions'] = enhanced_positions
                    except:
                        pass

        return {
            "id": strategy_id,
            "is_running": is_running,
            "pid": pid,
            "uptime": uptime,
            "pnl": round(pnl, 2),
            "details": state_details
        }

    def start_strategy(self, strategy_id: str):
        """Starts a strategy live.py as a background process."""
        if strategy_id in self.processes and self.processes[strategy_id].poll() is None:
            raise HTTPException(status_code=400, detail="Strategy already running")
            
        info = STRATEGIES_INFO.get(strategy_id)
        if not info:
             raise HTTPException(status_code=404, detail="Strategy not found")
             
        live_file = info['path'] / "live.py"
        if not live_file.exists():
            raise HTTPException(status_code=404, detail="live.py not found")
            
        # Set PYTHONPATH to project root so imports work
        env = os.environ.copy()
        env["PYTHONPATH"] = "c:/upstox_kotak/upstox_kotak"
        
        try:
            # Create/Open log file (overwrite for fresh logs on new run)
            log_path = info['path'] / "strategy.log"
            self.log_files[strategy_id] = open(log_path, "w")

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

    def stop_strategy(self, strategy_id: str):
        """Terminated a strategy process. Tries graceful stop via file signal first."""
        # 1. Check internal tracking
        proc = self.processes.get(strategy_id)
        info = STRATEGIES_INFO.get(strategy_id)
        
        if proc:
            # A. Graceful Stop Signal (.STOP file)
            if info:
                stop_signal_file = info['path'] / ".STOP"
                try:
                    stop_signal_file.touch()
                    # Wait for strategy to pick it up and exit (max 5s)
                    for _ in range(50):
                        if proc.poll() is not None:
                            break
                        time.sleep(0.1)
                except Exception as e:
                    print(f"Error sending stop signal: {e}")

            # B. Force Terminate if still running
            if proc.poll() is None:
                try:
                    p = psutil.Process(proc.pid)
                    for child in p.children(recursive=True):
                        child.terminate()
                    p.terminate()
                    p.wait(timeout=3)
                except:
                    if proc.poll() is None:
                        proc.kill()
            
            # C. Cleanup
            del self.processes[strategy_id]
            if strategy_id in self.start_times:
                del self.start_times[strategy_id]
            
            # Close log file handle if open
            if strategy_id in self.log_files:
                try:
                    self.log_files[strategy_id].close()
                except:
                    pass
                del self.log_files[strategy_id]
                
            # Remove signal file if it still exists
            if info and (info['path'] / ".STOP").exists():
                try: (info['path'] / ".STOP").unlink()
                except: pass

            return {"status": "stopped"}
        
        # 2. Check psutil (for orphaned processes)
        stopped = False
        for p in psutil.process_iter(['pid', 'cmdline']):
            try:
                cmdline = p.info['cmdline']
                if cmdline and "live.py" in cmdline[-1] and strategy_id in "".join(cmdline):
                    p.terminate()
                    stopped = True
            except:
                continue
                
        if stopped:
            return {"status": "stopped"}
            
        raise HTTPException(status_code=400, detail="Strategy not running")

    def get_strategy_logs(self, strategy_id: str, lines: int = 100) -> Dict:
        """Reads the last N lines from the strategy log file."""
        # Check if running first - if not, return empty/blank logs as requested
        # Use the robust check that handles restarts
        if not self._check_is_running(strategy_id):
            return {"logs": []}

        info = STRATEGIES_INFO.get(strategy_id)
        if not info:
             raise HTTPException(status_code=404, detail="Strategy not found")
        
        log_file = info['path'] / "strategy.log"
        if not log_file.exists():
            return {"logs": ["No logs available yet."]}
            
        try:
            # Simple implementation for tailing last N lines
            # For very large files, this might be inefficient but sufficient for now
            with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
                # Read all lines and take last N
                # Improved: using deque for memory efficiency if file is huge? 
                # Or just simple list slicing for now as logs rotate or are small
                content = f.readlines()
                return {"logs": content[-lines:]}
        except Exception as e:
            return {"logs": [f"Error reading logs: {str(e)}"]}

strategy_manager = StrategyManager()

app = FastAPI(title="OI Pro Analytics API", version="1.0.0")

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
async def get_pop_data(symbol: str = Query(..., description="Symbol like NIFTY"), 
                      expiry: str = Query(..., description="Expiry Date")):
    """
    Get data for Premium vs PoP Scatter Plot.
    """
    print(f"📉 [CORE] [PoP API] Request received for {symbol} expiry {expiry}")
    try:
        instrument_key = SYMBOL_MAP.get(symbol.upper())
        if not instrument_key:
            raise HTTPException(status_code=400, detail="Invalid symbol")
            
        token = get_access_token()
        
        # Run blocking call in threadpool to prevent freezing the server
        print(f"📉 [PoP API] Fetching option chain for {instrument_key}...")
        df = await run_in_threadpool(get_option_chain_dataframe, token, instrument_key, expiry)
        
        if df is None or df.empty:
            print(f"⚠️ [PoP API] No data found for {symbol}")
            return {"data": []}
            
        print(f"📉 [PoP API] Processing {len(df)} rows...")
        
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
        
        print(f"✅ [PoP API] Returning {len(points)} data points")
        return {"data": points}
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# --- Strategy Management API ---

@app.get("/api/strategies")
async def list_strategies():
    """Returns status of all tracked strategies."""
    results = []
    for strategy_id in STRATEGIES_INFO:
        status = strategy_manager.get_strategy_status(strategy_id)
        info = STRATEGIES_INFO[strategy_id]
        results.append({
            **status,
            "name": info["name"],
            "description": info["description"]
        })
    return {"strategies": results}

@app.post("/api/strategies/start/{strategy_id}")
async def start_strategy(strategy_id: str):
    return strategy_manager.start_strategy(strategy_id)

@app.post("/api/strategies/stop/{strategy_id}")
async def stop_strategy(strategy_id: str):
    return strategy_manager.stop_strategy(strategy_id)

@app.get("/api/strategies/logs/{strategy_id}")
async def get_strategy_logs(strategy_id: str):
    return strategy_manager.get_strategy_logs(strategy_id)

@app.get("/api/strategies/config/{strategy_id}")
async def get_strategy_config(strategy_id: str):
    """Parses config.py and returns the CONFIG dictionary."""
    info = STRATEGIES_INFO.get(strategy_id)
    if not info:
        raise HTTPException(status_code=404, detail="Strategy not found")
        
    config_file = info['path'] / "config.py"
    if not config_file.exists():
        raise HTTPException(status_code=404, detail="config.py not found")
        
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("config", str(config_file))
        config_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config_module)
        return {"config": config_module.CONFIG}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read config: {str(e)}")

@app.post("/api/strategies/config/{strategy_id}")
async def update_strategy_config(strategy_id: str, new_config: Dict):
    """Updates specific keys in config.py using regex to preserve comments."""
    info = STRATEGIES_INFO.get(strategy_id)
    if not info:
        raise HTTPException(status_code=404, detail="Strategy not found")
        
    config_file = info['path'] / "config.py"
    if not config_file.exists():
        raise HTTPException(status_code=404, detail="config.py not found")
        
    try:
        content = config_file.read_text()
        
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
                # If key not found in current content (maybe newly added or formatting different)
                # We could append it but safer to only update existing
                pass
            
        config_file.write_text(content)
        return {"status": "success", "message": "Configuration updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update config: {str(e)}")

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
        for key in instrument_keys:
            if key not in self.subscriptions:
                self.subscriptions[key] = []
            if websocket not in self.subscriptions[key]:
                self.subscriptions[key].append(websocket)
        
        # Trigger subscription on Upstox Streamer
        if streamer and streamer.market_streamer:
            try:
                streamer.subscribe_market_data(instrument_keys)
            except Exception as e:
                print(f"Error subscribing to keys {instrument_keys}: {e}")

    async def broadcast(self, message: dict):
        """
        Broadcasts message to relevant subscribers based on instrument_key.
        Also broadcasts to Market Watch if the key is an index.
        This method must be called from an async loop.
        """
        instrument_key = message.get('instrument_key')
        
        # 1. Targeted Subscriptions (Straddle Chart)
        if instrument_key and instrument_key in self.subscriptions:
            to_remove = []
            for connection in self.subscriptions[instrument_key]:
                try:
                    await connection.send_json(message)
                except Exception as e:
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

@app.on_event("startup")
async def startup_event():
    global streamer, loop
    loop = asyncio.get_event_loop()
    print("🚀 Starting Upstox WebSocket Bridge...")
    try:
        # Initialize streamer with access token
        token = auth_get_token()
        streamer = UpstoxStreamer(token)
        
        # Define callback that bridges Thread -> Async
        def on_market_update(data):
            if loop and manager:
                asyncio.run_coroutine_threadsafe(manager.broadcast(data), loop)
                
        # Connect streamer
        indices_keys = list(SYMBOL_MAP.values())
        print(f"📡 Subscribing to Dashboard Indices: {indices_keys}")

        # --- Pre-fetch Previous Closes for Indices ---
        print("⏳ Pre-fetching previous closes for indices...")
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
                    print(f"   ✅ {sym}: Prev Close = {prev_close}")
                else:
                    print(f"   ⚠️ {sym}: No historical data found")
            except Exception as e:
                print(f"   ❌ {sym}: Failed to fetch history: {e}")

        # --- Prefetch Option Master for LTP Lookup ---
        asyncio.create_task(prefetch_option_master())
        
        # --- Start Greeks Poller (1-min interval) ---
        asyncio.create_task(poll_major_greeks())

        # Start Streamer
        streamer.connect_market_data(
            instrument_keys=indices_keys, 
            mode="ltpc", 
            on_message=on_market_update
        )
        print("✅ Upstox Streamer Connected & Listening")
        
    except Exception as e:
        print(f"❌ Failed to initialize Upstox Streamer: {e}")

async def prefetch_option_master():
    """Fetches option chains for all indices to populate TRADING_SYMBOL_LOOKUP."""
    print("⏳ [Dashboard] Prefetching Option Master for LTP Lookup...")
    try:
        token = auth_get_token()
        
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
                print(f"   ⚠️ Failed to prefetch {symbol}: {e}")
                
    except Exception as e:
        print(f"❌ Prefetch failed: {e}")

async def poll_major_greeks():
    """
    Background task to poll NIFTY and BANKNIFTY Greeks every 1 minute.
    Populates GREEKS_HISTORY_CACHE for Net GEX line charts.
    """
    print("🚀 [CORE] [Greeks Poller] Background task started (1-min interval)")
    while True:
        try:
            token = auth_get_token()
            for symbol in ["NIFTY", "BANKNIFTY"]:
                index_key = SYMBOL_MAP.get(symbol)
                if not index_key: continue
                
                expiries = await run_in_threadpool(get_expiries, token, index_key)
                if not expiries: continue
                
                expiry = str(expiries[0]) # Target current week (normalized string)
                print(f"📊 [Greeks Poller] Fetching {symbol} {expiry}...")
                
                df = await run_in_threadpool(get_option_chain_dataframe, token, index_key, expiry)
                if df is not None and not df.empty:
                    # Calculate and cache
                    df = calculate_gex_for_chain(df, symbol)
                    snapshot_df = prepare_snapshot(df)
                    
                    cache_key = (symbol, expiry)
                    if cache_key not in GREEKS_HISTORY_CACHE:
                        GREEKS_HISTORY_CACHE[cache_key] = snapshot_df
                    else:
                        # Append new snapshot
                        GREEKS_HISTORY_CACHE[cache_key] = pd.concat([GREEKS_HISTORY_CACHE[cache_key], snapshot_df], ignore_index=True)
                    
                    print(f"   ✅ {symbol} GEX Saved. Points: {len(GREEKS_HISTORY_CACHE[cache_key])}")
                    
                    # Cleanup: Keep only today's data
                    today = datetime.now().date()
                    GREEKS_HISTORY_CACHE[cache_key] = GREEKS_HISTORY_CACHE[cache_key][
                        GREEKS_HISTORY_CACHE[cache_key]['timestamp'].dt.date == today
                    ]
                    
                    # Persistent storage (CSV)
                    try:
                        greeks_storage.save_snapshot(symbol, expiry, snapshot_df)
                    except Exception as storage_err:
                        print(f"❌ [Greeks Poller] Storage error: {storage_err}")
            
            await asyncio.sleep(60) # 1 minute interval
        except Exception as e:
            print(f"❌ [Greeks Poller] Error: {e}")
            await asyncio.sleep(30) # Wait before retry

@app.on_event("shutdown")
async def shutdown_event():
    global streamer
    if streamer:
        print("🛑 Disconnecting Upstox Streamer...")
        streamer.disconnect_all()

@app.websocket("/ws/market-watch")
async def websocket_market_watch(websocket: WebSocket):
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

@app.websocket("/ws/straddle")
async def websocket_straddle(websocket: WebSocket):
    """
    WebSocket endpoint for real-time Straddle updates.
    Client sends: {"action": "subscribe", "keys": ["NSE_FO|...", "NSE_FO|..."]}
    Server sends: Stream of tick data for those keys.
    """
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("action") == "subscribe":
                # Normalize keys to use pipe separator to match streamer updates
                keys = [k.replace(':', '|') for k in data.get("keys", [])]
                if keys:
                    print(f"📥 [Straddle WS] Received subscribe request for: {keys}")
                    await manager.subscribe(websocket, keys)
                    print(f"📡 [Straddle WS] Client subscribed. Active Subs: {list(manager.subscriptions.keys())}")
                    
                    # Send immediate latest data if available
                    if streamer:
                        for key in keys:
                            latest = streamer.get_latest_data(key)
                            if latest:
                                await websocket.send_json(latest)
                                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        print("🔌 Client disconnected")
    except Exception as e:
        print(f"WebSocket Error: {e}")
        manager.disconnect(websocket)

# CORS Configuration for React Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_access_token():
    """
    Returns a valid access token using the core authentication library.
    Automatically handles validation and refresh if credentials are in .env.
    """
    token = auth_get_token(auto_refresh=True)
    if not token:
        raise HTTPException(status_code=500, detail="Failed to retrieve or refresh access token. Please check .env credentials.")
    return token

def calculate_buildup(price_chg_pct, oi_chg_pct):
    if price_chg_pct > 0 and oi_chg_pct > 0: return "Long Buildup"
    if price_chg_pct < 0 and oi_chg_pct > 0: return "Short Buildup"
    if price_chg_pct > 0 and oi_chg_pct < 0: return "Short Covering"
    if price_chg_pct < 0 and oi_chg_pct < 0: return "Long Unwinding"
    return "Neutral"

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="Index.html not found")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), media_type="text/html; charset=utf-8")

@app.get("/pop", response_class=HTMLResponse)
async def serve_pop_page():
    html_path = os.path.join(os.path.dirname(__file__), "pop.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="pop.html not found")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), media_type="text/html; charset=utf-8")

@app.get("/pcr", response_class=HTMLResponse)
async def serve_pcr_page():
    html_path = os.path.join(os.path.dirname(__file__), "pcr.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="pcr.html not found")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), media_type="text/html; charset=utf-8")

@app.get("/multi", response_class=HTMLResponse)
async def serve_multi_chart_page():
    """
    Serves the Multi-Option Chart page.
    Allows users to build custom strategies with multiple legs and view combined premium charts.
    """
    html_path = os.path.join(os.path.dirname(__file__), "multi_chart.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="multi_chart.html not found")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), media_type="text/html; charset=utf-8")

@app.get("/straddle", response_class=HTMLResponse)
async def serve_straddle_page():
    """
    Serves the ATM Straddle Analysis dashboard page.
    """
    html_path = os.path.join(os.path.dirname(__file__), "straddle.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="straddle.html not found")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), media_type="text/html; charset=utf-8")

@app.get("/cumulative", response_class=HTMLResponse)
async def serve_cumulative_page():
    """
    Serves the Cumulative OI Analysis dashboard page.
    """
    html_path = os.path.join(os.path.dirname(__file__), "cumulative_oi.html")
    if not os.path.exists(html_path):
        # Create it later or error out
        raise HTTPException(status_code=404, detail="cumulative_oi.html not found")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), media_type="text/html; charset=utf-8")

@app.get("/strike", response_class=HTMLResponse)
async def serve_strike_page():
    """
    Serves the Strike Analysis page (Total OI & OI Change).
    """
    html_path = os.path.join(os.path.dirname(__file__), "strike.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="strike.html not found")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), media_type="text/html; charset=utf-8")

@app.get("/greeks", response_class=HTMLResponse)
async def serve_greeks_page():
    """
    Serves the Greeks Exposure Analysis page.
    """
    html_path = os.path.join(os.path.dirname(__file__), "greeks.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="greeks.html not found")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), media_type="text/html; charset=utf-8")

@app.get("/strike-greeks", response_class=HTMLResponse)
async def serve_strike_greeks_page():
    """
    Serves the Strike Greeks Analysis page (Historical plots).
    """
    html_path = os.path.join(os.path.dirname(__file__), "strike_greeks.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="strike_greeks.html not found")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), media_type="text/html; charset=utf-8")

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
    with open(js_path, "r", encoding="utf-8") as f:
        return Response(content=f.read(), media_type="application/javascript")


@app.get("/gex", response_class=HTMLResponse)
async def serve_gex_page():
    """
    Serves the Net GEX Regime Analysis page.
    """
    html_path = os.path.join(os.path.dirname(__file__), "gex.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="gex.html not found")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), media_type="text/html; charset=utf-8")

@app.get("/max-pain", response_class=HTMLResponse)
async def serve_max_pain_page():
    """
    Serves the Max Pain & Volatility Smile Analysis page.
    """
    html_path = os.path.join(os.path.dirname(__file__), "max_pain.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="max_pain.html not found")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), media_type="text/html; charset=utf-8")

@app.get("/multi-strike", response_class=HTMLResponse)
async def serve_multi_strike_page():
    """
    Serves the consolidated Multi-Strike Analysis page (Price + OI).
    """
    html_path = os.path.join(os.path.dirname(__file__), "multi_strike.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="multi_strike.html not found")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), media_type="text/html; charset=utf-8")

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

@app.get("/strategies", response_class=HTMLResponse)
async def serve_strategies_page():
    """
    Serves the Strategy Command Center page.
    """
    html_path = os.path.join(os.path.dirname(__file__), "strategies.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="strategies.html not found")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), media_type="text/html; charset=utf-8")

@app.get("/option-chain", response_class=HTMLResponse)
async def serve_option_chain_page():
    """
    Serves the Option Chain dashboard page.
    """
    html_path = os.path.join(os.path.dirname(__file__), "option_chain.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="option_chain.html not found")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), media_type="text/html; charset=utf-8")

@app.get("/api/greeks-data")
async def get_greeks_data(symbol: str = Query(..., description="Symbol like NIFTY"), 
                         expiry: str = Query(..., description="Expiry Date")):
    """
    Get Greeks (Delta, Gamma) data per strike.
    Appends new data to a global cache history.
    """
    print(f"📊 [CORE] [Greeks API] Request received for {symbol} expiry {expiry}")
    try:
        instrument_key = SYMBOL_MAP.get(symbol.upper())
        if not instrument_key:
            raise HTTPException(status_code=400, detail="Invalid symbol")
            
        token = get_access_token()
        
        # 1. Fetch Option Chain
        print(f"📊 [Greeks API] Fetching option chain for {instrument_key}...")
        df = await run_in_threadpool(get_option_chain_dataframe, token, instrument_key, expiry)
        
        if df is None or df.empty:
            return {"status": "error", "data": []}
            
        # Get Spot Price
        spot_price = df['spot_price'].iloc[0] if not df.empty else 0
        
        # Use standardized helper for GEX calculation
        df = calculate_gex_for_chain(df, symbol)
        total_gex = get_net_gex(df)

        # 2. Process & Add to Cache
        snapshot_df = prepare_snapshot(df)
        timestamp = snapshot_df['timestamp'].iloc[0]
        
        # Extract relevant columns
        # We need strike, greeks, oi
        # Assuming df has: strike_price, ce_delta, pe_delta, ce_gamma, pe_gamma, ce_oi, pe_oi
        
        # Select columns if they exist
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
        if cache_key not in GREEKS_HISTORY_CACHE:
            GREEKS_HISTORY_CACHE[cache_key] = snapshot_df
        else:
            # Append new snapshot
            GREEKS_HISTORY_CACHE[cache_key] = pd.concat([GREEKS_HISTORY_CACHE[cache_key], snapshot_df], ignore_index=True)
        
        # Persistent storage (CSV)
        try:
            greeks_storage.save_snapshot(symbol, expiry, snapshot_df)
        except Exception as storage_err:
            print(f"❌ [Greeks API] Storage error: {storage_err}")
                
        print(f"✅ [Greeks API] Cache updated. Total rows for {symbol}: {len(GREEKS_HISTORY_CACHE[cache_key])}")
        
        # 3. Prepare Response (Return LATEST snapshot for the chart)
        # The user wants "plot a bar chart showing the delta or gamma for each strike"
        # We return the data from the current fetch (snapshot_df)
        
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
                "timestamp": timestamp.isoformat()
            },
            "data": snapshot_df.to_dict(orient="records")
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/gex-history")
async def get_gex_history(symbol: str = "NIFTY", expiry: str = None):
    """
    Returns time-series data for Net GEX and Spot Price.
    Used for the Net GEX regime traffic light chart.
    """
    try:
        token = auth_get_token()
        index_key = SYMBOL_MAP.get(symbol.upper())
        if not expiry:
            expiries = await run_in_threadpool(get_expiries, token, index_key)
            if not expiries: return {"status": "error", "message": "No expiries found"}
            expiry = str(expiries[0])
        else:
            # Normalize: frontend sends '2026-02-24T00:00:00', poller stores '2026-02-24 00:00:00'
            expiry = str(expiry).replace('T', ' ')
            
        cache_key = (symbol.upper(), expiry)
        df_history = GREEKS_HISTORY_CACHE.get(cache_key)
        
        if df_history is None or df_history.empty:
            return {"status": "success", "data": []}
            
        history = []
        for ts, group in df_history.groupby('timestamp'):
            history.append({
                "timestamp": ts.strftime('%Y-%m-%d %H:%M:%S'),
                "net_gex": float(group['ce_gex'].sum() + group['pe_gex'].sum()),
                "spot": float(group['spot_price'].mean())
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
async def get_pcr_data(symbol: str = Query(..., description="Symbol like NIFTY"), 
                      expiry: str = Query(..., description="Expiry Date")):
    """
    Get data for PCR by Strike Grid.
    Returns list of {strike, pcr, sentiment, ce_oi, pe_oi, call_writer_domination, put_writer_domination}
    """
    print(f"📊 [CORE] [PCR API] Request received for {symbol} expiry {expiry}")
    try:
        instrument_key = SYMBOL_MAP.get(symbol.upper())
        if not instrument_key:
            raise HTTPException(status_code=400, detail="Invalid symbol")
            
        token = get_access_token()
        
        print(f"📊 [UPSTOX] [PCR API] Fetching option chain for {instrument_key}...")
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
        
        print(f"✅ [CORE] [PCR API] Returning {len(grid_data)} rows, spot={spot_price}")
        return {"data": grid_data, "spot_price": spot_price}
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/max-pain-data")
async def get_max_pain_data(symbol: str = Query(..., description="Symbol like NIFTY"), 
                           expiry: str = Query(..., description="Expiry Date")):
    """
    Get Max Pain and Volatility Smile data.
    Returns:
    - max_pain_strike: The strike with minimum total pain
    - pain_data: Array of {strike, total_pain, ce_pain, pe_pain}
    - iv_data: Array of {strike, ce_iv, pe_iv}
    - spot_price: Current spot price
    """
    print(f"📊 [CORE] [Max Pain API] Request received for {symbol} expiry {expiry}")
    try:
        instrument_key = SYMBOL_MAP.get(symbol.upper())
        if not instrument_key:
            raise HTTPException(status_code=400, detail="Invalid symbol")
            
        token = get_access_token()
        
        print(f"📊 [Max Pain API] Fetching option chain for {instrument_key}...")
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
        
        print(f"✅ [Max Pain API] Max Pain Strike: {max_pain_result['max_pain_strike']}, IV Data Points: {len(iv_data)}")
        
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
async def websocket_endpoint(websocket: WebSocket, symbol: str):
    global streamer
    await manager.connect(websocket)
    
    if streamer is None:
        token = get_access_token()
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
    token = get_access_token()
    key = SYMBOL_MAP.get(symbol.upper())
    if not key:
        raise HTTPException(status_code=400, detail="Invalid symbol")
    
    expiries = get_expiries(token, key)
    return {"status": "success", "expiries": expiries}

@app.get("/api/option-chain")
async def fetch_option_chain(symbol: str = "NIFTY", expiry: str = None, count: int = 6):
    """
    Fetch option chain data and return analytics.
    
    Args:
        symbol: Market symbol (e.g., NIFTY).
        expiry: Expiry date.
        count: Number of strikes to return around ATM (default: 6). 
               Use a higher number (e.g., 50) for full analysis pages.
    """
    token = get_access_token()
    key = SYMBOL_MAP.get(symbol.upper())
    if not key:
        raise HTTPException(status_code=400, detail="Invalid symbol")
    
    if not expiry:
        expiries = get_expiries(token, key)
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
    expiries = get_expiries(token, key) if key else []

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
async def get_straddle_data(symbol: str = "NIFTY", expiry: str = None, strike: float = None):
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
    print(f"📊 [CORE] [Straddle API] Request for {symbol} expiry {expiry}")
    try:
        token = get_access_token()
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
        
        print(f"🎯 Target Strike: {target_strike} | CE: {ce_key} | PE: {pe_key}")
        
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
                    "change_pct": round(float(change_pct), 2)
                }
            },
            "data": chart_data
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# NOTE: /strike and /greeks routes are already defined above. These duplicates have been removed.

@app.get("/option-chain", response_class=HTMLResponse)
async def serve_option_chain_page():
    """
    Serves the Option Chain page.
    """
    html_path = os.path.join(os.path.dirname(__file__), "option_chain.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="option_chain.html not found")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), media_type="text/html; charset=utf-8")

@app.get("/api/strike-data")
async def get_strike_data(symbol: str = "NIFTY", expiry: str = None, strike: float = None):
    """
    Fetches intraday data for a specific strike's CE and PE legs.
    Returns: {ce_oi, pe_oi, ce_ltp, pe_ltp} time-series.
    """
    print(f"📈 [UPSTOX] [Strike API] Request for {symbol} {strike} {expiry}")
    try:
        token = get_access_token()
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

@app.post("/api/multi-strike-history")
async def get_multi_strike_history(legs: List[LegRequest]):
    """
    Fetches historical 1-minute data for multiple legs, aligns them on timestamp,
    and calculates the Combined Premium and Running VWAP.
    """
    if not legs:
        return {"status": "success", "data": []}

    token = get_access_token()
    
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

    # 2. Process Data — raw price sum (no direction multiplier, matches broker chart display)
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
            df[col] = df['close']   # raw price, no direction sign
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

    # Combined Premium = sum of all leg prices (raw, matches broker)
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
    combined_df['timestamp'] = combined_df['timestamp'].dt.strftime('%Y-%m-%dT%H:%M:%S')

    chart_data = combined_df[['timestamp', 'premium', 'vwap']].to_dict(orient='records')

    return {
        "status": "success",
        "data": chart_data
    }

@app.get("/api/cumulative-oi")
async def get_cumulative_oi(symbol: str = "NIFTY", expiry: str = None, strike_range: int = 4):
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
    print(f"📈 [UPSTOX] [Cumulative OI] Fetching data for {symbol} expiry {expiry}")
    try:
        token = get_access_token()
        key = SYMBOL_MAP.get(symbol.upper())
        if not key:
            raise HTTPException(status_code=400, detail="Invalid symbol")
            
        if not expiry:
            expiries = get_expiries(token, key)
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
            
        # 2. Fetch Intraday Data for all legs — throttled to avoid SSL connection flooding
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
        merged['direction'] = merged['net_chg'].apply(lambda x: "BUY 🟢" if x > 0 else "SELL 🔴")
        
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
async def get_full_chain(symbol: str, expiry: str):
    """
    Get Complete Option Chain with Build Up & Top OI.
    """
    try:
        token = await run_in_threadpool(auth_get_token)
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
    symbol: str = Query(..., description="Symbol like NIFTY"),
    expiry: str = Query(..., description="Expiry Date"),
    strikes: str = Query(..., description="Comma-separated strikes")
):
    """
    Fetches intraday OI history for multiple selected strikes (CE and PE).
    """
    print(f"📈 [UPSTOX] [Multi-Strike OI] Request: {symbol} | {expiry} | Strikes: {strikes}")
    try:
        token = get_access_token()
        underlying_key = SYMBOL_MAP.get(symbol.upper())
        if not underlying_key:
            print(f"❌ [UPSTOX] [Multi-Strike OI] Invalid symbol: {symbol}")
            raise HTTPException(status_code=400, detail="Invalid symbol")
            
        strike_list = [float(s.strip()) for s in strikes.split(",") if s.strip()]
        if not strike_list:
            raise HTTPException(status_code=400, detail="No strikes provided")

        # 1. Get Option Chain to find keys for all strikes
        print(f"🔍 [UPSTOX] [Multi-Strike OI] Fetching chain for {symbol} {expiry}...")
        df = await run_in_threadpool(get_option_chain_dataframe, token, underlying_key, expiry)
        if df is None or df.empty:
            print(f"❌ [UPSTOX] [Multi-Strike OI] No option chain found")
            raise HTTPException(status_code=404, detail="No option chain data")
            
        df_subset = df[df['strike_price'].isin(strike_list)].copy()
        if df_subset.empty:
            print(f"❌ [UPSTOX] [Multi-Strike OI] Strikes {strike_list} not found in chain")
            raise HTTPException(status_code=404, detail="Selected strikes not found in chain")
            
        # 2. Fetch Intraday data for all selected legs
        _sem = asyncio.Semaphore(5)
        async def fetch_candle(instr_key, strike, type):
            async with _sem:
                print(f"⏳ [UPSTOX] [Multi-Strike OI] Fetching {strike} {type} ({instr_key})")
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
        print(f"✅ [UPSTOX] [Multi-Strike OI] Gathered {len(results)} legs")
        
        # 3. Process and Align
        all_dfs = []
        for i, candles in enumerate(results):
            m = mapping[i]
            col_name = f"{int(m['strike'])}_{m['type']}"
            
            if not candles: 
                print(f"⚠️ [UPSTOX] [Multi-Strike OI] No data for {col_name}")
                continue
            
            df_leg = pd.DataFrame(candles)[['timestamp', 'oi']].rename(columns={'oi': col_name})
            df_leg['timestamp'] = pd.to_datetime(df_leg['timestamp'])
            all_dfs.append(df_leg)
            
        if not all_dfs:
            print(f"⚠️ [UPSTOX] [Multi-Strike OI] All legs returned empty")
            return {"status": "success", "data": [], "metadata": {"strikes": strike_list}}
            
        # Outer merge all dataframes on timestamp
        merged = all_dfs[0]
        for i in range(1, len(all_dfs)):
            merged = pd.merge(merged, all_dfs[i], on='timestamp', how='outer')
            
        # Sort and fill gaps
        merged = merged.sort_values('timestamp').ffill().fillna(0)
        merged['timestamp'] = merged['timestamp'].dt.strftime('%H:%M')
        
        print(f"📊 [UPSTOX] [Multi-Strike OI] Success. Rows: {len(merged)}")
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
        print(f"❌ [UPSTOX] [Multi-Strike OI] Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/multi-strike-price-data")
async def get_multi_strike_price_data(
    symbol: str = Query(..., description="Symbol like NIFTY"),
    expiry: str = Query(..., description="Expiry Date"),
    strikes: str = Query(..., description="Comma-separated strikes")
):
    """
    Fetches intraday Price history for multiple selected strikes (CE and PE).
    """
    print(f"📈 [UPSTOX] [Multi-Strike Price] Request: {symbol} | {expiry} | Strikes: {strikes}")
    try:
        token = get_access_token()
        underlying_key = SYMBOL_MAP.get(symbol.upper())
        if not underlying_key:
            print(f"❌ [UPSTOX] [Multi-Strike Price] Invalid symbol: {symbol}")
            raise HTTPException(status_code=400, detail="Invalid symbol")
            
        strike_list = [float(s.strip()) for s in strikes.split(",") if s.strip()]
        if not strike_list:
            raise HTTPException(status_code=400, detail="No strikes provided")

        # 1. Get Option Chain to find keys for all strikes
        print(f"🔍 [UPSTOX] [Multi-Strike Price] Fetching chain for {symbol} {expiry}...")
        df = await run_in_threadpool(get_option_chain_dataframe, token, underlying_key, expiry)
        if df is None or df.empty:
            print(f"❌ [UPSTOX] [Multi-Strike Price] No option chain found")
            raise HTTPException(status_code=404, detail="No option chain data")
            
        df_subset = df[df['strike_price'].isin(strike_list)].copy()
        if df_subset.empty:
            print(f"❌ [UPSTOX] [Multi-Strike Price] Strikes {strike_list} not found in chain")
            raise HTTPException(status_code=404, detail="Selected strikes not found in chain")
            
        # 2. Fetch Intraday data for all selected legs
        _sem = asyncio.Semaphore(5)
        async def fetch_candle(instr_key, strike, type):
            async with _sem:
                print(f"⏳ [UPSTOX] [Multi-Strike Price] Fetching {strike} {type} ({instr_key})")
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
        print(f"✅ [UPSTOX] [Multi-Strike Price] Gathered {len(results)} legs")
        
        # 3. Process and Align
        all_dfs = []
        for i, candles in enumerate(results):
            m = mapping[i]
            col_name = f"{int(m['strike'])}_{m['type']}"
            
            if not candles: 
                print(f"⚠️ [UPSTOX] [Multi-Strike Price] No data for {col_name}")
                continue
            
            df_leg = pd.DataFrame(candles)[['timestamp', 'close']].rename(columns={'close': col_name})
            df_leg['timestamp'] = pd.to_datetime(df_leg['timestamp'])
            all_dfs.append(df_leg)
            
        if not all_dfs:
            print(f"⚠️ [UPSTOX] [Multi-Strike Price] All legs returned empty")
            return {"status": "success", "data": [], "metadata": {"strikes": strike_list}}
            
        # Outer merge all dataframes on timestamp
        merged = all_dfs[0]
        for i in range(1, len(all_dfs)):
            merged = pd.merge(merged, all_dfs[i], on='timestamp', how='outer')
            
        # Sort and fill gaps
        merged = merged.sort_values('timestamp').ffill().fillna(0)
        merged['timestamp'] = merged['timestamp'].dt.strftime('%H:%M')
        
        print(f"📊 [UPSTOX] [Multi-Strike Price] Success. Rows: {len(merged)}")
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
        print(f"❌ [UPSTOX] [Multi-Strike Price] Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)

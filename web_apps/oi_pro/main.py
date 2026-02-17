import sys
import os
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional, Dict
from fastapi.responses import HTMLResponse
import uvicorn
import json
import asyncio

# Add project root to path for lib imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from lib.api.option_chain import get_expiries, get_option_chain_dataframe, calculate_pcr, calculate_volume_pcr, calculate_oi_change_pcr
from lib.utils.instrument_utils import get_option_instrument_key
from lib.api.streaming import UpstoxStreamer
from lib.api.historical import get_intraday_data_v3
from lib.core.authentication import get_access_token as auth_get_token
import pandas as pd

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

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, symbol: str):
        await websocket.accept()
        if symbol not in self.active_connections:
            self.active_connections[symbol] = []
        self.active_connections[symbol].append(websocket)

    def disconnect(self, websocket: WebSocket, symbol: str):
        if symbol in self.active_connections:
            self.active_connections[symbol].remove(websocket)

    async def broadcast(self, message: dict, symbol: str):
        if symbol in self.active_connections:
            for connection in self.active_connections[symbol]:
                try:
                    await connection.send_json(message)
                except:
                    pass

manager = ConnectionManager()
streamer = None

def on_price_update(data):
    # This runs in a separate thread from streaming.py
    instrument_key = data.get('instrument_key')
    ltp = data.get('ltp')
    if instrument_key and ltp:
        # Map instrument key back to symbol for broadcast
        symbol_map = {
            "NSE_INDEX|Nifty 50": "NIFTY",
            "NSE_INDEX|Nifty Bank": "BANKNIFTY",
            "NSE_INDEX|Nifty Fin Service": "FINNIFTY"
        }
        symbol = symbol_map.get(instrument_key)
        if symbol:
            # We need to bridge the thread to the async loop
            # But for simplicity, we can just use a global or a queue if needed.
            # However, with FastAPI and uvicorn, we usually use a background task.
            pass

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
        
        print(f"📊 [PCR API] Fetching option chain for {instrument_key}...")
        df = await run_in_threadpool(get_option_chain_dataframe, token, instrument_key, expiry)
        
        if df is None or df.empty:
            return {"data": []}
            
        # Process DataFrame for PCR Grid
        grid_data = []
        
        for _, row in df.iterrows():
            strike = row['strike_price']
            ce_oi = row.get('ce_oi') or 0
            pe_oi = row.get('pe_oi') or 0
            
            # Skip if negligible OI to avoid division by zero or noise
            if ce_oi < 500 and pe_oi < 500:
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
        
        print(f"✅ [PCR API] Returning {len(grid_data)} rows")
        return {"data": grid_data}
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# Symbol Mapping for 6 Indices
SYMBOL_MAP = {
    "NIFTY": "NSE_INDEX|Nifty 50",
    "BANKNIFTY": "NSE_INDEX|Nifty Bank",
    "FINNIFTY": "NSE_INDEX|Nifty Fin Service",
    "NIFTYIT": "NSE_INDEX|Nifty IT",
    "MIDCPNIFTY": "NSE_INDEX|NIFTY MIDCAP 100",
    "SENSEX": "BSE_INDEX|SENSEX"
}

@app.websocket("/ws/market-watch")
async def market_watch_endpoint(websocket: WebSocket):
    global streamer
    await websocket.accept()
    
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
            prices = {}
            if streamer:
                for sym, key in SYMBOL_MAP.items():
                    latest = streamer.get_latest_data(key)
                    if latest and 'ltp' in latest:
                        ltp = latest['ltp']
                        # Try to get previous close from 'cp' (close price) or 'close'
                        prev_close = latest.get('cp') or latest.get('close') or ltp
                        
                        chg = 0.0
                        if prev_close > 0:
                            chg = ((ltp - prev_close) / prev_close) * 100
                            
                        prices[sym] = {
                            "ltp": ltp,
                            "chg": chg
                        }
            
            if prices:
                await websocket.send_json({"type": "market_update", "prices": prices})
    except WebSocketDisconnect:
        pass

@app.websocket("/ws/price/{symbol}")
async def websocket_endpoint(websocket: WebSocket, symbol: str):
    global streamer
    await manager.connect(websocket, symbol.upper())
    
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
    except WebSocketDisconnect:
        manager.disconnect(websocket, symbol.upper())

@app.get("/api/expiries")
async def fetch_expiries(symbol: str = "NIFTY"):
    token = get_access_token()
    key = SYMBOL_MAP.get(symbol.upper())
    if not key:
        raise HTTPException(status_code=400, detail="Invalid symbol")
    
    expiries = get_expiries(token, key)
    return {"status": "success", "expiries": expiries}

@app.get("/api/option-chain")
async def fetch_option_chain(symbol: str = "NIFTY", expiry: str = None):
    token = get_access_token()
    key = SYMBOL_MAP.get(symbol.upper())
    if not key:
        raise HTTPException(status_code=400, detail="Invalid symbol")
    
    if not expiry:
        expiries = get_expiries(token, key)
        if not expiries:
            raise HTTPException(status_code=404, detail="No expiries found")
        expiry = expiries[0]

    df = get_option_chain_dataframe(token, key, expiry)
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

    # ATM Strike Filtering (+/- 6 strikes)
    spot = df['spot_price'].iloc[0] if not df.empty else 0
    if spot > 0:
        # Find ATM strike
        df['strike_diff'] = (df['strike_price'] - spot).abs()
        atm_idx = df['strike_diff'].idxmin()
        
        # Get range of indices
        start_idx = max(0, atm_idx - 6)
        end_idx = min(len(df) - 1, atm_idx + 6)
        
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
            
        # 2. Fetch Intraday Data for all legs in parallel
        async def fetch_candle(instr_key):
            return await run_in_threadpool(get_intraday_data_v3, token, instr_key, "minute", 1)

        tasks = []
        for _, row in df_subset.iterrows():
            tasks.append(fetch_candle(row['ce_key']))
            tasks.append(fetch_candle(row['pe_key']))
            
        # Also fetch index index data for the LTP line
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

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)

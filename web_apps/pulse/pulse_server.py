"""
pulse_server.py — News Pulse FastAPI Backend
Serves the news dashboard and auto-scrapes every 10 minutes.
"""

import os
import socket
import logging
import pandas as pd
import uvicorn

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime

# ─── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.abspath(os.path.join(BASE_DIR, "../../pulse_highlights.csv"))
HTML_PATH = os.path.join(BASE_DIR, "index.html")

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ─── App ─────────────────────────────────────────────────────────────────────
app = FastAPI(title="News Pulse")

# Import scraper
import sys
sys.path.insert(0, BASE_DIR)
from scraper import scrape_and_save

# ─── Scheduler ───────────────────────────────────────────────────────────────
scheduler = BackgroundScheduler()

@app.on_event("startup")
def start_scheduler():
    scheduler.add_job(scrape_and_save, "interval", minutes=10, id="pulse_scraper",
                      next_run_time=None)  # Don't scrape on startup; use existing CSV
    scheduler.start()
    logger.info("[SCHEDULER] Scraper job registered — every 10 minutes.")

@app.on_event("shutdown")
def stop_scheduler():
    scheduler.shutdown()

# ─── Routes ──────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def serve_index():
    with open(HTML_PATH, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/api/news")
def get_news():
    try:
        df = pd.read_csv(CSV_PATH)
        df = df.where(pd.notnull(df), None)  # Replace NaN with None
        articles = df.to_dict(orient="records")
        return JSONResponse({
            "articles": articles,
            "total": len(articles),
            "last_updated": datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"[API] Failed to read CSV: {e}")
        return JSONResponse({"articles": [], "total": 0, "error": str(e)}, status_code=500)

@app.post("/api/scrape")
def manual_scrape():
    """Manually trigger a scrape."""
    count = scrape_and_save()
    return {"scraped": count, "timestamp": datetime.now().isoformat()}

# ─── Port Discovery ───────────────────────────────────────────────────────────
def find_free_port(start=8090):
    for port in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("", port))
                return port
            except OSError:
                continue
    return start

if __name__ == "__main__":
    port = find_free_port(8090)
    print(f"\n{'='*60}")
    print(f"  📰 News Pulse Server")
    print(f"{'='*60}")
    print(f"  URL  : http://localhost:{port}")
    print(f"  CSV  : {CSV_PATH}")
    print(f"  Auto-scrape: every 10 minutes")
    print(f"{'='*60}\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

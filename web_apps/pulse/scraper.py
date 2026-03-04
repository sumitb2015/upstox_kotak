"""
scraper.py — Pulse.zerodha.com News Scraper
Scrapes the news feed and saves to pulse_highlights.csv
"""

import urllib.request
import pandas as pd
import logging
import os
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

CSV_PATH = os.path.join(os.path.dirname(__file__), "../../pulse_highlights.csv")
CSV_PATH = os.path.abspath(CSV_PATH)

TARGET_URL = "https://pulse.zerodha.com/"

def scrape_pulse() -> pd.DataFrame:
    """Fetches pulse.zerodha.com and returns a DataFrame of all articles."""
    req = urllib.request.Request(
        TARGET_URL,
        headers={"User-Agent": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}
    )
    html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8")
    soup = BeautifulSoup(html, "html.parser")

    articles = []
    items = soup.find_all("li", class_="item")

    for item in items:
        title_el = item.find("h2", class_="title")
        if title_el and title_el.find("a"):
            a_tag = title_el.find("a")
            title = a_tag.text.strip()
            link = a_tag.get("href", "")
            feed_el = item.find("span", class_="feed")
            source = feed_el.text.strip().replace("—", "").strip() if feed_el else ""
            date_el = item.find("span", class_="date")
            time_str = date_el.text.strip() if date_el else ""
            articles.append({"title": title, "link": link, "source": source, "time": time_str, "is_nested": False})

        similar_ul = item.find("ul", class_="similar")
        if similar_ul:
            for li in similar_ul.find_all("li"):
                a_tag = li.find("a", class_="title2")
                if a_tag:
                    title = a_tag.text.strip()
                    link = a_tag.get("href", "")
                    feed_el = li.find("span", class_="feed")
                    source = feed_el.text.strip().replace("—", "").strip() if feed_el else ""
                    date_el = li.find("span", class_="date")
                    time_str = date_el.text.strip() if date_el else ""
                    articles.append({"title": title, "link": link, "source": source, "time": time_str, "is_nested": True})

    return pd.DataFrame(articles)


def scrape_and_save():
    """Scrapes pulse.zerodha.com and writes the result to the CSV file."""
    try:
        logger.info(f"[SCRAPER] Starting scrape at {datetime.now().strftime('%H:%M:%S')}")
        df = scrape_pulse()
        df.to_csv(CSV_PATH, index=False)
        logger.info(f"[SCRAPER] Done. Saved {len(df)} articles to {CSV_PATH}")
        return len(df)
    except Exception as e:
        logger.error(f"[SCRAPER] Failed: {e}")
        return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    count = scrape_and_save()
    print(f"Scraped {count} articles.")

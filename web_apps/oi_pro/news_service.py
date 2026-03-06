import feedparser
import asyncio
import logging
from datetime import datetime
from time import mktime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

# --- In-Memory Cache ---
news_cache = {
    "articles": [],
    "last_updated": None
}

NEWS_SOURCES = [
    {
        "provider": "Economic Times",
        "url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"
    },
    {
        "provider": "Moneycontrol",
        "url": "https://www.moneycontrol.com/rss/latestnews.xml"
    },
    {
        "provider": "NDTV Profit",
        "url": "https://feeds.feedburner.com/ndtvprofit-latest"
    }
]

def fetch_and_parse_feeds():
    """Synchronous function to fetch and parse all RSS feeds."""
    all_articles = []
    seen_titles = set()
    
    for source in NEWS_SOURCES:
        try:
            feed = feedparser.parse(source["url"])
            if feed.bozo:
                logger.warning(f"Malformed feed detected for {source['provider']}. Exception: {feed.bozo_exception}")

            for entry in feed.entries:
                title = entry.title.strip()
                if title in seen_titles:
                    continue  # deduplicate by exact title
                
                seen_titles.add(title)
                
                # Parse date if available
                pub_date = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    pub_date = datetime.fromtimestamp(mktime(entry.published_parsed)).isoformat()
                
                all_articles.append({
                    "id": entry.get('id', entry.get('link', '')),
                    "title": title,
                    "summary": entry.get('summary', '').strip(), # can contain HTML
                    "source": source["provider"],
                    "url": entry.get('link', ''),
                    "published_at": pub_date,
                    "category": source["provider"] # simple grouping for now
                })
        except Exception as e:
            logger.error(f"Error fetching RSS for {source['provider']}: {e}")
            
    # Sort newest first inside memory
    all_articles.sort(key=lambda x: x['published_at'] or "", reverse=True)
    return all_articles

async def refresh_news_cache():
    """Async wrapper wrapper to run blocking IO and update the cache."""
    try:
        logger.info("Refreshing market news feeds...")
        articles = await asyncio.to_thread(fetch_and_parse_feeds)
        news_cache["articles"] = articles
        news_cache["last_updated"] = datetime.now().isoformat()
        logger.info(f"Loaded {len(articles)} market news articles into cache.")
    except Exception as e:
        logger.error(f"Failed to refresh news cache: {e}")

def start_news_scheduler():
    """Starts the apscheduler for pulling news every 15 mins."""
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        refresh_news_cache, 
        trigger=IntervalTrigger(minutes=15),
        id='news_fetcher_job',
        replace_existing=True,
        # Start immediately
        next_run_time=datetime.now()
    )
    scheduler.start()
    return scheduler

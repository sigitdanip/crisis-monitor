"""
News, health, and political data fetchers.
Sources: NewsAPI, WHO RSS (hantavirus), ACLED conflict data, RCP polls scrape.
Each sub-source has graceful degradation — partial returns on failure.
"""
import logging
import os
import re
from typing import Any

import feedparser
import httpx

logger = logging.getLogger(__name__)


# ---- NewsAPI ----

def _fetch_newsapi_headlines() -> list[dict[str, Any]]:
    """Fetch crisis-relevant headlines via NewsAPI."""
    api_key = os.environ.get("NEWS_API_KEY")
    if not api_key:
        logger.info("NEWS_API_KEY not set — skipping news headlines")
        return []

    queries = [
        "NATO", "energy crisis", "food prices", "credit spreads",
        "China economy", "EM currency", "protests", "hantavirus",
    ]
    headlines: list[dict[str, Any]] = []
    try:
        with httpx.Client(timeout=15.0) as client:
            for q in queries:
                try:
                    r = client.get(
                        "https://newsapi.org/v2/everything",
                        params={
                            "q": q,
                            "apiKey": api_key,
                            "pageSize": 3,
                            "sortBy": "publishedAt",
                            "language": "en",
                        },
                    )
                    r.raise_for_status()
                    articles = r.json().get("articles", [])
                    for art in articles:
                        headlines.append({
                            "name": art.get("title", "Untitled"),
                            "category": "News",
                            "value": 1,  # presence indicator
                            "unit": "headline",
                            "status": "normal",
                            "trigger_level": "n/a",
                            "source": art.get("source", {}).get("name", ""),
                            "url": art.get("url", ""),
                        })
                except Exception:
                    logger.warning("NewsAPI query '%s' failed", q)
    except Exception:
        logger.exception("NewsAPI fetch failed")
    logger.info("NewsAPI: %d headlines", len(headlines))
    return headlines


# ---- WHO RSS ----

WHO_RSS_FEEDS = [
    "https://www.who.int/rss-feeds/news-english.xml",
    "https://www.who.int/feeds/entity/don/en/rss.xml",
]


def _fetch_who_rss() -> list[dict[str, Any]]:
    """Fetch WHO RSS feeds for disease outbreak news."""
    results: list[dict[str, Any]] = []
    for feed_url in WHO_RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:10]:
                title = entry.get("title", "")
                if any(kw in title.lower() for kw in ["hanta", "virus", "outbreak", "pandemic"]):
                    results.append({
                        "name": title,
                        "category": "Health",
                        "value": 1,
                        "unit": "alert",
                        "status": "normal",
                        "trigger_level": "n/a",
                        "source": "WHO",
                        "url": entry.get("link", ""),
                    })
        except Exception:
            logger.warning("WHO RSS fetch failed for %s", feed_url)
    logger.info("WHO RSS: %d health alerts", len(results))
    return results


# ---- ACLED ----

def _fetch_acled_protests() -> dict[str, Any] | None:
    """Fetch ACLED protest event count."""
    api_key = os.environ.get("ACLED_API_KEY")
    email = os.environ.get("ACLED_EMAIL")
    if not api_key or not email:
        logger.info("ACLED_API_KEY/EMAIL not set — skipping protest data")
        return None
    try:
        with httpx.Client(timeout=20.0) as client:
            r = client.get(
                "https://api.acleddata.com/acled/read",
                params={
                    "key": api_key,
                    "email": email,
                    "event_type": "Protests",
                    "limit": 100,
                    "event_date": "2025-06-01|2025-06-30",
                    "event_date_where": "BETWEEN",
                },
            )
            r.raise_for_status()
            data = r.json()
            count = data.get("count", len(data.get("data", [])))
            return {
                "name": "ACLED Protest Events",
                "category": "Political",
                "value": count,
                "unit": "events/month",
                "status": "normal",
                "trigger_level": "3+ countries with major protests",
            }
    except Exception:
        logger.exception("ACLED fetch failed")
        return None


# ---- RCP Polls ----

def _fetch_rcp_polls() -> dict[str, Any] | None:
    """Scrape RealClearPolitics generic ballot or approval polling average."""
    # ponytail: HTML scrape with narrow regex; fragile but free.
    # If RCP changes layout, falls back to None (graceful degradation).
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            r = client.get(
                "https://www.realclearpolling.com/polls/state-of-the-union/trump-approval",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            r.raise_for_status()
            # Look for approval average pattern: "XX.X%"
            # ponytail: fragile regex — RCP markup changes; no API available
            matches = re.findall(r'(\d+\.\d+)%', r.text)
            if len(matches) >= 2:
                approve = float(matches[0])
                disapprove = float(matches[1])
                return {
                    "name": "Trump Approval Rating",
                    "category": "Political",
                    "value": approve,
                    "unit": "% approve",
                    "status": "normal",
                    "trigger_level": "<40%",
                    "metadata": f"disapprove={disapprove}%",
                }
            return None
    except Exception:
        logger.exception("RCP scrape failed")
        return None


def fetch_all_news() -> list[dict[str, Any]]:
    """Fetch all news, health, and political indicators. Returns partial on failure."""
    results: list[dict[str, Any]] = []

    # NewsAPI headlines
    results.extend(_fetch_newsapi_headlines())

    # WHO RSS
    results.extend(_fetch_who_rss())

    # ACLED protests
    acled = _fetch_acled_protests()
    if acled:
        results.append(acled)

    # RCP polls
    rcp = _fetch_rcp_polls()
    if rcp:
        results.append(rcp)

    logger.info("Fetched %d news/political indicators", len(results))
    return results


def _demo() -> None:
    results = fetch_all_news()
    for r in results[:5]:
        print(f"  {r['name'][:80]}")
    print(f"  ... ({len(results)} total)")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    _demo()

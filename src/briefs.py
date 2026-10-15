from datetime import datetime, timedelta
from typing import Dict, Optional

import feedparser
from loguru import logger

from src.sources import _get, DEFAULT_USER_AGENT

# A "brief" is a daily newsletter that already summarizes the day's coverage.
# It's used as reference material when an article's own page can't be read.
#
#   type: url  -> `url` is a template, e.g. "https://weirdhat.net/brief/{date:%Y%m%d}.html"
#   type: rss  -> find the entry in feed `url` whose title contains `title_contains`
#                 (a template, e.g. "슬로우레터 {date.month}월{date.day}일")

MAX_BRIEF_CHARS = 40000


def _extract(url: str, user_agent: str) -> Optional[str]:
    import trafilatura

    response = _get(url, user_agent, missing_ok=True)
    if response is None:
        return None
    text = trafilatura.extract(response.content, url=url, include_comments=False)
    return text[:MAX_BRIEF_CHARS] if text else None


def _find_url(brief_conf: Dict, date: datetime, user_agent: str) -> Optional[str]:
    if brief_conf["type"] == "url":
        return brief_conf["url"].format(date=date)

    if brief_conf["type"] == "rss":
        response = _get(brief_conf["url"], user_agent)
        if response is None:
            return None
        needle = brief_conf["title_contains"].format(date=date)
        for entry in feedparser.parse(response.content).entries:
            if needle in entry.get("title", ""):
                return entry.get("link")
        return None

    logger.error(f"Unknown brief type: {brief_conf['type']}")
    return None


def fetch_brief(brief_id: str, brief_conf: Dict, today: datetime,
                user_agent: str = DEFAULT_USER_AGENT) -> Optional[str]:
    """Returns the text of today's brief, falling back to yesterday's."""
    for date in (today, today - timedelta(days=1)):
        url = _find_url(brief_conf, date, user_agent)
        if not url:
            continue
        text = _extract(url, user_agent)
        if text:
            logger.info(f"Loaded brief '{brief_id}' for {date:%Y-%m-%d} ({len(text)} chars): {url}")
            return text
    logger.warning(f"No brief found for '{brief_id}' (today or yesterday).")
    return None

import calendar
import html
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from urllib.parse import urljoin

import feedparser
import requests
from bs4 import BeautifulSoup
from loguru import logger

DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; web-fetch-notify-bot/1.0; personal news digest)"
KST = timezone(timedelta(hours=9))

# --- Helpers ---


def _get(url: str, user_agent: str, missing_ok: bool = False) -> Optional[requests.Response]:
    """GETs a URL, returning None on failure. With `missing_ok`, a 404 is logged as a warning."""
    try:
        response = requests.get(url, headers={"User-Agent": user_agent}, timeout=15)
        response.raise_for_status()
        return response
    except requests.exceptions.HTTPError as e:
        if missing_ok and e.response is not None and e.response.status_code == 404:
            logger.warning(f"Not found (yet): {url}")
        else:
            logger.error(f"Request failed for {url}: {e}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed for {url}: {e}")
    return None


def _unescape_all(text: str) -> str:
    """Unescapes repeatedly to undo double-escaped feeds (e.g. '&amp;amp;')."""
    while True:
        unescaped = html.unescape(text)
        if unescaped == text:
            return text
        text = unescaped


def _clean_text(text: str, limit: int = 300) -> str:
    """Strips HTML tags/entities and collapses whitespace."""
    if not text:
        return ""
    text = _unescape_all(BeautifulSoup(text, "html.parser").get_text(" "))
    # Some feeds (Pressian) emit entities with the leading '&' missing, e.g. 'hellip;'.
    text = re.sub(r"(?<!&)(hellip|middot|lsquo|rsquo|ldquo|rdquo|quot);",
                  lambda m: html.unescape(f"&{m.group(1)};"), text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _normalize_link(link: str) -> str:
    """Removes tracking parameters so the same article always maps to the same URL."""
    link = _unescape_all(link.strip())
    link = re.sub(r"[?&](utm_[a-z]+|ref)=[^&#]*", "", link)
    if "?" not in link and "&" in link:
        link = link.split("&", 1)[0]
    return link


def _entry_published(entry) -> Optional[str]:
    """Returns the entry's publication time as an ISO string (UTC), or None."""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc).isoformat()

    # Some feeds (e.g. Pressian's dc:date) use "YYYY-MM-DD HH:MM:SS" without a timezone,
    # which feedparser can't parse. Treat it as KST.
    raw = entry.get("published") or entry.get("updated") or entry.get("dc_date")
    if raw:
        try:
            dt = datetime.strptime(raw.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
            return dt.astimezone(timezone.utc).isoformat()
        except ValueError:
            logger.trace(f"Could not parse date '{raw}'")
    return None


# --- Collectors ---


def collect_rss(source_id: str, source_conf: Dict, user_agent: str) -> List[Dict]:
    """Collects articles from an RSS/Atom feed."""
    response = _get(source_conf["url"], user_agent)
    if response is None:
        return []

    feed = feedparser.parse(response.content)
    articles = []
    for entry in feed.entries:
        link = entry.get("link")
        title = _clean_text(entry.get("title", ""), limit=500)
        if not link or not title:
            continue
        articles.append({
            "link": _normalize_link(link),
            "source_id": source_id,
            "title": title,
            "description": _clean_text(entry.get("summary", "")),
            "published_at": _entry_published(entry),
        })
    return articles


def collect_html_list(source_id: str, source_conf: Dict, user_agent: str) -> List[Dict]:
    """
    Collects articles from list pages by matching anchors whose href contains `link_pattern`.
    The title is taken from the anchor's `title` attribute, a `.title` child, or its text;
    the description from a `.content` child if present.
    """
    pattern = source_conf["link_pattern"]
    articles: Dict[str, Dict] = {}

    for page_url in source_conf["urls"]:
        response = _get(page_url, user_agent)
        if response is None:
            continue
        soup = BeautifulSoup(response.text, "html.parser")

        for a in soup.find_all("a", href=True):
            if pattern not in a["href"]:
                continue
            link = _normalize_link(urljoin(page_url, a["href"]))

            title_el = a.select_one(".title")
            title = a.get("title") or (title_el.get_text(" ") if title_el else a.get_text(" "))
            title = _clean_text(title, limit=500)
            content_el = a.select_one(".content")
            description = _clean_text(content_el.get_text(" ")) if content_el else ""

            # The same article is often linked several times (thumbnail + headline); keep the richest.
            existing = articles.get(link)
            if existing and len(existing["title"]) >= len(title):
                continue
            if len(title) < 5:
                continue
            articles[link] = {
                "link": link,
                "source_id": source_id,
                "title": title,
                "description": description,
                "published_at": None,
            }
    return list(articles.values())


COLLECTORS = {
    "rss": collect_rss,
    "html_list": collect_html_list,
}


def collect_source(source_id: str, source_conf: Dict, user_agent: str = DEFAULT_USER_AGENT) -> List[Dict]:
    """Collects articles for one configured source."""
    collector = COLLECTORS.get(source_conf.get("type"))
    if collector is None:
        logger.error(f"Unknown source type for '{source_id}': {source_conf.get('type')}")
        return []
    try:
        articles = collector(source_id, source_conf, user_agent)
        logger.info(f"Collected {len(articles)} articles from {source_conf.get('name', source_id)}")
        return articles
    except Exception as e:
        logger.error(f"Unexpected error while collecting '{source_id}': {e}")
        return []


def fetch_article_body(url: str, user_agent: str = DEFAULT_USER_AGENT, max_chars: int = 4000) -> Optional[str]:
    """Fetches an article page and extracts the main text."""
    import trafilatura

    response = _get(url, user_agent)
    if response is None:
        return None
    text = trafilatura.extract(response.text, url=url, include_comments=False, include_tables=False)
    if not text:
        logger.warning(f"Could not extract article body from {url}")
        return None
    return text[:max_chars]

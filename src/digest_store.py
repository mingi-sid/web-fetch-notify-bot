import sqlite3
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List
from loguru import logger

# Kept separate from sent_news.db so the digest and keyword alerts don't interfere.
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'digest.db')


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def setup_database():
    """Ensures the digest tables exist."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with _connect() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS articles (
                link TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                published_at TEXT,
                first_seen_at TEXT NOT NULL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS digest_sent (
                digest_name TEXT NOT NULL,
                link TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                PRIMARY KEY (digest_name, link)
            )
        ''')
    logger.info(f"Digest database setup complete. Path: {DB_PATH}")


def save_articles(articles: List[Dict]) -> int:
    """Inserts newly seen articles; returns how many were new."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        before = conn.total_changes
        conn.executemany(
            '''INSERT OR IGNORE INTO articles (link, source_id, title, description, published_at, first_seen_at)
               VALUES (:link, :source_id, :title, :description, :published_at, :first_seen_at)''',
            [{**a, "first_seen_at": now} for a in articles],
        )
        return conn.total_changes - before


def get_candidates(digest_name: str, source_ids: List[str], hours: int = 24) -> List[Dict]:
    """
    Returns articles from the given sources first seen within the last `hours`
    that haven't been sent in this digest yet. Articles whose publication date is
    known and older than the window (plus some slack) are skipped.
    """
    now = datetime.now(timezone.utc)
    seen_since = (now - timedelta(hours=hours)).isoformat()
    published_since = (now - timedelta(hours=hours + 12)).isoformat()
    placeholders = ",".join("?" * len(source_ids))
    with _connect() as conn:
        rows = conn.execute(
            f'''SELECT * FROM articles a
                WHERE a.source_id IN ({placeholders})
                  AND a.first_seen_at >= ?
                  AND (a.published_at IS NULL OR a.published_at >= ?)
                  AND NOT EXISTS (SELECT 1 FROM digest_sent s
                                  WHERE s.digest_name = ? AND s.link = a.link)
                ORDER BY a.first_seen_at''',
            (*source_ids, seen_since, published_since, digest_name),
        ).fetchall()
    return [dict(row) for row in rows]


def mark_sent(digest_name: str, links: List[str]):
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO digest_sent (digest_name, link, sent_at) VALUES (?, ?, ?)",
            [(digest_name, link, now) for link in links],
        )


def prune(days: int = 14):
    """Deletes collected articles older than `days` to keep the DB small."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with _connect() as conn:
        deleted = conn.execute("DELETE FROM articles WHERE first_seen_at < ?", (cutoff,)).rowcount
        conn.execute("DELETE FROM digest_sent WHERE sent_at < ?", (cutoff,))
    if deleted:
        logger.info(f"Pruned {deleted} old articles from digest DB.")

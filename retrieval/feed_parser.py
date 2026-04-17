"""RSS feed parser for ilpost.it articles."""

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

import httpx

DB_PATH = Path(__file__).parent / "articles.db"
ARTICLE_URL_RE = re.compile(r"https?://[^/]+/\d{4}/\d{2}/\d{2}/[^/]+/?$")


@dataclass
class Article:
    title: str
    url: str
    pub_date: str  # ISO 8601
    categories: list[str]
    summary: str | None


# --- HTML stripping ---

class _HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_text(self) -> str:
        return "".join(self._parts).strip()


def _strip_html(text: str) -> str | None:
    stripper = _HTMLStripper()
    stripper.feed(text)
    result = stripper.get_text()
    return result if result else None


# --- Parsing ---

def _parse_pub_date(raw: str) -> str:
    """Convert RFC 2822 date string to ISO 8601."""
    try:
        dt: datetime = parsedate_to_datetime(raw)
        return dt.isoformat()
    except Exception:
        return raw  # fallback: store as-is


def _parse_item(item: ElementTree.Element) -> Article | None:
    url = (item.findtext("link") or "").strip()
    if not ARTICLE_URL_RE.match(url):
        return None

    title = (item.findtext("title") or "").strip()
    pub_date = _parse_pub_date((item.findtext("pubDate") or "").strip())
    categories = [c.text.strip() for c in item.findall("category") if c.text]
    raw_summary = (item.findtext("description") or "").strip()
    summary = _strip_html(raw_summary) if raw_summary else None

    return Article(title=title, url=url, pub_date=pub_date, categories=categories, summary=summary)


# --- DB ---

def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            url       TEXT PRIMARY KEY,
            title     TEXT NOT NULL,
            pub_date  TEXT,
            categories TEXT,
            summary   TEXT
        )
    """)
    conn.commit()


def _save_articles(articles: list[Article], conn: sqlite3.Connection) -> int:
    """Insert articles, skip duplicates. Returns count of newly inserted rows."""
    inserted = 0
    for a in articles:
        try:
            conn.execute(
                "INSERT INTO articles (url, title, pub_date, categories, summary) VALUES (?, ?, ?, ?, ?)",
                (a.url, a.title, a.pub_date, ",".join(a.categories), a.summary),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            pass  # already exists
    conn.commit()
    return inserted


# --- Public API ---

def fetch_feed(url: str) -> list[Article]:
    """Fetch and parse a single ilpost.it RSS feed URL. Saves new articles to DB."""
    response = httpx.get(url, follow_redirects=True, timeout=10)
    response.raise_for_status()

    root = ElementTree.fromstring(response.content.strip())
    channel = root.find("channel")
    if channel is None:
        return []

    articles: list[Article] = []
    for item in channel.findall("item"):
        article = _parse_item(item)
        if article:
            articles.append(article)

    with sqlite3.connect(DB_PATH) as conn:
        _init_db(conn)
        inserted = _save_articles(articles, conn)

    print(f"[fetch_feed] {url}: {len(articles)} articles parsed, {inserted} new saved to DB")
    return articles


def fetch_all(urls: list[str]) -> list[Article]:
    """Fetch and parse multiple RSS feed URLs. Returns combined list of all articles."""
    all_articles: list[Article] = []
    for url in urls:
        all_articles.extend(fetch_feed(url))
    return all_articles

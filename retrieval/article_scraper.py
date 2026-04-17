"""Scraper for full article text from ilpost.it pages."""

import json
import re
import sqlite3
from html.parser import HTMLParser
from pathlib import Path

import httpx

DB_PATH = Path(__file__).parent / "articles.db"
NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)


class _HTMLStripper(HTMLParser):
    _BLOCK = {'p', 'div', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'blockquote', 'article', 'section'}

    def __init__(self):
        super().__init__()
        self._buf = ''

    def _ensure_newline(self, tag: str) -> None:
        if tag.lower() in self._BLOCK and self._buf and not self._buf.endswith('\n'):
            self._buf += '\n'

    def handle_starttag(self, tag: str, attrs) -> None:
        self._ensure_newline(tag)

    def handle_endtag(self, tag: str) -> None:
        self._ensure_newline(tag)

    def handle_data(self, data: str) -> None:
        if data:
            # Insert space between adjacent inline elements to avoid concatenation artifacts
            if self._buf and not self._buf[-1].isspace() and not data[0].isspace():
                self._buf += ' '
            self._buf += data

    def get_text(self) -> str:
        text = re.sub(r' +', ' ', self._buf)        # collapse multiple spaces
        text = re.sub(r'\n{3,}', '\n\n', text)      # max two consecutive newlines
        return text.strip()


def _strip_html(html: str) -> str:
    s = _HTMLStripper()
    s.feed(html)
    text = s.get_text()
    # Remove "Caricamento player" label injected by embedded audio/video players
    text = re.sub(r"(?i)^caricamento player\s*\n?", "", text)
    return text.strip()


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS article_text (
            url       TEXT PRIMARY KEY REFERENCES articles(url),
            raw_text  TEXT NOT NULL
        )
    """)
    conn.commit()


def scrape_article(url: str) -> str | None:
    """Fetch a single article URL and return its plain text, or None on failure."""
    response = httpx.get(url, follow_redirects=True, timeout=10)
    response.raise_for_status()

    match = NEXT_DATA_RE.search(response.text)
    if not match:
        print(f"  [warn] __NEXT_DATA__ not found: {url}")
        return None

    data = json.loads(match.group(1))
    try:
        content_html = data["props"]["pageProps"]["data"]["data"]["main"]["data"]["content_html"]
    except (KeyError, TypeError):
        print(f"  [warn] content_html path missing: {url}")
        return None

    if not content_html:
        print(f"  [warn] empty content_html: {url}")
        return None

    return _strip_html(content_html)


def scrape_all() -> None:
    """Scrape full text for all articles in the DB that don't yet have text."""
    with sqlite3.connect(DB_PATH) as conn:
        _init_db(conn)

        urls = [
            row[0]
            for row in conn.execute("""
                SELECT a.url FROM articles a
                LEFT JOIN article_text t ON a.url = t.url
                WHERE t.url IS NULL
            """).fetchall()
        ]

    print(f"Articles to scrape: {len(urls)}")

    results: list[tuple[str, str]] = []
    for i, url in enumerate(urls, 1):
        print(f"[{i}/{len(urls)}] {url}")
        text = scrape_article(url)
        if text:
            results.append((url, text))

    with sqlite3.connect(DB_PATH) as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO article_text (url, raw_text) VALUES (?, ?)",
            results,
        )
        conn.commit()

    print(f"\nDone. {len(results)}/{len(urls)} articles saved.")

"""Scrapes article metadata from ilpost.it section pages (e.g. /politica/, /economia/)."""

import json
import re
import sqlite3
from pathlib import Path

import httpx

from feed_parser import Article, _init_db, _save_articles

DB_PATH = Path(__file__).parent / "articles.db"
NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)

SECTIONS = [
    "politica",
    "economia",
    "mondo",
    "italia",
    "scienza",
    "tecnologia",
    "cultura",
    "sport",
]


def _fetch_page(section: str, page: int) -> tuple[list[Article], int]:
    """Fetch one section page. Returns (articles, total_pages)."""
    url = f"https://www.ilpost.it/{section}/page/{page}/" if page > 1 else f"https://www.ilpost.it/{section}/"
    response = httpx.get(url, follow_redirects=True, timeout=10)
    response.raise_for_status()

    match = NEXT_DATA_RE.search(response.text)
    if not match:
        return [], 0

    data = json.loads(match.group(1))
    try:
        main = data["props"]["pageProps"]["data"]["data"]["main"]
    except (KeyError, TypeError):
        return [], 0

    head = main.get("head", {})
    total_items = head.get("total", 0)
    hits_per_page = head.get("hits", 20)
    total_pages = (total_items + hits_per_page - 1) // hits_per_page

    articles: list[Article] = []
    for item in main.get("data", []):
        link = item.get("link", "")
        if not re.match(r"https?://[^/]+/\d{4}/\d{2}/\d{2}/[^/]+/?$", link):
            continue
        title = item.get("title", "").strip()
        summary = (item.get("titolo2") or "").strip() or None
        pub_date = item.get("date", "") or item.get("modified", "") or ""
        articles.append(Article(
            title=title,
            url=link,
            pub_date=pub_date,
            categories=[section],
            summary=summary,
        ))

    return articles, total_pages


def fetch_section(section: str, max_pages: int = 10) -> int:
    """Fetch up to max_pages pages of a section. Returns total new articles saved."""
    print(f"\n[{section}] fetching up to {max_pages} pages...")
    total_new = 0

    with sqlite3.connect(DB_PATH) as conn:
        _init_db(conn)

        for page in range(1, max_pages + 1):
            try:
                articles, total_pages = _fetch_page(section, page)
            except httpx.HTTPError as e:
                print(f"  [warn] page {page} failed: {e}")
                break

            if not articles:
                break

            new = _save_articles(articles, conn)
            total_new += new
            print(f"  page {page}/{min(max_pages, total_pages)}: {len(articles)} found, {new} new")

            if page >= total_pages:
                break

    print(f"[{section}] done — {total_new} new articles saved")
    return total_new


def fetch_all_sections(max_pages: int = 10) -> None:
    """Fetch all configured sections."""
    grand_total = 0
    for section in SECTIONS:
        grand_total += fetch_section(section, max_pages=max_pages)
    print(f"\nTotal new articles across all sections: {grand_total}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch articles from ilpost.it section pages")
    parser.add_argument("--sections", nargs="+", default=SECTIONS, help="Sections to fetch")
    parser.add_argument("--max-pages", type=int, default=10, help="Max pages per section")
    args = parser.parse_args()

    grand_total = 0
    for section in args.sections:
        grand_total += fetch_section(section, max_pages=args.max_pages)
    print(f"\nTotal new articles: {grand_total}")

# Building the article corpus

Technical notes on the retrieval pipeline in `retrieval/`: fetch → scrape → chunk → embed. For the high-level architecture and quick "how to update the corpus" commands, see the root [README](../README.md).

## Step 1a — RSS feed parser (`retrieval/feed_parser.py`)

Fetches articles from ilpost.it RSS feeds and stores metadata in SQLite.

- Fetches one or more RSS feed URLs
- Parses XML and extracts: title, url, pub_date, categories, summary
- `pub_date`: parsed from RFC 2822, stored as ISO 8601
- `categories`: standard `<category>` tags with CDATA, stored as comma-separated string
- `summary`: from `<description>`, HTML-stripped; `None` if empty
- Filters out non-articles — keeps only URLs matching `/YYYY/MM/DD/slug/`
- Deduplicates by URL (SQLite PRIMARY KEY on `url`)
- Public API: `fetch_feed(url)` / `fetch_all(urls)`
- DB table: `articles` (url, title, pub_date, categories, summary)

## Step 1b — Section page parser (`retrieval/section_parser.py`)

Fetches article metadata by scraping ilpost.it section pages (e.g. `/politica/`, `/economia/`).

- Parses `__NEXT_DATA__` JSON from section pages — same pattern as the article scraper
- 20 articles per page; each section has hundreds of pages (e.g. `politica` has 342)
- Deduplicates by URL (same SQLite PRIMARY KEY as feed_parser)
- CLI: `python section_parser.py --sections politica economia --max-pages 20`
- Public API: `fetch_section(section, max_pages)` / `fetch_all_sections(max_pages)`

## Step 2 — Article scraper (`retrieval/article_scraper.py`)

Downloads full article text for each URL in the DB.

- ilpost.it is a Next.js app — article content is embedded in `__NEXT_DATA__` JSON in the page HTML
- Extracts `props.pageProps.data.data.main.data.content_html` from the JSON blob
- Strips HTML tags using stdlib `html.parser`
- Strips the "Caricamento player" label injected by embedded audio/video players
- Skips articles already present in `article_text` (idempotent)
- Public API: `scrape_article(url)` / `scrape_all()`
- DB table: `article_text` (url, raw_text) — separate from `articles` to keep metadata queries lean

## Step 3 — Chunker (`retrieval/chunker.py`)

Splits each article's raw text into overlapping token chunks.

- Tokenizer: `tiktoken` with `cl100k_base` (same encoding as Voyage AI / OpenAI embedding models)
- Target: 500 tokens per chunk, 50-token overlap carried forward between chunks
- Splits on paragraph boundaries (`\n`); falls back to raw token slicing for single paragraphs > 500 tokens
- Skips articles already chunked (idempotent)
- Public API: `chunk_text(url, text)` / `chunk_all()`
- DB table: `chunks` (id, url, chunk_index, text, token_count)

## Step 4 — Embedder (`retrieval/embedder.py`)

Generates vector embeddings for each chunk and stores them in SQLite.

- Model: `voyage-3-lite` (Voyage AI) — free tier, Italian-capable
- API key from root `.env` (`VOYAGE_API_KEY`)
- Embeddings stored as JSON-serialized float arrays in SQLite (sufficient for prototype scale)
- Similarity search: cosine similarity computed in Python with `numpy` (no vector DB needed at prototype scale — see the README for how to swap in a real one)
- Skips chunks already embedded (idempotent)
- Public API: `embed_all()` / `retrieve(query, top_k=6)`
- DB table: `embeddings` (chunk_id, vector)
- `retrieve()` returns a ranked list of chunks with text + article metadata (title, url, pub_date, categories)

## Known issues / future improvements

- **No conversation persistence**: chat history lives in memory, lost on disconnect — no sidebar, no session reload

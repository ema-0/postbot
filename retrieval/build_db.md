I'm building a RAG (Retrieval-Augmented Generation) chat that answers questions about Italian politics and current affairs using exclusively articles from ilpost.it as the source of truth.

---

## Done

### Step 1 — RSS feed parser (`retrieval/feed_parser.py`)

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

### Step 2 — Article scraper (`retrieval/article_scraper.py`)

Downloads full article text for each URL in the DB.

- ilpost.it is a Next.js app — article content is embedded in `__NEXT_DATA__` JSON in the page HTML
- Extracts `props.pageProps.data.data.main.data.content_html` from the JSON blob
- Strips HTML tags using stdlib `html.parser`
- Strips "Caricamento player" label injected by embedded audio/video players
- Skips articles already present in `article_text` (idempotent)
- Public API: `scrape_article(url)` / `scrape_all()`
- DB table: `article_text` (url, raw_text) — separate from `articles` to keep metadata queries lean

> ⚠️ **Known issue:** adjacent HTML elements (e.g. links followed by text) are sometimes concatenated without a space, producing artifacts like `"Sardegnaha approvato"`. Fix: in `_HTMLStripper.handle_data`, insert a space between data segments, or strip/reconstruct from the HTML more carefully.

### Step 3 — Chunker (`retrieval/chunker.py`)

Splits each article's raw text into overlapping token chunks.

- Tokenizer: `tiktoken` with `cl100k_base` (same encoding as Voyage AI / OpenAI embedding models)
- Target: 500 tokens per chunk, 50-token overlap carried forward between chunks
- Splits on paragraph boundaries (`\n`); falls back to raw token slicing for single paragraphs > 500 tokens
- Skips articles already chunked (idempotent)
- Public API: `chunk_text(url, text)` / `chunk_all()`
- DB table: `chunks` (id, url, chunk_index, text, token_count)
- Result: 80 chunks from 19 articles, avg 414 tokens, all in 100–500 range

### Step 4 — Embedder (`retrieval/embedder.py`)

Generates vector embeddings for each chunk and stores them in SQLite.

- Model: `voyage-3-lite` (Voyage AI) — free tier, Italian-capable
- API key from root `.env`
- Embeddings stored as JSON-serialized float arrays in SQLite (sufficient for prototype scale)
- Similarity search: cosine similarity computed in Python with `numpy` (no vector DB needed at 80 chunks)
- Skips chunks already embedded (idempotent)
- Public API: `embed_all()` / `retrieve(query, top_k=6)`
- DB table: `embeddings` (chunk_id, vector)
- `retrieve()` returns ranked list of chunks with text + article metadata (title, url, pub_date, categories)

### Step 5 — RAG MCP server (`servers/rag/`)

Exposes retrieval as an MCP tool over HTTP+SSE.

- FastMCP server on port 8001
- Exposes one tool: `search_articles(query, top_k=6)`
- Tool description and parameter schema auto-generated from type hints and docstring by FastMCP
- Cherry-picks `embedder.py` + `articles.db` from `retrieval/` at Docker build time
- See `servers/chat/agentic_loop.md` for the MCP protocol details

### Step 6 — Chat server + agentic loop (`servers/chat/`)

FastAPI WebSocket server with LLM-driven retrieval via Pattern B agentic loop.

- WebSocket endpoint on port 8000 — connection stays open for the whole conversation
- MCP session to RAG server is persistent per WebSocket connection (opened once, reused across turns)
- Tools discovered dynamically from MCP server at session start via `list_tools()`
- Agentic loop: LLM decides when to call `search_articles` and with what query; loop runs until LLM produces text
- Streaming: tool call fragments accumulated across stream chunks; final text answer streamed live to the user
- LLM: GPT-4o-mini via OpenRouter
- System prompt instructs: answer only from retrieved articles, cite sources, don't invent facts
- Citations in the answer are delegated to the LLM (it knows what it used)
- Max tool iterations: 5 (safety limit)

### Step 7 — CLI client (`client.py`)

Simple interactive WebSocket client for testing.

- Connects to `ws://localhost:8000/chat`
- Streams tokens to stdout as they arrive
- Conversation history maintained server-side

### Step 8 — Frontend (`client/`)

Next.js chat UI for demo and potential POC handoff.

- Chat bubbles with streaming tokens rendered live
- Blinking cursor during streaming
- Sources section below each assistant message — parsed from the LLM "Fonti:" block, rendered as clickable links
- Il Post branding (red `#c60000`, editorial style)
- Connection status indicator (green/red dot)
- WebSocket URL configurable via `NEXT_PUBLIC_WS_URL` env var (`.env.local` for local, env var for deployment)
- Deployable to Vercel with zero config

---

## Deployment

### Frontend (`client/`) → Vercel ✓
- Framework preset: Next.js, root directory: `client/`
- Env var: `NEXT_PUBLIC_WS_URL=wss://<chat-railway-domain>/chat`
- Auto-deploys on every push to `main`

### Chat + RAG servers → Railway ✓
- Railway does **not** support `docker-compose.yml` directly — each service deployed separately with its own Dockerfile
- RAG service: Dockerfile path `servers/rag/Dockerfile`, build context `servers/rag`
- Chat service: Dockerfile path `servers/chat/Dockerfile`, build context `servers/chat`
- RAG does not need a public domain (only chat calls it internally)
- Chat needs a public domain (Vercel connects to it via WebSocket)

### Env vars
| Service | Variable | Value |
|---------|----------|-------|
| rag | `VOYAGE_API_KEY` | from Voyage AI dashboard |
| chat | `OPENROUTER_API_KEY` | from OpenRouter dashboard |
| chat | `RAG_URL` | `http://rag.railway.internal:8001/sse` |
| chat | `ALLOWED_ORIGINS` | `https://<vercel-domain>` (no trailing slash) |
| vercel | `NEXT_PUBLIC_WS_URL` | `wss://<chat-railway-domain>/chat` |

### Notes
- `articles.db` is baked into the RAG image — to update articles, rebuild and redeploy
- Railway free tier pauses services after inactivity — cold start on first request
- `--timeout-keep-alive 0` is required in the chat Dockerfile CMD to prevent uvicorn from dropping the WebSocket while waiting for the LLM response

---

## Known issues / future improvements

- ~~**Scraper whitespace bug**: adjacent HTML elements concatenated without space~~ ✓ fixed
- **No conversation persistence**: chat history lives in memory, lost on disconnect — no sidebar, no session reload
- **Small corpus**: prototype runs on 19 articles (2 feeds × ~10 articles) — expand feeds and article count for a real demo

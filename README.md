# Postbot

A retrieval-augmented generation (RAG) chat that answers questions about Italian politics, economy, and current affairs using articles from [ilpost.it](https://www.ilpost.it) as its only source of truth. Every answer is grounded in retrieved article chunks and cites the original sources.

This is a personal/educational prototype, **not affiliated with or endorsed by Il Post**. See [Content & copyright](#content--copyright) below.

## How it works

```
ilpost.it → scraper → chunker → embedder → SQLite (articles.db)
                                                  |
User → chat server (WebSocket) → agentic loop → RAG MCP tool → similarity search → top-k chunks
                                                  |
                                          LLM answer + citations
```

- **Retrieval pipeline** (`retrieval/`): scrapes article metadata and full text from ilpost.it, splits it into overlapping token chunks, and embeds each chunk into a SQLite database.
- **RAG server** (`servers/rag/`): an MCP server exposing a single `search_articles` tool that runs cosine-similarity search over the embedded chunks.
- **Chat server** (`servers/chat/`): a FastAPI WebSocket server running an agentic loop — the LLM decides when to call `search_articles` and streams its answer back token by token.
- **Frontend** (`client/`): a Next.js chat UI. A minimal Python CLI client (`client.py`) is also included for quick testing.

## Repository layout

| Path | What it is |
|---|---|
| `retrieval/` | Scraper, chunker, embedder — scripts to build/update the article corpus |
| `servers/rag/` | MCP server exposing article retrieval as a tool |
| `servers/chat/` | WebSocket chat server with the agentic retrieval loop |
| `client/` | Next.js frontend |
| `client.py` | Minimal CLI client for testing the chat server directly |
| `docker-compose.yml` | Runs `chat` + `rag` services together locally |

See `retrieval/build_db.md` for corpus-building details.

## Setup

**Requirements:** Python 3.11+, Node.js 18+, Docker (optional, for `docker-compose`), an [OpenRouter](https://openrouter.ai) API key, and a [Voyage AI](https://www.voyageai.com) API key.

1. Create a `.env` file in the repo root:
   ```
   OPENROUTER_API_KEY=...
   VOYAGE_API_KEY=...
   ALLOWED_ORIGINS=http://localhost:3000
   ```
2. Run the chat + RAG servers:
   ```bash
   docker compose up --build
   ```
   This starts the RAG server (port 8001, internal) and the chat server (port 8000, WebSocket at `/chat`).
3. Talk to it either via the CLI client:
   ```bash
   python client.py
   ```
   or the web client:
   ```bash
   cd client
   npm install
   npm run dev
   ```
   Set `NEXT_PUBLIC_WS_URL=ws://localhost:8000/chat` in `client/.env.local`.

## The demo database

`servers/rag/articles.db` committed in this repo is a **small demo database** — a handful of real articles with their text truncated to a few sentences, kept only to show the schema and let the RAG server boot for local testing. It is not the full corpus.

To build a real corpus, use the scripts in `retrieval/` (see `retrieval/build_db.md` for the full workflow):

```bash
cd retrieval
python -c "from feed_parser import fetch_all; fetch_all(['https://www.ilpost.it/feed/'])"
python -c "
from article_scraper import scrape_all
from chunker import chunk_all
from embedder import embed_all
scrape_all()
chunk_all()
embed_all()
"
```

This produces `retrieval/articles.db` (gitignored — never commit the full corpus).

## Using a real vector database

At prototype scale, similarity search runs in-process with `numpy` over embeddings stored as JSON in SQLite (`retrieve()` in `embedder.py`). This does not scale past a few thousand chunks.

To swap in a real vector database (e.g. Supabase/Postgres with `pgvector`, Pinecone, Qdrant, ...):
- Replace the `embeddings` table with your vector store, keeping `chunk_id → vector` as the mapping.
- Reimplement `retrieve(query, top_k)` in `embedder.py` to embed the query and query your vector store instead of scanning SQLite.
- Everything downstream (the `search_articles` MCP tool, the agentic loop, the chat server) is unaffected, since it only depends on `retrieve()`'s return shape.

## Content & copyright

Article text is scraped from ilpost.it for retrieval purposes. The demo database ships only short, truncated excerpts. If you build a full corpus with the `retrieval/` scripts, keep it local/private — do not redistribute scraped article text, and respect ilpost.it's terms of service.

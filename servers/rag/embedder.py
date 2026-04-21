"""Generates embeddings for chunks using Voyage AI and stores them in SQLite."""

import json
import os
import sqlite3
from pathlib import Path

import numpy as np
import voyageai

DB_PATH = Path(__file__).parent / "articles.db"
MODEL = "voyage-3-lite"
BATCH_SIZE = 128  # Voyage AI supports up to 128 inputs per request


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS embeddings (
            chunk_id  INTEGER PRIMARY KEY REFERENCES chunks(id),
            vector    TEXT NOT NULL  -- JSON-encoded list of floats
        )
    """)
    conn.commit()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a), np.array(b)
    return float(np.dot(va, vb) / (np.linalg.norm(va) * np.linalg.norm(vb)))


def embed_all() -> None:
    """Generate and store embeddings for all chunks that don't have one yet."""
    api_key = os.environ.get("VOYAGE_API_KEY")
    if not api_key:
        raise RuntimeError("VOYAGE_API_KEY environment variable not set")

    client = voyageai.Client(api_key=api_key)

    with sqlite3.connect(DB_PATH) as conn:
        _init_db(conn)
        rows = conn.execute("""
            SELECT c.id, c.text FROM chunks c
            LEFT JOIN embeddings e ON c.id = e.chunk_id
            WHERE e.chunk_id IS NULL
        """).fetchall()

    print(f"Chunks to embed: {len(rows)}")

    # Process in batches
    all_results: list[tuple[int, str]] = []
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        ids = [r[0] for r in batch]
        texts = [r[1] for r in batch]

        response = client.embed(texts, model=MODEL, input_type="document")
        for chunk_id, vector in zip(ids, response.embeddings):
            all_results.append((chunk_id, json.dumps(vector)))

        print(f"  embedded {min(i + BATCH_SIZE, len(rows))}/{len(rows)}")

    with sqlite3.connect(DB_PATH) as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO embeddings (chunk_id, vector) VALUES (?, ?)",
            all_results,
        )
        conn.commit()

    print(f"\nDone. {len(all_results)} embeddings saved.")


def retrieve(query: str, top_k: int = 6) -> list[dict]:
    """Embed a query and return the top_k most similar chunks with metadata."""
    api_key = os.environ.get("VOYAGE_API_KEY")
    if not api_key:
        raise RuntimeError("VOYAGE_API_KEY environment variable not set")

    print("[RAG] embedding query...", flush=True)
    client = voyageai.Client(api_key=api_key)
    response = client.embed([query], model=MODEL, input_type="query")
    query_vector = response.embeddings[0]
    print("[RAG] query embedded, loading vectors from DB...", flush=True)

    try:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute("""
                SELECT e.chunk_id, e.vector, c.text, c.url, a.title, a.pub_date, a.categories
                FROM embeddings e
                JOIN chunks c ON e.chunk_id = c.id
                JOIN articles a ON c.url = a.url
            """).fetchall()
    except Exception as e:
        print(f"[RAG] DB error: {e}", flush=True)
        raise

    print(f"[RAG] loaded {len(rows)} vectors, computing similarity...", flush=True)
    scored = []
    for chunk_id, vector_json, text, url, title, pub_date, categories in rows:
        vector = json.loads(vector_json)
        score = cosine_similarity(query_vector, vector)
        scored.append({
            "chunk_id": chunk_id,
            "score": score,
            "text": text,
            "url": url,
            "title": title,
            "pub_date": pub_date,
            "categories": categories,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]

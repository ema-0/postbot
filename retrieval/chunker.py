"""Splits article text into overlapping token chunks and stores them in SQLite."""

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import tiktoken

DB_PATH = Path(__file__).parent / "articles.db"

CHUNK_SIZE = 500    # target tokens per chunk
OVERLAP = 50        # tokens carried over from previous chunk
ENCODING = "cl100k_base"  # encoding for text-embedding-3-small


@dataclass
class Chunk:
    url: str
    chunk_index: int
    text: str
    token_count: int


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            url         TEXT NOT NULL REFERENCES articles(url),
            chunk_index INTEGER NOT NULL,
            text        TEXT NOT NULL,
            token_count INTEGER NOT NULL
        )
    """)
    conn.commit()


def chunk_text(url: str, text: str) -> list[Chunk]:
    """Split text into overlapping chunks of ~CHUNK_SIZE tokens."""
    enc = tiktoken.get_encoding(ENCODING)

    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    # Tokenize each paragraph
    para_tokens = [enc.encode(p) for p in paragraphs]

    chunks: list[Chunk] = []
    current_tokens: list[int] = []
    chunk_index = 0

    for tokens in para_tokens:
        # If adding this paragraph would exceed CHUNK_SIZE, flush current chunk first
        if current_tokens and len(current_tokens) + len(tokens) > CHUNK_SIZE:
            text_chunk = enc.decode(current_tokens)
            chunks.append(Chunk(url, chunk_index, text_chunk, len(current_tokens)))
            chunk_index += 1
            # Keep last OVERLAP tokens as context for the next chunk
            current_tokens = current_tokens[-OVERLAP:]

        # If a single paragraph is larger than CHUNK_SIZE, split it by tokens directly
        if len(tokens) > CHUNK_SIZE:
            start = 0
            while start < len(tokens):
                end = start + CHUNK_SIZE
                slice_tokens = tokens[start:end]
                text_chunk = enc.decode(slice_tokens)
                chunks.append(Chunk(url, chunk_index, text_chunk, len(slice_tokens)))
                chunk_index += 1
                start += CHUNK_SIZE - OVERLAP
            current_tokens = []
        else:
            current_tokens.extend(tokens)

    # Flush remaining tokens
    if current_tokens:
        text_chunk = enc.decode(current_tokens)
        chunks.append(Chunk(url, chunk_index, text_chunk, len(current_tokens)))

    return chunks


def chunk_all() -> None:
    """Chunk all articles in article_text that don't yet have chunks."""
    with sqlite3.connect(DB_PATH) as conn:
        _init_db(conn)

        rows = conn.execute("""
            SELECT t.url, t.raw_text FROM article_text t
            LEFT JOIN chunks c ON t.url = c.url
            WHERE c.url IS NULL
        """).fetchall()

    print(f"Articles to chunk: {len(rows)}")

    all_chunks: list[Chunk] = []
    for url, text in rows:
        article_chunks = chunk_text(url, text)
        all_chunks.extend(article_chunks)
        print(f"  {len(article_chunks):2d} chunks  {url}")

    with sqlite3.connect(DB_PATH) as conn:
        conn.executemany(
            "INSERT INTO chunks (url, chunk_index, text, token_count) VALUES (?, ?, ?, ?)",
            [(c.url, c.chunk_index, c.text, c.token_count) for c in all_chunks],
        )
        conn.commit()

    print(f"\nDone. {len(all_chunks)} chunks saved from {len(rows)} articles.")

"""MCP RAG server — exposes article retrieval as an MCP tool over HTTP+SSE."""

import os

from mcp.server.fastmcp import FastMCP

from embedder import retrieve

mcp = FastMCP(
    "rag",
    host=os.environ.get("RAG_HOST", "0.0.0.0"),
    port=int(os.environ.get("RAG_PORT", "8001")),
)


@mcp.tool()
def search_articles(query: str, top_k: int = 6) -> list[dict]:
    """Search the ilpost.it article database for chunks relevant to the query.

    Args:
        query: The search query in natural language (Italian or English).
        top_k: Number of top results to return (default 6).

    Returns:
        List of chunks ranked by relevance, each with: chunk_id, score,
        text, url, title, pub_date, categories.
    """
    print(f"[RAG] query received: '{query}' (top_k={top_k})", flush=True)
    results = retrieve(query, top_k=top_k)
    print(f"[RAG] returning {len(results)} chunks", flush=True)
    return results


if __name__ == "__main__":
    mcp.run(transport="sse")

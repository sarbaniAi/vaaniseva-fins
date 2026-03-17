"""UC Vector Search for policies and FAQs."""

import logging
from vaaniseva.config import VS_ENDPOINT_NAME, VS_INDEX_NAME, DATABRICKS_HOST, DATABRICKS_TOKEN

logger = logging.getLogger(__name__)


def search_knowledge_base(query: str, num_results: int = 3) -> list[dict]:
    """
    Search the knowledge base using UC Vector Search.

    Returns list of {"content": str, "title": str, "score": float}.
    """
    if not all([VS_ENDPOINT_NAME, VS_INDEX_NAME, DATABRICKS_HOST, DATABRICKS_TOKEN]):
        logger.warning("Vector Search not configured, returning empty results")
        return []

    try:
        import requests

        resp = requests.post(
            f"{DATABRICKS_HOST}/api/2.0/vector-search/indexes/{VS_INDEX_NAME}/query",
            headers={
                "Authorization": f"Bearer {DATABRICKS_TOKEN}",
                "Content-Type": "application/json",
            },
            json={
                "query_text": query,
                "columns": ["content", "title", "category"],
                "num_results": num_results,
            },
            timeout=15,
        )

        if resp.status_code != 200:
            logger.error(f"Vector Search error {resp.status_code}: {resp.text}")
            return []

        data = resp.json()
        results = []
        for row in data.get("result", {}).get("data_array", []):
            results.append({
                "content": row[0] if len(row) > 0 else "",
                "title": row[1] if len(row) > 1 else "",
                "category": row[2] if len(row) > 2 else "",
                "score": row[-1] if len(row) > 3 else 0.0,
            })
        return results

    except Exception as e:
        logger.error(f"Vector Search exception: {e}")
        return []


def format_rag_context(results: list[dict]) -> str:
    """Format RAG results into a context string for the LLM."""
    if not results:
        return ""
    parts = []
    for r in results:
        title = r.get("title", "Policy")
        content = r.get("content", "")
        parts.append(f"[{title}]: {content}")
    return "\n\n".join(parts)

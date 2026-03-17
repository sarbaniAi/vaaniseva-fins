"""Hybrid retrieval: RAG for policies, SQL for account data."""

import logging
import re

from vaaniseva.retrieval.rag import search_knowledge_base, format_rag_context
from vaaniseva.retrieval.genie import get_customer_loans, get_overdue_loans

logger = logging.getLogger(__name__)

# Keywords that indicate policy/process questions (→ RAG)
POLICY_KEYWORDS = [
    "policy", "niyam", "rule", "guideline", "rbi", "restructur", "waiver",
    "moratorium", "penalty", "late fee", "complaint", "escalat", "process",
    "kaise", "how", "kya kar sakte", "option", "vikal",
]

# Keywords that indicate account/loan data questions (→ SQL)
ACCOUNT_KEYWORDS = [
    "amount", "kitna", "rashi", "balance", "emi", "payment", "paid",
    "overdue", "pending", "loan", "account", "history", "last payment",
]


def classify_query(text: str) -> str:
    """Classify whether query needs RAG, SQL, or both."""
    text_lower = text.lower()
    needs_rag = any(kw in text_lower for kw in POLICY_KEYWORDS)
    needs_sql = any(kw in text_lower for kw in ACCOUNT_KEYWORDS)

    if needs_rag and needs_sql:
        return "both"
    elif needs_rag:
        return "rag"
    elif needs_sql:
        return "sql"
    return "rag"  # Default to RAG for general questions


def get_context(
    customer_text: str,
    customer_id: int,
    stage: str,
) -> tuple[str, list[dict] | None]:
    """
    Get combined context for the agent brain.

    Returns:
        (rag_context_str, sql_results_list)
    """
    query_type = classify_query(customer_text)
    rag_context = ""
    sql_context = None

    # Always include loan data during NEGOTIATION and PURPOSE stages
    if stage in ("PURPOSE", "NEGOTIATION", "RESOLUTION"):
        query_type = "both" if query_type == "rag" else query_type

    if query_type in ("rag", "both"):
        results = search_knowledge_base(customer_text, num_results=3)
        rag_context = format_rag_context(results)

    if query_type in ("sql", "both"):
        sql_context = get_overdue_loans(customer_id)

    return rag_context, sql_context

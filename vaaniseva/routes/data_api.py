"""Dashboard aggregate API routes."""

import logging
from fastapi import APIRouter

from vaaniseva import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats")
async def get_stats():
    """Get dashboard statistics."""
    total_calls = db.execute_one(
        "SELECT COUNT(*) as count FROM call_logs WHERE status = 'COMPLETED'"
    )
    avg_score = db.execute_one(
        "SELECT ROUND(AVG(overall_score)::numeric, 1) as avg FROM quality_scores"
    )
    resolution = db.execute_one(
        """SELECT
            COUNT(*) FILTER (WHERE outcome IN ('PROMISE_TO_PAY','PARTIAL_PAYMENT','RESTRUCTURE_REQUEST')) as resolved,
            COUNT(*) as total
           FROM call_logs WHERE status = 'COMPLETED'"""
    )
    by_outcome = db.execute(
        """SELECT outcome, COUNT(*) as count
           FROM call_logs WHERE status = 'COMPLETED' AND outcome IS NOT NULL
           GROUP BY outcome"""
    )
    by_language = db.execute(
        """SELECT language, COUNT(*) as count
           FROM call_logs WHERE status = 'COMPLETED'
           GROUP BY language"""
    )

    total = (total_calls or {}).get("count", 0)
    resolved = (resolution or {}).get("resolved", 0)
    res_total = (resolution or {}).get("total", 1)

    return {
        "total_calls": total,
        "avg_quality_score": float((avg_score or {}).get("avg", 0) or 0),
        "resolution_rate": round(resolved / max(res_total, 1) * 100, 1),
        "calls_by_outcome": {r["outcome"]: r["count"] for r in (by_outcome or [])},
        "calls_by_language": {r["language"]: r["count"] for r in (by_language or [])},
    }

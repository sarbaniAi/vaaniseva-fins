"""Quality audit API routes."""

import json
import logging
from fastapi import APIRouter

from vaaniseva import db
from vaaniseva.models import AuditRunRequest
from vaaniseva.audit.batch_runner import score_calls

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/scores")
async def list_scores():
    """List all quality scores."""
    return db.execute(
        """SELECT qs.*, cl.customer_id,
                  cp.name as customer_name, cl.language, cl.outcome,
                  cl.turn_count, cl.started_at, cl.ended_at
           FROM quality_scores qs
           JOIN call_logs cl ON qs.call_id = cl.call_id
           JOIN customer_profiles cp ON cl.customer_id = cp.id
           ORDER BY qs.scored_at DESC"""
    )


@router.get("/scores/{call_id}")
async def get_score(call_id: str):
    """Get quality score for a specific call."""
    score = db.execute_one(
        "SELECT * FROM quality_scores WHERE call_id = %s", (call_id,)
    )
    if not score:
        return {"error": "Score not found for this call"}

    # Parse JSON fields
    for field in ("findings", "recommendations"):
        if isinstance(score.get(field), str):
            try:
                score[field] = json.loads(score[field])
            except json.JSONDecodeError:
                pass
    return score


@router.post("/run")
async def run_audit(req: AuditRunRequest):
    """Run quality audit on calls."""
    results = score_calls(req.call_ids)
    return {"scored": len(results), "results": results}


@router.get("/calls")
async def list_completed_calls():
    """List completed calls available for audit."""
    return db.execute(
        """SELECT cl.call_id, cl.customer_id, cp.name as customer_name,
                  cl.language, cl.outcome, cl.stage, cl.turn_count,
                  cl.started_at, cl.ended_at,
                  CASE WHEN qs.call_id IS NOT NULL THEN true ELSE false END as is_scored
           FROM call_logs cl
           JOIN customer_profiles cp ON cl.customer_id = cp.id
           LEFT JOIN quality_scores qs ON cl.call_id = qs.call_id
           WHERE cl.status = 'COMPLETED'
           ORDER BY cl.ended_at DESC"""
    )

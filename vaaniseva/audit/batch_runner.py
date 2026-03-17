"""Batch runner to score unscored call transcripts."""

import json
import logging

from vaaniseva import db
from vaaniseva.audit.evaluator import evaluate_transcript

logger = logging.getLogger(__name__)


def get_unscored_calls() -> list[dict]:
    """Fetch call logs that don't have quality scores yet."""
    return db.execute(
        """SELECT cl.call_id, cl.transcript
           FROM call_logs cl
           LEFT JOIN quality_scores qs ON cl.call_id = qs.call_id
           WHERE qs.call_id IS NULL AND cl.transcript IS NOT NULL
           ORDER BY cl.ended_at DESC"""
    )


def score_calls(call_ids: list[str] | None = None) -> list[dict]:
    """
    Score calls. If call_ids is None, score all unscored calls.

    Returns list of scoring results.
    """
    if call_ids:
        calls = []
        for cid in call_ids:
            row = db.execute_one(
                "SELECT call_id, transcript FROM call_logs WHERE call_id = %s", (cid,)
            )
            if row:
                calls.append(row)
    else:
        calls = get_unscored_calls()

    results = []
    for call in calls:
        call_id = call["call_id"]
        transcript = call.get("transcript")

        if isinstance(transcript, str):
            try:
                transcript = json.loads(transcript)
            except json.JSONDecodeError:
                logger.error(f"Invalid transcript JSON for call {call_id}")
                continue

        if not transcript:
            continue

        logger.info(f"Scoring call {call_id}...")
        score = evaluate_transcript(call_id, transcript)

        # Store in database
        db.execute_write(
            """INSERT INTO quality_scores
               (call_id, overall_score, compliance_score, script_adherence_score,
                empathy_score, resolution_score, language_quality_score,
                findings, recommendations, scored_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
               ON CONFLICT (call_id) DO UPDATE SET
                overall_score = EXCLUDED.overall_score,
                compliance_score = EXCLUDED.compliance_score,
                script_adherence_score = EXCLUDED.script_adherence_score,
                empathy_score = EXCLUDED.empathy_score,
                resolution_score = EXCLUDED.resolution_score,
                language_quality_score = EXCLUDED.language_quality_score,
                findings = EXCLUDED.findings,
                recommendations = EXCLUDED.recommendations,
                scored_at = NOW()""",
            (
                call_id,
                score.overall_score,
                score.compliance_score,
                score.script_adherence_score,
                score.empathy_score,
                score.resolution_score,
                score.language_quality_score,
                json.dumps(score.findings),
                json.dumps(score.recommendations),
            ),
        )

        results.append(score.model_dump())
        logger.info(f"Call {call_id} scored: {score.overall_score}")

    return results

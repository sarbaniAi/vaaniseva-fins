"""LLM-based rubric scoring for call transcripts."""

import json
import logging

from vaaniseva.agent.brain import call_llm
from vaaniseva.audit.rubric import get_rubric_prompt, get_weights
from vaaniseva.models import QualityScore

logger = logging.getLogger(__name__)

EVALUATOR_SYSTEM_PROMPT = """You are a quality auditor for an Indian NBFC's collections call center.
You evaluate call transcripts against a compliance and quality rubric.
You must be objective, fair, and thorough.
Always respond with valid JSON only — no markdown, no explanation outside the JSON."""


def evaluate_transcript(call_id: str, transcript: list[dict]) -> QualityScore:
    """
    Score a call transcript using the LLM evaluator.

    Args:
        call_id: The call identifier.
        transcript: List of {"speaker": "agent"|"customer", "text": str, "stage": str}.

    Returns:
        QualityScore with per-category scores and findings.
    """
    # Format transcript for the evaluator
    transcript_text = "\n".join(
        f"[{t.get('stage', 'UNKNOWN')}] {t['speaker'].upper()}: {t['text']}"
        for t in transcript
    )

    rubric_text = get_rubric_prompt()

    prompt = f"""Evaluate the following collections call transcript against the rubric below.

RUBRIC:
{rubric_text}

TRANSCRIPT:
{transcript_text}

Respond with ONLY a JSON object in this exact format:
{{
    "compliance_score": <0-100>,
    "script_adherence_score": <0-100>,
    "empathy_score": <0-100>,
    "resolution_score": <0-100>,
    "language_quality_score": <0-100>,
    "findings": ["finding 1", "finding 2", ...],
    "recommendations": ["recommendation 1", "recommendation 2", ...]
}}

Score each category 0-100 where:
- 90-100: Excellent, meets all criteria
- 70-89: Good, minor gaps
- 50-69: Needs improvement
- Below 50: Significant issues"""

    try:
        response = call_llm(
            system_prompt=EVALUATOR_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=0.3,
        )

        # Parse JSON from response
        # Handle potential markdown wrapping
        json_str = response.strip()
        if json_str.startswith("```"):
            json_str = json_str.split("```")[1]
            if json_str.startswith("json"):
                json_str = json_str[4:]
        json_str = json_str.strip()

        scores = json.loads(json_str)
        weights = get_weights()

        # Calculate weighted overall score
        overall = (
            scores.get("compliance_score", 0) * weights["compliance"]
            + scores.get("script_adherence_score", 0) * weights["script_adherence"]
            + scores.get("empathy_score", 0) * weights["empathy_tone"]
            + scores.get("resolution_score", 0) * weights["resolution"]
            + scores.get("language_quality_score", 0) * weights["language_quality"]
        )

        return QualityScore(
            call_id=call_id,
            overall_score=round(overall, 1),
            compliance_score=scores.get("compliance_score", 0),
            script_adherence_score=scores.get("script_adherence_score", 0),
            empathy_score=scores.get("empathy_score", 0),
            resolution_score=scores.get("resolution_score", 0),
            language_quality_score=scores.get("language_quality_score", 0),
            findings=scores.get("findings", []),
            recommendations=scores.get("recommendations", []),
        )

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse evaluator JSON: {e}")
        return QualityScore(
            call_id=call_id,
            overall_score=0,
            compliance_score=0,
            script_adherence_score=0,
            empathy_score=0,
            resolution_score=0,
            language_quality_score=0,
            findings=["Evaluation failed: could not parse LLM response"],
            recommendations=["Re-run evaluation"],
        )
    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        return QualityScore(
            call_id=call_id,
            overall_score=0,
            compliance_score=0,
            script_adherence_score=0,
            empathy_score=0,
            resolution_score=0,
            language_quality_score=0,
            findings=[f"Evaluation error: {str(e)}"],
            recommendations=["Re-run evaluation"],
        )

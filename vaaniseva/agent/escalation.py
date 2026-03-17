"""Escalation detection and context summary generation."""

import logging
import re

from vaaniseva.agent.brain import call_llm

logger = logging.getLogger(__name__)

# Trigger phrases (case-insensitive)
ESCALATION_TRIGGERS = [
    # English
    r"\bsupervisor\b", r"\bmanager\b", r"\bescalat", r"\bcomplaint\b",
    r"\blegal\b", r"\blawyer\b", r"\bcourt\b", r"\bconsumer forum\b",
    r"\bRBI\b", r"\bombudsman\b",
    # Hindi
    r"\bsupervisor\b", r"\bmanager\b", r"\bshikayat\b", r"\bcomplaint\b",
    r"\bwakeel\b", r"\bvakeel\b", r"\badaalat\b", r"\bcourt\b",
]

# Detect abusive or threatening language (from customer side)
ABUSE_PATTERNS = [
    r"\bgaali\b", r"\bbadtameez\b", r"\bbhag\b",
    # Keep this minimal — we detect tone, not specific words
]

MAX_DEADLOCK_TURNS = 6  # If negotiation goes beyond this without progress


def should_escalate(
    customer_text: str,
    conversation_history: list[dict],
    current_stage: str,
    turn_count: int,
) -> tuple[bool, str]:
    """
    Check if the call should be escalated.

    Returns:
        (should_escalate, reason)
    """
    text_lower = customer_text.lower()

    # Check explicit escalation requests
    for pattern in ESCALATION_TRIGGERS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True, "Customer requested supervisor/escalation"

    # Check for abusive language
    for pattern in ABUSE_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True, "Abusive language detected — agent safety protocol"

    # Deadlock detection in negotiation
    if current_stage == "NEGOTIATION" and turn_count > MAX_DEADLOCK_TURNS:
        return True, f"Negotiation deadlock after {turn_count} turns"

    return False, ""


def generate_escalation_summary(
    customer_name: str,
    conversation_history: list[dict],
    escalation_reason: str,
    loan_context: dict,
) -> str:
    """Generate a context summary for the supervisor handoff."""
    transcript_text = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in conversation_history
    )

    prompt = f"""Summarize this collections call for supervisor handoff. Be concise (3-5 bullet points).

Customer: {customer_name}
Escalation Reason: {escalation_reason}
Loan Details: {loan_context}

Transcript:
{transcript_text}

Provide:
1. Key customer concerns
2. What was offered
3. Why escalation happened
4. Recommended next steps"""

    try:
        return call_llm(
            system_prompt="You are a call center supervisor receiving an escalation summary. Be factual and concise.",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
        )
    except Exception as e:
        logger.error(f"Escalation summary generation failed: {e}")
        return f"Escalation Reason: {escalation_reason}\nCustomer: {customer_name}\n(Auto-summary unavailable)"

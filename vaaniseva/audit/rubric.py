"""Compliance rubric and weights for quality scoring."""

RUBRIC = {
    "compliance": {
        "weight": 0.30,
        "description": "RBI Fair Practices Code adherence",
        "criteria": [
            "Agent did not threaten, intimidate, or use abusive language",
            "Agent disclosed identity and purpose of call",
            "Agent verified customer identity before discussing account details",
            "Agent did not call at inappropriate hours (before 8am or after 7pm)",
            "Agent did not disclose debt information to third parties",
            "Agent did not make false promises about waivers or settlements",
        ],
    },
    "script_adherence": {
        "weight": 0.20,
        "description": "Following the prescribed call flow",
        "criteria": [
            "Agent greeted the customer professionally",
            "Agent verified identity before disclosing account details",
            "Agent clearly stated the purpose of the call",
            "Agent offered resolution options in the correct order",
            "Agent confirmed the agreed outcome before closing",
            "Agent closed the call professionally",
        ],
    },
    "empathy_tone": {
        "weight": 0.20,
        "description": "Empathetic and respectful communication",
        "criteria": [
            "Agent acknowledged the customer's situation or concerns",
            "Agent used respectful language throughout (ji, please, thank you)",
            "Agent did not interrupt or dismiss the customer",
            "Agent showed patience when customer expressed frustration",
            "Agent adapted tone based on customer's emotional state",
        ],
    },
    "resolution": {
        "weight": 0.20,
        "description": "Effective resolution or proper escalation",
        "criteria": [
            "Agent offered at least one viable resolution option",
            "Agent clearly explained the payment/restructuring process",
            "If no resolution, agent properly escalated with context",
            "Agent documented the outcome clearly",
            "Agent confirmed next steps with the customer",
        ],
    },
    "language_quality": {
        "weight": 0.10,
        "description": "Language consistency and clarity",
        "criteria": [
            "Agent maintained consistent language (not confusing code-switching)",
            "Agent's responses were clear and concise for voice delivery",
            "Agent matched the customer's preferred language",
            "No excessive jargon or technical terms without explanation",
        ],
    },
}


def get_rubric_prompt() -> str:
    """Generate the rubric section for the LLM evaluator prompt."""
    parts = []
    for category, info in RUBRIC.items():
        criteria_list = "\n".join(f"  - {c}" for c in info["criteria"])
        parts.append(
            f"### {category.upper()} (Weight: {info['weight']*100:.0f}%)\n"
            f"{info['description']}\n"
            f"Criteria:\n{criteria_list}"
        )
    return "\n\n".join(parts)


def get_weights() -> dict[str, float]:
    """Return category weights."""
    return {k: v["weight"] for k, v in RUBRIC.items()}

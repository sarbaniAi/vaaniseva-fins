"""LLM call logic — Sarvam-105B primary, Sarvam-30B (Databricks) fallback."""

import logging
import re

import requests

from vaaniseva.config import (
    SARVAM_API_KEY,
    SARVAM_API_BASE,
    SARVAM_LLM_MODEL,
    DATABRICKS_HOST,
    DATABRICKS_TOKEN,
    SARVAM_ENDPOINT_NAME,
)

logger = logging.getLogger(__name__)


def call_llm(
    system_prompt: str,
    messages: list[dict],
    max_tokens: int = 300,
    temperature: float = 0.7,
) -> str:
    """
    Call the LLM with a system prompt and conversation history.

    Tries Sarvam-105B API first, falls back to Sarvam-30B on Databricks Model Serving.

    Args:
        system_prompt: The system prompt (stage-specific).
        messages: List of {"role": "user"|"assistant", "content": "..."}.
        max_tokens: Max response tokens.
        temperature: Sampling temperature.

    Returns:
        The assistant's response text.
    """
    # Sarvam API requires first non-system message to be from user.
    # Strip leading assistant messages from conversation history.
    trimmed = list(messages)
    while trimmed and trimmed[0].get("role") == "assistant":
        trimmed.pop(0)
    full_messages = [{"role": "system", "content": system_prompt}] + trimmed

    # Primary: Sarvam-105B via API
    if SARVAM_API_KEY:
        try:
            resp = requests.post(
                f"{SARVAM_API_BASE}/v1/chat/completions",
                headers={
                    "api-subscription-key": SARVAM_API_KEY,
                    "Content-Type": "application/json",
                },
                json={
                    "model": SARVAM_LLM_MODEL,
                    "messages": full_messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
                timeout=30,
            )
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                return _clean_response(content)
            logger.warning(f"Sarvam API {resp.status_code}: {resp.text[:500]}, trying fallback")
        except Exception as e:
            logger.warning(f"Sarvam API error: {e}, trying fallback")

    # Fallback: Sarvam-30B on Databricks Model Serving
    if DATABRICKS_HOST and DATABRICKS_TOKEN:
        try:
            resp = requests.post(
                f"{DATABRICKS_HOST}/serving-endpoints/{SARVAM_ENDPOINT_NAME}/invocations",
                headers={
                    "Authorization": f"Bearer {DATABRICKS_TOKEN}",
                    "Content-Type": "application/json",
                },
                json={
                    "messages": full_messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
                timeout=30,
            )
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                return _clean_response(content)
            logger.error(f"Databricks endpoint error {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.error(f"Databricks endpoint exception: {e}")

    raise RuntimeError("Both Sarvam-105B and Sarvam-30B endpoints are unavailable")


def _clean_response(text: str) -> str:
    """Strip reasoning/thinking blocks from LLM output, keep only spoken dialogue."""
    # Strip <think>...</think> blocks (complete)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)

    # Strip unclosed <think> blocks (Sarvam-M often doesn't close them)
    if "<think>" in text:
        # Everything after <think> until end might be reasoning
        parts = text.split("<think>")
        # Keep only the part before <think>, or after </think> if it exists
        clean_parts = []
        for i, part in enumerate(parts):
            if i == 0:
                clean_parts.append(part)
            else:
                # This part is after a <think> — check if there's </think>
                if "</think>" in part:
                    after_think = part.split("</think>", 1)[1]
                    clean_parts.append(after_think)
                # else: skip entirely (unclosed think block)
        text = " ".join(clean_parts)

    # Strip English reasoning lines
    reasoning_patterns = [
        r"^Okay[,.]?\s.*$", r"^Let me\s.*$", r"^I need to\s.*$", r"^I should\s.*$",
        r"^The user\s.*$", r"^The task\s.*$", r"^The customer\s.*$", r"^The example\s.*$",
        r"^The greeting\s.*$", r"^The agent\s.*$", r"^First[,.]?\s.*$", r"^Since\s.*$",
        r"^Wait[,.]?\s.*$", r"^Now[,.]?\s.*$", r"^So[,.]?\s.*$", r"^Here'?s?\s.*$",
        r"^Looking at\s.*$", r"^Based on\s.*$", r"^According to\s.*$",
        r"^I'll\s.*$", r"^My response\s.*$", r"^The rules?\s.*$",
        r"^Check.*$", r"^Note:?\s.*$", r"^This is\s.*$", r"^In this\s.*$",
    ]
    for p in reasoning_patterns:
        text = re.sub(p, "", text, flags=re.MULTILINE | re.IGNORECASE)

    # Extract quoted Hindi/Hinglish speech if reasoning is mixed in
    if any(phrase in text.lower() for phrase in ["let me", "i should", "the user", "i need to", "the stage"]):
        quotes = re.findall(r'"([^"]+)"', text)
        if quotes:
            text = " ".join(quotes)

    text = re.sub(r"\n\s*\n", "\n", text).strip()
    return text

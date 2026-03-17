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
    full_messages = [{"role": "system", "content": system_prompt}] + messages

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
            logger.warning(f"Sarvam API {resp.status_code}, trying fallback")
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
    """Strip <think> blocks and extra whitespace from LLM output."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    return text.strip()

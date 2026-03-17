"""Sarvam Saaras v3 Speech-to-Text client."""

import base64
import io
import logging

import requests

from vaaniseva.config import SARVAM_API_KEY, SARVAM_API_BASE

logger = logging.getLogger(__name__)


def transcribe(audio_b64: str, filename: str = "audio.webm") -> tuple[str, str]:
    """
    Transcribe audio using Sarvam Saaras v3.

    Args:
        audio_b64: Base64-encoded audio data.
        filename: Filename hint for MIME type detection.

    Returns:
        (transcript, language_code) e.g. ("mujhe EMI ke baare mein baat karni hai", "hi")
    """
    audio_bytes = base64.b64decode(audio_b64)
    headers = {"api-subscription-key": SARVAM_API_KEY}
    files = {"file": (filename, io.BytesIO(audio_bytes), "audio/webm")}
    data = {
        "model": "saaras:v3",
        "language_code": "unknown",
        "with_timestamps": "false",
    }

    resp = requests.post(
        f"{SARVAM_API_BASE}/speech-to-text",
        headers=headers,
        files=files,
        data=data,
        timeout=30,
    )

    if resp.status_code != 200:
        logger.error(f"STT error {resp.status_code}: {resp.text}")
        raise RuntimeError(f"STT failed: {resp.text}")

    result = resp.json()
    transcript = result.get("transcript", "")
    lang = result.get("language_code", "en")
    # Normalize lang code: "hi-IN" → "hi"
    if "-" in lang:
        lang = lang.split("-")[0]

    logger.info(f"STT: lang={lang}, text={transcript[:80]}...")
    return transcript, lang

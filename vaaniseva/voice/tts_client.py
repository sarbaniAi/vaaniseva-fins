"""Sarvam Bulbul v3 Text-to-Speech client."""

import logging
import re

import requests

from vaaniseva.config import SARVAM_API_KEY, SARVAM_API_BASE, LANG_MAP, LANG_VOICES

logger = logging.getLogger(__name__)


def clean_for_tts(text: str) -> str:
    """Strip markdown/HTML so TTS doesn't read formatting characters aloud."""
    t = re.sub(r"<[^>]+>", "", text)
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = re.sub(r"\*(.+?)\*", r"\1", t)
    t = re.sub(r"__(.+?)__", r"\1", t)
    t = re.sub(r"_(.+?)_", r"\1", t)
    t = re.sub(r"~~(.+?)~~", r"\1", t)
    t = re.sub(r"`(.+?)`", r"\1", t)
    t = re.sub(r"^#{1,6}\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"^\s*[-*+]\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"^\s*\d+\.\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"^\s*>\s*", "", t, flags=re.MULTILINE)
    t = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", t)
    t = re.sub(r"[|]", " ", t)
    t = re.sub(r"-{3,}", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def synthesize(text: str, lang: str = "hi") -> str | None:
    """
    Convert text to speech using Sarvam Bulbul v3.

    Args:
        text: Text to speak.
        lang: 2-letter language code.

    Returns:
        Base64-encoded WAV audio, or None on failure.
    """
    lang_code = LANG_MAP.get(lang[:2] if lang else "hi", "hi-IN")
    voice = LANG_VOICES.get(lang[:2] if lang else "hi", "anushka")
    clean_text = clean_for_tts(text)

    if not clean_text:
        return None

    # Bulbul limit is ~500 chars per request
    clean_text = clean_text[:500]

    try:
        resp = requests.post(
            f"{SARVAM_API_BASE}/text-to-speech",
            headers={
                "api-subscription-key": SARVAM_API_KEY,
                "Content-Type": "application/json",
            },
            json={
                "inputs": [clean_text],
                "target_language_code": lang_code,
                "speaker": voice,
                "model": "bulbul:v2",
                "pitch": 0,
                "pace": 1.0,
                "loudness": 1.5,
                "enable_preprocessing": True,
            },
            timeout=30,
        )

        if resp.status_code == 200:
            audio_b64 = resp.json().get("audios", [None])[0]
            if audio_b64:
                return audio_b64
            logger.warning("TTS returned empty audio")
        else:
            logger.error(f"TTS error {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.error(f"TTS exception: {e}")

    return None

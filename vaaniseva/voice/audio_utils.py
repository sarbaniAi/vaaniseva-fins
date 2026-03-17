"""Audio encoding and format conversion utilities."""

import base64
import re


def strip_data_uri(audio_data: str) -> str:
    """Strip data URI prefix from base64 audio string."""
    if "base64," in audio_data:
        return audio_data.split("base64,")[1]
    return audio_data


def detect_lang_from_text(text: str) -> str:
    """Detect language from Unicode script ranges."""
    if any("\u0900" <= c <= "\u097F" for c in text):
        return "hi"
    if any("\u0B80" <= c <= "\u0BFF" for c in text):
        return "ta"
    if any("\u0C00" <= c <= "\u0C7F" for c in text):
        return "te"
    if any("\u0C80" <= c <= "\u0CFF" for c in text):
        return "kn"
    if any("\u0D00" <= c <= "\u0D7F" for c in text):
        return "ml"
    if any("\u0980" <= c <= "\u09FF" for c in text):
        return "bn"
    if any("\u0A80" <= c <= "\u0AFF" for c in text):
        return "gu"
    if any("\u0900" <= c <= "\u097F" for c in text):
        return "mr"  # Marathi shares Devanagari
    if any("\u0A00" <= c <= "\u0A7F" for c in text):
        return "pa"
    if any("\u0B00" <= c <= "\u0B7F" for c in text):
        return "od"
    return "en"

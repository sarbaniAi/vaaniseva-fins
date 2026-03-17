"""Environment variables, constants, and language maps."""

import os

# --- Sarvam AI ---
SARVAM_API_KEY = os.environ.get("SARVAM_API_KEY", "")
SARVAM_API_BASE = "https://api.sarvam.ai"
SARVAM_LLM_MODEL = "sarvam-m"  # Sarvam-105B via API

# --- Databricks ---
DATABRICKS_HOST = os.environ.get("DATABRICKS_HOST", "")
DATABRICKS_TOKEN = os.environ.get("DATABRICKS_TOKEN", "")
SARVAM_ENDPOINT_NAME = os.environ.get("SARVAM_ENDPOINT_NAME", "sarvam-30b-serving")

# --- Lakebase (Autoscaling) ---
LAKEBASE_PROJECT = os.environ.get("LAKEBASE_PROJECT", "vaaniseva")
LAKEBASE_BRANCH = os.environ.get("LAKEBASE_BRANCH", "production")
LAKEBASE_ENDPOINT = os.environ.get("LAKEBASE_ENDPOINT", "primary")
LAKEBASE_HOST = os.environ.get("LAKEBASE_HOST", "")
LAKEBASE_DB_NAME = os.environ.get("LAKEBASE_DB_NAME", "vaaniseva")

# --- Vector Search ---
VS_ENDPOINT_NAME = os.environ.get("VS_ENDPOINT_NAME", "")
VS_INDEX_NAME = os.environ.get("VS_INDEX_NAME", "")

# --- Genie ---
GENIE_SPACE_ID = os.environ.get("GENIE_SPACE_ID", "")

# --- Language maps ---
LANG_MAP = {
    "hi": "hi-IN", "en": "en-IN", "ta": "ta-IN", "te": "te-IN",
    "kn": "kn-IN", "ml": "ml-IN", "bn": "bn-IN", "gu": "gu-IN",
    "mr": "mr-IN", "pa": "pa-IN", "od": "od-IN",
}

LANG_NAMES = {
    "hi": "Hindi", "en": "English", "ta": "Tamil", "te": "Telugu",
    "kn": "Kannada", "ml": "Malayalam", "bn": "Bengali", "gu": "Gujarati",
    "mr": "Marathi", "pa": "Punjabi", "od": "Odia",
}

# TTS voice per language (Bulbul v3 voices)
LANG_VOICES = {
    "hi": "anushka", "en": "anushka", "ta": "anushka", "te": "anushka",
    "kn": "anushka", "ml": "anushka", "bn": "anushka", "gu": "anushka",
    "mr": "anushka", "pa": "anushka", "od": "anushka",
}

# Call flow states
class CallStage:
    GREETING = "GREETING"
    IDENTITY_VERIFICATION = "IDENTITY_VERIFICATION"
    PURPOSE = "PURPOSE"
    NEGOTIATION = "NEGOTIATION"
    RESOLUTION = "RESOLUTION"
    CLOSING = "CLOSING"
    ESCALATION = "ESCALATION"

CALL_STAGE_ORDER = [
    CallStage.GREETING,
    CallStage.IDENTITY_VERIFICATION,
    CallStage.PURPOSE,
    CallStage.NEGOTIATION,
    CallStage.RESOLUTION,
    CallStage.CLOSING,
]

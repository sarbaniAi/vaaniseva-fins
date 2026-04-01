#!/usr/bin/env python3
"""Generate app.yaml.local from .env file for Databricks App deployment."""

import os

# Load .env if not already in environment
env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                if value and key not in os.environ:
                    os.environ[key] = value


def env(key, default=""):
    return os.environ.get(key, default)


yaml_content = f"""command:
  - uvicorn
  - app:app
  - --host
  - 0.0.0.0
  - --port
  - "8000"

env:
  # Sarvam AI
  - name: SARVAM_API_KEY
    value: "{env('SARVAM_API_KEY')}"
  - name: SARVAM_ENDPOINT_NAME
    value: "{env('SARVAM_ENDPOINT_NAME', 'sarvam-30b-serving')}"

  # Lakebase
  - name: LAKEBASE_PROJECT
    value: "{env('LAKEBASE_PROJECT', 'vaaniseva')}"
  - name: LAKEBASE_BRANCH
    value: "{env('LAKEBASE_BRANCH', 'production')}"
  - name: LAKEBASE_ENDPOINT
    value: "{env('LAKEBASE_ENDPOINT', 'primary')}"
  - name: LAKEBASE_HOST
    value: "{env('LAKEBASE_HOST')}"
  - name: LAKEBASE_DB_NAME
    value: "{env('LAKEBASE_DB_NAME', 'vaaniseva')}"

  # Twilio
  - name: TWILIO_ACCOUNT_SID
    value: "{env('TWILIO_ACCOUNT_SID')}"
  - name: TWILIO_AUTH_TOKEN
    value: "{env('TWILIO_AUTH_TOKEN')}"
  - name: TWILIO_PHONE_NUMBER
    value: "{env('TWILIO_PHONE_NUMBER')}"
  - name: TWILIO_WHATSAPP_FROM
    value: "{env('TWILIO_WHATSAPP_FROM', 'whatsapp:+14155238886')}"

  # Sarvam TTS via Twilio Function
  - name: SARVAM_TTS_URL
    value: "{env('SARVAM_TTS_URL')}"

  # Optional
  - name: VS_ENDPOINT_NAME
    value: "{env('VS_ENDPOINT_NAME')}"
  - name: VS_INDEX_NAME
    value: "{env('VS_INDEX_NAME')}"
  - name: GENIE_SPACE_ID
    value: "{env('GENIE_SPACE_ID')}"
"""

output_path = os.path.join(os.path.dirname(__file__), "..", "app.yaml.local")
with open(output_path, "w") as f:
    f.write(yaml_content)

print(f"Generated {output_path}")

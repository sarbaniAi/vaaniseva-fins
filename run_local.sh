#!/bin/bash
# Run VaaniSeva locally for development
# Set environment variables before running

export SARVAM_API_KEY="${SARVAM_API_KEY}"
export SARVAM_ENDPOINT_NAME="sarvam-30b-serving"
export LAKEBASE_HOST="${LAKEBASE_HOST}"
export LAKEBASE_PROJECT="vaaniseva"
export LAKEBASE_BRANCH="production"
export LAKEBASE_ENDPOINT="primary"
export LAKEBASE_DB_NAME="vaaniseva"
export TWILIO_ACCOUNT_SID="${TWILIO_ACCOUNT_SID}"
export TWILIO_AUTH_TOKEN="${TWILIO_AUTH_TOKEN}"
export TWILIO_PHONE_NUMBER="${TWILIO_PHONE_NUMBER}"

uvicorn app:app --host 0.0.0.0 --port 8000 --reload

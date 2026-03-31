"""Twilio telephony integration for real outbound calls."""

import logging
import os

from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Connect

logger = logging.getLogger(__name__)

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER", "")


def get_client() -> Client:
    """Get Twilio REST client."""
    return Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


def initiate_call(to_number: str, call_id: str, app_host: str) -> dict:
    """
    Place an outbound call via Twilio.

    When the customer picks up, Twilio connects a WebSocket media stream
    to our app for bidirectional audio.

    Args:
        to_number: Customer phone number (E.164 format, e.g. +919876543210)
        call_id: VaaniSeva call session ID
        app_host: Public hostname of the app (e.g. yatra-voice-agent-xxx.databricksapps.com)

    Returns:
        dict with call_sid and status
    """
    client = get_client()

    # TwiML instructs Twilio to connect a WebSocket stream when customer answers
    twiml_url = f"https://{app_host}/api/telephony/twiml/{call_id}"

    call = client.calls.create(
        to=to_number,
        from_=TWILIO_PHONE_NUMBER,
        url=twiml_url,
        method="POST",
        status_callback=f"https://{app_host}/api/telephony/status/{call_id}",
        status_callback_event=["initiated", "ringing", "answered", "completed"],
        status_callback_method="POST",
    )

    logger.info(f"Twilio call initiated: SID={call.sid}, to={to_number}, call_id={call_id}")

    return {
        "call_sid": call.sid,
        "status": call.status,
    }

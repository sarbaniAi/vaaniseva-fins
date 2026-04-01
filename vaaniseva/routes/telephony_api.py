"""Telephony API routes — Twilio outbound calls using inline TwiML (no webhooks needed).

Databricks Apps are behind SSO, so Twilio can't reach webhook URLs.
Instead, we use inline TwiML + Twilio Call Update API for multi-turn conversation.
"""

import logging
import os
import asyncio
from datetime import datetime

from fastapi import APIRouter, Request
from twilio.rest import Client

from vaaniseva.agent.call_flow import create_session, get_session, remove_session
from vaaniseva.retrieval.genie import get_customer_profile, get_customer_loans

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/telephony", tags=["telephony"])

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER", "")
SARVAM_TTS_URL = os.environ.get("SARVAM_TTS_URL", "")  # Twilio Function /audio endpoint

# Active phone calls: call_id → {"twilio_sid": str, "status": str}
_phone_calls: dict[str, dict] = {}


def _get_twilio() -> Client:
    return Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


def _escape_xml(text: str) -> str:
    """Escape text for safe XML embedding."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;"))


@router.post("/dial")
async def dial_customer(request: Request):
    """Initiate a real outbound call. Agent speaks first, then listens."""
    body = await request.json()
    customer_id = body.get("customer_id")
    to_number = body.get("to_number")
    call_purpose = body.get("call_purpose", "LOAN_RECOVERY")

    if not customer_id or not to_number:
        return {"error": "customer_id and to_number required"}

    customer = get_customer_profile(customer_id)
    if not customer:
        return {"error": "Customer not found"}
    loans = get_customer_loans(customer_id)

    # Create agent session
    session = create_session(
        customer=customer,
        loans=loans,
        language="hi",
        agent_name="VaaniSeva Agent",
        call_purpose=call_purpose,
    )

    # Generate greeting
    try:
        greeting_text, _ = session.generate_greeting()
    except Exception as e:
        logger.error(f"Greeting generation failed: {e}")
        greeting_text = f"Namaste, main VaaniSeva se bol raha hoon. Kya main {customer.get('name', '')} ji se baat kar sakta hoon?"

    # Place call with inline TwiML — greeting + pause
    # Use Sarvam Bulbul TTS via Twilio Function if configured, else fall back to Polly
    if SARVAM_TTS_URL:
        from urllib.parse import quote
        audio_url = f"{SARVAM_TTS_URL}?text={quote(greeting_text[:500])}&amp;lang=hi-IN"
        twiml = f"""<Response>
    <Play>{audio_url}</Play>
    <Pause length="120"/>
</Response>"""
    else:
        safe_greeting = _escape_xml(greeting_text)
        twiml = f"""<Response>
    <Say voice="Polly.Aditi" language="hi-IN">{safe_greeting}</Say>
    <Pause length="120"/>
</Response>"""

    try:
        client = _get_twilio()
        call = client.calls.create(
            to=to_number,
            from_=TWILIO_PHONE_NUMBER,
            twiml=twiml,
        )

        _phone_calls[session.call_id] = {
            "twilio_sid": call.sid,
            "status": "GREETING",
            "customer_name": customer.get("name"),
        }

        logger.info(f"Call placed: SID={call.sid}, to={to_number}, call_id={session.call_id}")

        return {
            "call_id": session.call_id,
            "call_sid": call.sid,
            "status": "DIALING",
            "customer_name": customer.get("name"),
            "greeting": greeting_text,
        }
    except Exception as e:
        logger.error(f"Twilio dial failed: {e}")
        remove_session(session.call_id)
        return {"error": str(e)}


@router.post("/send-agent-message")
async def send_agent_message(request: Request):
    """Send a new agent message to an active phone call (update call TwiML)."""
    body = await request.json()
    call_id = body.get("call_id")
    agent_text = body.get("agent_text", "")

    if not call_id or call_id not in _phone_calls:
        return {"error": "Call not found"}

    phone_call = _phone_calls[call_id]
    twilio_sid = phone_call["twilio_sid"]

    if SARVAM_TTS_URL:
        from urllib.parse import quote
        audio_url = f"{SARVAM_TTS_URL}?text={quote(agent_text[:500])}&amp;lang=hi-IN"
        twiml = f"""<Response>
    <Play>{audio_url}</Play>
    <Pause length="120"/>
</Response>"""
    else:
        safe_text = _escape_xml(agent_text)
        twiml = f"""<Response>
    <Say voice="Polly.Aditi" language="hi-IN">{safe_text}</Say>
    <Pause length="120"/>
</Response>"""

    try:
        client = _get_twilio()
        client.calls(twilio_sid).update(twiml=twiml)
        return {"status": "sent", "agent_text": agent_text}
    except Exception as e:
        logger.error(f"Call update failed: {e}")
        return {"error": str(e)}


@router.post("/process-turn")
async def process_phone_turn(request: Request):
    """Process a conversation turn for a phone call.

    The agent operator types what the customer said (heard over phone),
    and gets the agent's response which is then spoken on the call.
    """
    body = await request.json()
    call_id = body.get("call_id")
    customer_text = body.get("customer_text", "")

    if not call_id:
        return {"error": "call_id required"}

    session = get_session(call_id)
    if not session:
        return {"error": "Session not found"}

    phone_call = _phone_calls.get(call_id)
    if not phone_call:
        return {"error": "Phone call not found"}

    # Process the turn through the agent
    try:
        response = session.process_turn(text=customer_text)
        agent_text = response.agent_text

        # Update the live phone call with the agent's response
        twilio_sid = phone_call["twilio_sid"]
        safe_text = _escape_xml(agent_text)

        if response.is_ended:
            twiml = f"""<Response>
    <Say voice="Polly.Aditi" language="hi-IN">{safe_text}</Say>
    <Hangup/>
</Response>"""
        else:
            twiml = f"""<Response>
    <Say voice="Polly.Aditi" language="hi-IN">{safe_text}</Say>
    <Pause length="120"/>
</Response>"""

        client = _get_twilio()
        client.calls(twilio_sid).update(twiml=twiml)

        return {
            "call_id": call_id,
            "customer_text": customer_text,
            "agent_text": agent_text,
            "stage": response.stage,
            "is_ended": response.is_ended,
        }
    except Exception as e:
        logger.error(f"Phone turn processing error: {e}")
        return {"error": str(e)}


@router.post("/hangup")
async def hangup_call(request: Request):
    """Hang up an active phone call."""
    body = await request.json()
    call_id = body.get("call_id")

    phone_call = _phone_calls.get(call_id)
    if not phone_call:
        return {"error": "Call not found"}

    try:
        client = _get_twilio()
        client.calls(phone_call["twilio_sid"]).update(status="completed")
        _phone_calls.pop(call_id, None)

        session = get_session(call_id)
        if session:
            session.end_call(outcome="COMPLETED")

        return {"status": "hung_up"}
    except Exception as e:
        return {"error": str(e)}


@router.get("/call-status/{call_id}")
async def get_call_status(call_id: str):
    """Get status of a phone call."""
    phone_call = _phone_calls.get(call_id)
    if not phone_call:
        return {"error": "Call not found"}

    try:
        client = _get_twilio()
        call = client.calls(phone_call["twilio_sid"]).fetch()
        return {
            "call_id": call_id,
            "twilio_sid": call.sid,
            "status": call.status,
            "duration": call.duration,
        }
    except Exception as e:
        return {"error": str(e)}

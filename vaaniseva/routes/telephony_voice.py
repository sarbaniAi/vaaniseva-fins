"""Fully automated voice-to-voice telephony — polling-based (no webhooks needed).

Flow:
1. Place call with TwiML: <Say>greeting</Say> <Record/> <Pause/>
2. Customer speaks → Twilio records audio
3. Background task polls for recording → downloads → Sarvam STT → LLM
4. Updates call with new TwiML: <Say>response</Say> <Record/> <Pause/>
5. Repeat until call ends

Works entirely from Databricks App — no ngrok, no proxy, no public endpoints.
"""

import asyncio
import io
import logging
import os
import time

import requests as http_requests
from fastapi import APIRouter, Request

from vaaniseva.agent.call_flow import create_session, get_session, remove_session
from vaaniseva.retrieval.genie import get_customer_profile, get_customer_loans
from vaaniseva.voice.stt_client import transcribe
from vaaniseva.retrieval.hybrid import get_context

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/voice", tags=["voice"])

TWILIO_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE = os.environ.get("TWILIO_PHONE_NUMBER", "")
TWILIO_API = "https://api.twilio.com/2010-04-01"
SARVAM_TTS_URL = os.environ.get("SARVAM_TTS_URL", "")

# Track active voice calls
_voice_calls: dict[str, dict] = {}


def _twilio_auth():
    return (TWILIO_SID, TWILIO_TOKEN)


def _escape_xml(text: str) -> str:
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;"))


def _make_twiml(say_text: str, record: bool = True, hangup: bool = False) -> str:
    """Build TwiML for a turn: Play Sarvam audio or fall back to Polly Say."""
    if SARVAM_TTS_URL:
        from urllib.parse import quote
        audio_url = f"{SARVAM_TTS_URL}?text={quote(say_text[:500])}&amp;lang=hi-IN"
        speak = f'<Play>{audio_url}</Play>'
    else:
        safe = _escape_xml(say_text)
        speak = f'<Say voice="Polly.Aditi" language="hi-IN">{safe}</Say>'

    if hangup:
        return f"""<Response>
  {speak}
  <Pause length="1"/>
  <Hangup/>
</Response>"""

    if record:
        return f"""<Response>
  {speak}
  <Pause length="3"/>
  <Record maxLength="20" playBeep="true" trim="trim-silence" timeout="5"/>
  <Pause length="300"/>
</Response>"""
    else:
        return f"""<Response>
  {speak}
  <Pause length="300"/>
</Response>"""


@router.post("/dial")
async def dial_customer(request: Request):
    """Start a fully automated voice call."""
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

    session = create_session(
        customer=customer, loans=loans,
        language="hi", agent_name="Ria",
        call_purpose=call_purpose,
    )

    # Scripted greeting
    greeting, _ = session.generate_greeting()

    # Place call with inline TwiML
    twiml = _make_twiml(greeting, record=True)

    try:
        resp = http_requests.post(
            f"{TWILIO_API}/Accounts/{TWILIO_SID}/Calls.json",
            auth=_twilio_auth(),
            data={
                "To": to_number,
                "From": TWILIO_PHONE,
                "Twiml": twiml,
            },
        )
        if resp.status_code not in (200, 201):
            return {"error": f"Twilio error {resp.status_code}: {resp.text}"}

        call_data = resp.json()
        call_sid = call_data["sid"]

        _voice_calls[session.call_id] = {
            "twilio_sid": call_sid,
            "status": "DIALING",
            "turn": 0,
            "last_recording_count": 0,
            "processing": False,
        }

        # Start background polling task
        asyncio.create_task(_poll_and_respond(session.call_id))

        logger.info(f"Voice call placed: SID={call_sid}, call_id={session.call_id}")
        return {
            "call_id": session.call_id,
            "call_sid": call_sid,
            "status": "DIALING",
            "customer_name": customer.get("name"),
            "greeting": greeting,
        }
    except Exception as e:
        logger.error(f"Dial failed: {e}")
        remove_session(session.call_id)
        return {"error": str(e)}


async def _poll_and_respond(call_id: str):
    """Background task: poll for new recordings, process, update call."""
    vc = _voice_calls.get(call_id)
    if not vc:
        return

    call_sid = vc["twilio_sid"]
    session = get_session(call_id)
    if not session:
        return

    logger.info(f"Starting polling for call {call_id} (SID: {call_sid})")

    max_turns = 20
    poll_interval = 2  # seconds

    for turn in range(max_turns):
        if session.is_ended:
            break

        # Wait for a recording to appear
        recording_url = await _wait_for_new_recording(call_sid, vc, timeout=60)

        if not recording_url:
            # No recording after timeout — customer may have hung up
            logger.info(f"Call {call_id}: no recording after timeout, ending")
            break

        # Check if call is still active
        if not _is_call_active(call_sid):
            logger.info(f"Call {call_id}: call no longer active")
            break

        # Download and transcribe
        customer_text = await _download_and_transcribe(recording_url)
        logger.info(f"Call {call_id} turn {turn}: Customer said: '{customer_text}'")

        # Filter out echo/noise: repeated characters or gibberish from TTS bleed
        if customer_text:
            words = customer_text.split()
            unique_words = set(words)
            # If >80% of words are the same, it's echo/noise
            if len(words) > 3 and len(unique_words) <= 2:
                logger.info(f"Call {call_id}: Filtered echo/noise: '{customer_text[:50]}'")
                customer_text = ""

        if not customer_text or not customer_text.strip():
            # Couldn't understand — ask to repeat
            twiml = _make_twiml(
                "Maaf kijiye, sun nahi payi. Kya aap dobara bol sakte hain?",
                record=True,
            )
            _update_call(call_sid, twiml)
            continue

        # Process through agent
        try:
            rag_context, sql_context = get_context(
                customer_text, session.customer.get("id", 0), session.stage
            )
            response = session.process_turn(
                text=customer_text,
                rag_context=rag_context or "",
                sql_context=sql_context,
            )

            agent_text = response.agent_text
            if not agent_text or len(agent_text) < 3:
                agent_text = "Ji, main samajh gayi. Kya aap thoda aur bata sakte hain?"

            logger.info(f"Call {call_id} turn {turn}: Agent: '{agent_text[:100]}' | Stage: {response.stage}")

            if response.is_ended:
                twiml = _make_twiml(agent_text, record=False, hangup=True)
                _update_call(call_sid, twiml)
                break
            else:
                twiml = _make_twiml(agent_text, record=True)
                _update_call(call_sid, twiml)

        except Exception as e:
            logger.error(f"Call {call_id} processing error: {e}")
            twiml = _make_twiml(
                "Maaf kijiye, technical issue aa rahi hai. Hum aapko dobara call karenge. Namaste.",
                hangup=True,
            )
            _update_call(call_sid, twiml)
            break

        vc["turn"] = turn + 1

    # Cleanup
    session.end_call(outcome="COMPLETED")
    _voice_calls.pop(call_id, None)
    logger.info(f"Call {call_id} ended after {vc.get('turn', 0)} turns")


async def _wait_for_new_recording(call_sid: str, vc: dict, timeout: int = 60) -> str | None:
    """Poll Twilio for a new recording on this call."""
    start = time.time()
    known_count = vc.get("last_recording_count", 0)

    while time.time() - start < timeout:
        await asyncio.sleep(2)

        try:
            resp = http_requests.get(
                f"{TWILIO_API}/Accounts/{TWILIO_SID}/Recordings.json",
                auth=_twilio_auth(),
                params={"CallSid": call_sid},
            )
            if resp.status_code != 200:
                continue

            recordings = resp.json().get("recordings", [])
            if len(recordings) > known_count:
                # New recording found
                vc["last_recording_count"] = len(recordings)
                latest = recordings[0]  # Most recent first
                rec_sid = latest["sid"]
                # Return the audio URL
                return f"{TWILIO_API}/Accounts/{TWILIO_SID}/Recordings/{rec_sid}.wav"
        except Exception as e:
            logger.warning(f"Recording poll error: {e}")

        # Check if call is still active
        if not _is_call_active(call_sid):
            return None

    return None


async def _download_and_transcribe(recording_url: str) -> str:
    """Download recording from Twilio and transcribe via Sarvam STT."""
    import base64
    try:
        resp = http_requests.get(recording_url, auth=_twilio_auth())
        if resp.status_code != 200:
            logger.error(f"Recording download failed: {resp.status_code}")
            return ""

        audio_b64 = base64.b64encode(resp.content).decode("utf-8")
        transcript, lang = transcribe(audio_b64, filename="recording.wav")
        return transcript
    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        return ""


def _update_call(call_sid: str, twiml: str):
    """Update a live Twilio call with new TwiML."""
    try:
        resp = http_requests.post(
            f"{TWILIO_API}/Accounts/{TWILIO_SID}/Calls/{call_sid}.json",
            auth=_twilio_auth(),
            data={"Twiml": twiml},
        )
        if resp.status_code != 200:
            logger.error(f"Call update failed: {resp.status_code} {resp.text}")
    except Exception as e:
        logger.error(f"Call update exception: {e}")


def _is_call_active(call_sid: str) -> bool:
    """Check if a Twilio call is still in progress."""
    try:
        resp = http_requests.get(
            f"{TWILIO_API}/Accounts/{TWILIO_SID}/Calls/{call_sid}.json",
            auth=_twilio_auth(),
        )
        if resp.status_code == 200:
            status = resp.json().get("status", "")
            return status in ("queued", "ringing", "in-progress")
    except Exception:
        pass
    return False


@router.post("/hangup")
async def hangup(request: Request):
    """Hang up an active voice call."""
    body = await request.json()
    call_id = body.get("call_id")

    vc = _voice_calls.get(call_id)
    if not vc:
        return {"error": "Call not found"}

    twiml = _make_twiml("Dhanyavaad, aapka din shubh ho. Namaste.", hangup=True)
    _update_call(vc["twilio_sid"], twiml)

    session = get_session(call_id)
    if session:
        session.end_call(outcome="COMPLETED")
    _voice_calls.pop(call_id, None)

    return {"status": "hung_up"}


@router.get("/active-calls")
async def list_active_calls():
    """List active voice calls."""
    return {
        cid: {"twilio_sid": vc["twilio_sid"], "turn": vc["turn"], "status": vc["status"]}
        for cid, vc in _voice_calls.items()
    }

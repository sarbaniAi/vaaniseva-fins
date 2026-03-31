"""WhatsApp API routes — BFSI Collections flow via Twilio WhatsApp.

Supports:
- Outbound messaging (text + interactive menus)
- Incoming webhook (text + voice notes)
- Structured collection flow (payment reminders, restructuring)
- Voice note transcription via Sarvam STT
"""

import base64
import logging
import os
import threading
from datetime import datetime
from xml.sax.saxutils import escape as xml_escape

import requests as http_requests
from fastapi import APIRouter, Request
from fastapi.responses import Response as FastAPIResponse

from vaaniseva.agent.brain import call_llm
from vaaniseva.voice.stt_client import transcribe

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])

TWILIO_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_WA_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
TWILIO_API = "https://api.twilio.com/2010-04-01"

# In-memory stores (thread-safe)
_lock = threading.Lock()
_conversations: dict[str, list[dict]] = {}   # phone -> messages
_flow_state: dict[str, dict] = {}            # phone -> {step, data}

WA_SYSTEM_PROMPT = """You are VaaniSeva, a polite and professional collections assistant on WhatsApp.
Respond in the SAME language the customer writes (Hindi, English, Hinglish, etc.).
Keep responses SHORT (1-2 sentences, max 300 chars for easy mobile reading).
No markdown headers. Use plain text with occasional emoji.
Help with: payment reminders, EMI queries, loan restructuring, payment links.
Always be respectful per RBI Fair Practices Code. Never threaten or harass."""


def _normalize_phone(number: str) -> str:
    number = number.strip().replace(" ", "").replace("-", "")
    if number.startswith("whatsapp:"):
        number = number[9:]
    if not number.startswith("+"):
        number = "+91" + number
    return number


def _twilio_send(to: str, body: str) -> dict:
    """Send a WhatsApp message via Twilio REST API."""
    wa_to = f"whatsapp:{_normalize_phone(to)}"
    try:
        resp = http_requests.post(
            f"{TWILIO_API}/Accounts/{TWILIO_SID}/Messages.json",
            auth=(TWILIO_SID, TWILIO_TOKEN),
            data={"To": wa_to, "From": TWILIO_WA_FROM, "Body": body},
            timeout=30,
        )
        if resp.status_code in (200, 201):
            return {"status": "sent", "sid": resp.json().get("sid")}
        return {"error": f"Twilio {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        return {"error": str(e)}


def _store_message(phone: str, role: str, text: str):
    phone = _normalize_phone(phone)
    with _lock:
        if phone not in _conversations:
            _conversations[phone] = []
        _conversations[phone].append({
            "role": role,
            "text": text,
            "time": datetime.now().strftime("%H:%M"),
        })


# ===================================================================
# COLLECTIONS FLOW ENGINE
# ===================================================================

def _process_flow(phone: str, user_msg: str) -> str:
    """Process a WhatsApp collections flow step. Returns bot reply."""
    phone = _normalize_phone(phone)
    with _lock:
        state = _flow_state.get(phone, {"step": "menu", "data": {}})
    step = state["step"]
    data = state.get("data", {})

    # Reset keywords
    if user_msg.strip().lower() in ("menu", "back", "start", "hi", "hello", "reset"):
        with _lock:
            _flow_state[phone] = {"step": "menu", "data": {}}
        return _menu_text()

    if step == "menu":
        choice = user_msg.strip()
        if choice in ("1", "payment", "pay"):
            with _lock:
                _flow_state[phone] = {"step": "verify_account", "data": {"flow": "payment"}}
            return "Share your last 4 digits of account number."

        elif choice in ("2", "emi", "balance"):
            with _lock:
                _flow_state[phone] = {"step": "verify_account", "data": {"flow": "emi"}}
            return "Share your last 4 digits of account number."

        elif choice in ("3", "restructure"):
            with _lock:
                _flow_state[phone] = {"step": "verify_account", "data": {"flow": "restructure"}}
            return "Share your last 4 digits of account number."

        elif choice in ("4", "callback", "call"):
            with _lock:
                _flow_state[phone] = {"step": "callback_time", "data": {"flow": "callback"}}
            return ("When would you like us to call you?\n"
                    "1. Today (8AM-7PM)\n"
                    "2. Tomorrow\n"
                    "3. This weekend")

        else:
            # Free-form AI chat
            with _lock:
                _flow_state[phone] = {"step": "chat", "data": {"flow": "chat"}}
            return _ai_reply(phone, user_msg)

    elif step == "verify_account":
        # Look up customer by account_last4 in Lakebase
        last4 = user_msg.strip()
        if len(last4) > 4:
            last4 = last4[-4:]
        try:
            from vaaniseva.retrieval.genie import get_all_customers, get_customer_loans
            from vaaniseva import db
            cust = db.execute_one(
                "SELECT * FROM customer_profiles WHERE account_last4 = %s", (last4,)
            )
        except Exception as e:
            logger.error(f"DB lookup error: {e}")
            cust = None

        if not cust:
            return f"Account {last4} not found. Please re-enter your last 4 digits."

        # Fetch loans
        try:
            loans = get_customer_loans(cust["id"])
        except Exception:
            loans = []

        # Format loan details
        total_overdue = sum(float(l.get("overdue_amount", 0)) for l in loans)
        loan_text = f"*{cust['name']}* ({cust['city']})\nRisk: {cust['risk_tier']}\n\n"
        for i, l in enumerate(loans):
            od = float(l.get("overdue_amount", 0))
            loan_text += f"*Loan {i+1}: {l['loan_type']}*\n"
            loan_text += f"  Principal: Rs.{float(l['principal']):,.0f}\n"
            loan_text += f"  EMI: Rs.{float(l['emi_amount']):,.0f}/mo\n"
            if od > 0:
                loan_text += f"  Overdue: Rs.{od:,.0f} ({l['days_overdue']}d)\n"
            if l.get("last_payment_date"):
                loan_text += f"  Last Pay: {str(l['last_payment_date'])[:10]}\n"
            loan_text += "\n"
        if total_overdue > 0:
            loan_text += f"*Total Overdue: Rs.{total_overdue:,.0f}*\n"

        data["cust_id"] = cust["id"]
        data["cust_name"] = cust["name"]
        data["account"] = last4
        data["total_overdue"] = total_overdue

        flow = data.get("flow", "emi")

        if flow == "payment":
            with _lock:
                _flow_state[phone] = {"step": "payment_method", "data": data}
            return (f"Verified: *{cust['name']}* (...{last4})\n"
                    f"Overdue: *Rs.{total_overdue:,.0f}*\n\n"
                    "Pay via?\n1. UPI\n2. Net Banking\n3. Debit Card\n4. Payment link")

        elif flow == "emi":
            with _lock:
                _flow_state[phone] = {"step": "emi_detail", "data": data}
            return (f"Verified!\n\n{loan_text}\n"
                    "1. Make a payment\n2. Download statement\n3. Payment history\n4. Talk to agent\n\n"
                    "Reply *menu* to go back.")

        elif flow == "restructure":
            with _lock:
                _flow_state[phone] = {"step": "restructure_reason", "data": data}
            return (f"Verified: *{cust['name']}* (...{last4})\n"
                    f"Outstanding: Rs.{total_overdue:,.0f}\n\n"
                    "Reason for restructuring?\n"
                    "1. Salary delayed\n2. Medical emergency\n3. Job loss\n4. Other")

    elif step == "payment_method":
        methods = {"1": "UPI", "2": "Net Banking", "3": "Debit Card", "4": "Payment Link"}
        method = methods.get(user_msg.strip(), user_msg)
        with _lock:
            _flow_state[phone] = {"step": "menu", "data": {}}
        total = data.get("total_overdue", 0)
        return (f"Payment registered!\n\n"
                f"Name: {data.get('cust_name', '-')}\n"
                f"Amount: Rs.{total:,.0f}\n"
                f"Method: {method}\n"
                f"Ref: VS-{datetime.now().strftime('%Y%m%d%H%M')}\n\n"
                "Reply *menu* for more options.")

    elif step == "emi_detail":
        if user_msg.strip() in ("1", "pay"):
            with _lock:
                _flow_state[phone] = {"step": "payment_method", "data": data}
            return (f"Due: Rs.{data.get('total_overdue', 0):,.0f}\n\n"
                    "Pay via?\n1. UPI\n2. Net Banking\n3. Debit Card\n4. Payment link")
        elif user_msg.strip() in ("2", "statement"):
            with _lock:
                _flow_state[phone] = {"step": "menu", "data": {}}
            return f"Statement emailed within 24hrs.\nRef: ST-{datetime.now().strftime('%Y%m%d%H%M')}\n\nReply *menu*"
        elif user_msg.strip() in ("3", "history"):
            # Fetch payment history from Lakebase
            try:
                from vaaniseva.retrieval.genie import get_payment_history
                cid = data.get("cust_id")
                # Get all loan IDs for this customer
                from vaaniseva import db
                loan_ids = db.execute("SELECT id FROM loan_accounts WHERE customer_id = %s", (cid,))
                history = []
                for lid in loan_ids[:3]:
                    history.extend(get_payment_history(lid["id"], 3))
                if history:
                    reply = "*Recent Payments:*\n\n"
                    for h in history[:5]:
                        reply += f"{str(h['payment_date'])[:10]} | Rs.{float(h['amount']):,.0f} | {h.get('payment_mode','')} | {h.get('status','')}\n"
                    reply += "\nReply *menu*"
                else:
                    reply = "No payment history found.\nReply *menu*"
            except Exception as e:
                reply = f"Could not fetch history.\nReply *menu*"
            with _lock:
                _flow_state[phone] = {"step": "menu", "data": {}}
            return reply
        elif user_msg.strip() in ("4", "agent"):
            with _lock:
                _flow_state[phone] = {"step": "menu", "data": {}}
            return f"Agent callback in 4hrs.\nRef: AG-{datetime.now().strftime('%Y%m%d%H%M')}\n\nReply *menu*"
        else:
            with _lock:
                _flow_state[phone] = {"step": "menu", "data": {}}
            return _menu_text()

    elif step == "restructure_reason":
        reasons = {"1": "Salary delayed", "2": "Medical emergency", "3": "Job loss", "4": "Other"}
        reason = reasons.get(user_msg.strip(), user_msg)
        data["reason"] = reason
        with _lock:
            _flow_state[phone] = {"step": "restructure_confirm", "data": data}
        return (f"Reason: {reason}\n\n"
                "Our restructuring team will review your request within 48 hours.\n"
                "You'll receive a call with available options.\n\n"
                "Would you like to proceed?\n"
                "1. Yes, submit request\n"
                "2. No, go back")

    elif step == "restructure_confirm":
        if user_msg.strip() in ("1", "yes"):
            with _lock:
                _flow_state[phone] = {"step": "menu", "data": {}}
            return (f"Your restructuring request has been submitted.\n"
                    f"Reference: RS-{datetime.now().strftime('%Y%m%d%H%M')}\n"
                    f"Reason: {data.get('reason', 'Not specified')}\n\n"
                    "Our team will contact you within 48 hours.\n"
                    "Reply *menu* for more options.")
        else:
            with _lock:
                _flow_state[phone] = {"step": "menu", "data": {}}
            return _menu_text()

    elif step == "callback_time":
        times = {"1": "Today", "2": "Tomorrow", "3": "This weekend"}
        when = times.get(user_msg.strip(), user_msg)
        with _lock:
            _flow_state[phone] = {"step": "menu", "data": {}}
        return (f"Callback scheduled for: {when}\n"
                f"Reference: CB-{datetime.now().strftime('%Y%m%d%H%M')}\n\n"
                "Our agent will call you between 8 AM - 7 PM.\n"
                "Reply *menu* for more options.")

    elif step == "chat":
        if user_msg.strip().lower() in ("menu", "back", "options"):
            with _lock:
                _flow_state[phone] = {"step": "menu", "data": {}}
            return _menu_text()
        return _ai_reply(phone, user_msg)

    # Fallback
    with _lock:
        _flow_state[phone] = {"step": "menu", "data": {}}
    return _menu_text()


def _menu_text() -> str:
    return ("Namaste! Welcome to *VaaniSeva*.\n\n"
            "How can we help you today?\n"
            "1. Make a Payment\n"
            "2. Check EMI Details\n"
            "3. Request Loan Restructuring\n"
            "4. Request Callback\n"
            "5. Ask a Question\n\n"
            "Reply with a number to get started.")


def _ai_reply(phone: str, user_msg: str) -> str:
    """Generate free-form AI reply using conversation history."""
    with _lock:
        msgs = _conversations.get(phone, [])
    # Build history pairs
    history = []
    messages = [{"role": "system", "content": WA_SYSTEM_PROMPT}]
    for m in msgs[-8:]:
        messages.append({
            "role": "user" if m["role"] == "user" else "assistant",
            "content": m["text"],
        })
    messages.append({"role": "user", "content": user_msg})
    try:
        return call_llm(WA_SYSTEM_PROMPT, messages[1:])  # pass without system (call_llm adds it)
    except Exception as e:
        logger.error(f"WhatsApp AI reply error: {e}")
        return "Sorry, I'm having trouble right now. Please try again or reply *menu* for options."


# ===================================================================
# API ENDPOINTS
# ===================================================================

@router.post("/send")
async def send_message(request: Request):
    """Send a WhatsApp message to a customer. Falls back to local-only if Twilio fails."""
    body = await request.json()
    to = body.get("to", "")
    message = body.get("message", "")

    if not to or not message:
        return {"error": "to and message required"}

    _store_message(to, "agent", message)

    # Try Twilio, but don't fail if it doesn't work
    if TWILIO_SID and TWILIO_TOKEN:
        result = _twilio_send(to, message)
        if "error" not in result:
            return {**result, "mode": "twilio"}
        # Twilio failed — still saved locally
        logger.warning(f"Twilio send failed, saved locally: {result.get('error', '')[:100]}")
        return {"status": "local_only", "mode": "local",
                "note": "Message saved locally. Twilio send failed — activate WhatsApp Sandbox in Twilio Console."}

    return {"status": "local_only", "mode": "local",
            "note": "Twilio not configured. Message saved locally."}


@router.post("/start-flow")
async def start_flow(request: Request):
    """Start the collections flow. Works locally without Twilio."""
    body = await request.json()
    to = body.get("to", "")

    if not to:
        return {"error": "to (phone number) required"}

    phone = _normalize_phone(to)
    with _lock:
        _flow_state[phone] = {"step": "menu", "data": {}}

    msg = _menu_text()
    _store_message(to, "agent", msg)

    # Try Twilio but don't block on failure
    twilio_result = None
    if TWILIO_SID and TWILIO_TOKEN:
        twilio_result = _twilio_send(to, msg)
        if "error" in twilio_result:
            logger.warning(f"Twilio WhatsApp failed: {twilio_result['error'][:100]}")
            twilio_result = None

    return {
        "status": "flow_started",
        "flow_started": True,
        "mode": "twilio" if twilio_result else "local",
        "note": "" if twilio_result else "Flow started locally. Use 'Simulate Incoming' to test. To send real WhatsApp: activate Sandbox in Twilio Console."
    }


@router.post("/simulate")
async def simulate_incoming(request: Request):
    """Simulate an incoming WhatsApp message (for testing without webhook)."""
    body = await request.json()
    phone = body.get("from", "")
    message = body.get("message", "")

    if not phone or not message:
        return {"error": "from and message required"}

    phone = _normalize_phone(phone)
    _store_message(phone, "user", message)

    reply = _process_flow(phone, message)
    _store_message(phone, "agent", reply)

    return {"reply": reply, "phone": phone}


@router.get("/conversations")
async def list_conversations():
    """List all WhatsApp conversations."""
    with _lock:
        result = {}
        for phone, msgs in _conversations.items():
            result[phone] = {
                "message_count": len(msgs),
                "last_message": msgs[-1] if msgs else None,
            }
    return result


@router.get("/conversations/{phone}")
async def get_conversation(phone: str):
    """Get conversation history for a phone number."""
    phone = _normalize_phone(phone)
    with _lock:
        msgs = list(_conversations.get(phone, []))
    return {"phone": phone, "messages": msgs}


@router.post("/incoming")
async def incoming_webhook(request: Request):
    """Twilio WhatsApp incoming message webhook.

    Configure this URL in Twilio Console > WhatsApp Sandbox > Webhook URL.
    URL: https://<your-proxy>/api/whatsapp/incoming
    """
    form = await request.form()
    from_number = form.get("From", "")
    body_text = form.get("Body", "")
    num_media = int(form.get("NumMedia", "0"))

    logger.info(f"WhatsApp from {from_number}: {body_text[:80]}")

    phone = from_number.replace("whatsapp:", "")
    phone = _normalize_phone(phone)

    # Handle voice notes
    if num_media > 0:
        media_url = form.get("MediaUrl0", "")
        media_type = form.get("MediaContentType0", "")
        if media_url and "audio" in (media_type or ""):
            try:
                audio_resp = http_requests.get(
                    media_url, auth=(TWILIO_SID, TWILIO_TOKEN), timeout=30)
                audio_b64 = base64.b64encode(audio_resp.content).decode()
                transcript, lang = transcribe(audio_b64, "audio.ogg")
                _store_message(phone, "user", f"[Voice] {transcript}")
                reply = _process_flow(phone, transcript)
            except Exception as e:
                logger.error(f"Voice note error: {e}")
                reply = "Sorry, I couldn't process your voice note. Please type your message."
                _store_message(phone, "user", "[Voice note - failed to process]")
        else:
            _store_message(phone, "user", body_text or "[Media]")
            reply = _process_flow(phone, body_text or "hi")
    else:
        _store_message(phone, "user", body_text)
        reply = _process_flow(phone, body_text)

    _store_message(phone, "agent", reply)

    # Return TwiML response
    safe_reply = xml_escape(reply[:1600])
    twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{safe_reply}</Message></Response>'
    return FastAPIResponse(content=twiml, media_type="application/xml")

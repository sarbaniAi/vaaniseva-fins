"""VaaniSeva — FastAPI entrypoint with Twilio Voice + WhatsApp."""

import logging
import os
import sys

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("vaaniseva")

app = FastAPI(
    title="VaaniSeva",
    description="Sovereign AI Voice Agent for Indian BFSI Collections",
    version="0.2.0",
)


@app.on_event("startup")
async def startup():
    """Initialize Lakebase connection pool on startup (non-blocking)."""
    import threading
    def _init_db():
        try:
            from vaaniseva.db import init_pool
            init_pool()
            logger.info("Lakebase connection pool ready")
        except Exception as e:
            logger.warning(f"Lakebase init failed: {e}")
    # Run in background so app starts immediately
    threading.Thread(target=_init_db, daemon=True).start()
    logger.info("App started, Lakebase init running in background...")


# --- Core API routes ---
from vaaniseva.routes.call_api import router as call_router
from vaaniseva.routes.customer_api import router as customer_router
from vaaniseva.routes.audit_api import router as audit_router
from vaaniseva.routes.data_api import router as data_router

app.include_router(call_router)
app.include_router(customer_router)
app.include_router(audit_router)
app.include_router(data_router)

# --- Twilio telephony routes ---
try:
    from vaaniseva.routes.telephony_api import router as telephony_router
    app.include_router(telephony_router)
    logger.info("Telephony routes registered (/api/telephony/*)")
except Exception as e:
    logger.warning(f"Telephony routes skipped: {e}")

try:
    from vaaniseva.routes.telephony_voice import router as voice_router
    app.include_router(voice_router)
    logger.info("Voice telephony routes registered (/api/voice/*)")
except Exception as e:
    logger.warning(f"Voice telephony routes skipped: {e}")

# --- WhatsApp routes ---
try:
    from vaaniseva.routes.whatsapp_api import router as whatsapp_router
    app.include_router(whatsapp_router)
    logger.info("WhatsApp routes registered (/api/whatsapp/*)")
except Exception as e:
    logger.warning(f"WhatsApp routes skipped: {e}")


# --- Health check ---
@app.get("/api/health")
async def health():
    db_ok = False
    db_error = ""
    try:
        from vaaniseva import db
        if db._pool is not None:
            rows = db.execute("SELECT 1 AS ok")
            db_ok = True
        else:
            db_error = "Pool not initialized"
    except Exception as e:
        db_error = str(e)[:200]
    return {
        "status": "ok",
        "service": "VaaniSeva",
        "db_connected": db_ok,
        "db_error": db_error,
        "twilio_configured": bool(os.environ.get("TWILIO_ACCOUNT_SID")),
    }


# --- WhatsApp process endpoint (called by Twilio Function relay) ---
from fastapi import Request as FastAPIRequest
from pydantic import BaseModel

class WAProcessRequest(BaseModel):
    message: str = ""
    from_number: str = ""

    class Config:
        # Accept "from" as alias for "from_number"
        populate_by_name = True

@app.post("/api/whatsapp/process")
async def whatsapp_process(request: FastAPIRequest):
    """Process a WhatsApp message. Called by Twilio Function as relay."""
    body = await request.json()
    from_number = body.get("from", "")
    message = body.get("message", "")
    try:
        from vaaniseva.routes.whatsapp_api import _process_flow, _normalize_phone, _store_message
        phone = _normalize_phone(from_number)
        _store_message(phone, "user", message)
        reply = _process_flow(phone, message)
        _store_message(phone, "agent", reply)
        return {"reply": reply}
    except Exception as e:
        logger.error(f"WhatsApp process error: {e}")
        return {"reply": f"Error: {e}", "error": True}


# --- Serve static files (SPA) — must be last ---
app.mount("/", StaticFiles(directory="static", html=True), name="static")

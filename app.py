"""VaaniSeva — FastAPI entrypoint."""

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
    version="0.1.0",
)


@app.on_event("startup")
async def startup():
    """Initialize Lakebase connection pool on startup."""
    try:
        from vaaniseva.db import init_pool
        init_pool()
        logger.info("Lakebase connection pool ready")
    except Exception as e:
        logger.warning(f"Lakebase init skipped (will work without DB): {e}")


# --- Register API routes ---
from vaaniseva.routes.call_api import router as call_router
from vaaniseva.routes.customer_api import router as customer_router
from vaaniseva.routes.audit_api import router as audit_router
from vaaniseva.routes.data_api import router as data_router

app.include_router(call_router)
app.include_router(customer_router)
app.include_router(audit_router)
app.include_router(data_router)


# --- Health check ---
@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "VaaniSeva"}


# --- Serve static files (SPA) ---
app.mount("/", StaticFiles(directory="static", html=True), name="static")

"""Call management API routes."""

import json
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from vaaniseva import db
from vaaniseva.models import CallStartRequest, CallStartResponse, CallTurnRequest, CallEndRequest
from vaaniseva.agent.call_flow import create_session, get_session, remove_session
from vaaniseva.retrieval.genie import get_customer_profile, get_customer_loans
from vaaniseva.retrieval.hybrid import get_context
from vaaniseva.voice.tts_client import synthesize

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/call", tags=["calls"])


@router.post("/start", response_model=CallStartResponse)
async def start_call(req: CallStartRequest):
    """Start a new call session with a customer."""
    # Fetch customer data
    customer = get_customer_profile(req.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    loans = get_customer_loans(req.customer_id)

    # Create session
    session = create_session(
        customer=customer,
        loans=loans,
        language=req.language,
        agent_name=req.agent_name,
        call_purpose=req.call_purpose,
    )

    # Generate greeting
    greeting_text, greeting_audio = session.generate_greeting()

    # Log call start
    try:
        db.execute_write(
            """INSERT INTO call_logs
               (call_id, customer_id, agent_name, language, stage, started_at, status)
               VALUES (%s, %s, %s, %s, %s, %s, 'IN_PROGRESS')""",
            (session.call_id, req.customer_id, req.agent_name, req.language,
             session.stage, datetime.utcnow()),
        )
    except Exception as e:
        logger.warning(f"Failed to log call start: {e}")

    return CallStartResponse(
        call_id=session.call_id,
        customer_name=customer.get("name", "Customer"),
        language=session.language,
        greeting_text=greeting_text,
        greeting_audio_b64=greeting_audio,
        stage=session.stage,
    )


@router.post("/turn")
async def call_turn(req: CallTurnRequest):
    """Process one turn in the call."""
    session = get_session(req.call_id)
    if not session:
        raise HTTPException(status_code=404, detail="Call session not found")

    # Get hybrid context
    customer_text = req.text or ""
    rag_context, sql_context = "", None
    if customer_text:
        rag_context, sql_context = get_context(
            customer_text,
            session.customer.get("id", 0),
            session.stage,
        )

    # Process the turn
    response = session.process_turn(
        audio_b64=req.audio_b64,
        text=req.text,
        rag_context=rag_context,
        sql_context=sql_context,
    )

    # Update call log
    try:
        db.execute_write(
            "UPDATE call_logs SET stage = %s, turn_count = %s WHERE call_id = %s",
            (session.stage, session.turn_count, session.call_id),
        )
    except Exception as e:
        logger.warning(f"Failed to update call log: {e}")

    return response


@router.post("/end")
async def end_call(req: CallEndRequest):
    """End a call session."""
    session = get_session(req.call_id)
    if not session:
        raise HTTPException(status_code=404, detail="Call session not found")

    summary = session.end_call(outcome=req.outcome, notes=req.notes)

    # Save to database
    try:
        db.execute_write(
            """UPDATE call_logs SET
                stage = %s, outcome = %s, turn_count = %s,
                language = %s, ended_at = %s, status = 'COMPLETED',
                transcript = %s, notes = %s
               WHERE call_id = %s""",
            (
                summary["stage_reached"],
                summary["outcome"],
                summary["turn_count"],
                summary["language"],
                datetime.utcnow(),
                json.dumps(summary["transcript"]),
                req.notes,
                req.call_id,
            ),
        )
    except Exception as e:
        logger.warning(f"Failed to save call log: {e}")

    remove_session(req.call_id)
    return summary


@router.websocket("/ws/{call_id}")
async def call_websocket(websocket: WebSocket, call_id: str):
    """WebSocket for bidirectional audio+transcript streaming."""
    await websocket.accept()

    session = get_session(call_id)
    if not session:
        await websocket.close(code=4004, reason="Call session not found")
        return

    try:
        while not session.is_ended:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "audio":
                audio_b64 = data.get("audio_b64", "")
                rag_context, sql_context = get_context(
                    "", session.customer.get("id", 0), session.stage
                )
                response = session.process_turn(
                    audio_b64=audio_b64,
                    rag_context=rag_context,
                    sql_context=sql_context,
                )
                await websocket.send_json(response.model_dump())

            elif msg_type == "text":
                text = data.get("text", "")
                rag_context, sql_context = get_context(
                    text, session.customer.get("id", 0), session.stage
                )
                response = session.process_turn(
                    text=text,
                    rag_context=rag_context,
                    sql_context=sql_context,
                )
                await websocket.send_json(response.model_dump())

            elif msg_type == "end":
                summary = session.end_call(
                    outcome=data.get("outcome"),
                    notes=data.get("notes"),
                )
                await websocket.send_json({"type": "call_ended", **summary})
                break

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for call {call_id}")
        if not session.is_ended:
            session.end_call(outcome="DISCONNECTED")
    except Exception as e:
        logger.error(f"WebSocket error for call {call_id}: {e}")
        await websocket.close(code=1011, reason=str(e))

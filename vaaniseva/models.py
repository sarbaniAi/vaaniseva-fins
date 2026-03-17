"""Pydantic models for VaaniSeva."""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class CallStageEnum(str, Enum):
    GREETING = "GREETING"
    IDENTITY_VERIFICATION = "IDENTITY_VERIFICATION"
    PURPOSE = "PURPOSE"
    NEGOTIATION = "NEGOTIATION"
    RESOLUTION = "RESOLUTION"
    CLOSING = "CLOSING"
    ESCALATION = "ESCALATION"


class CallOutcome(str, Enum):
    PROMISE_TO_PAY = "PROMISE_TO_PAY"
    PARTIAL_PAYMENT = "PARTIAL_PAYMENT"
    RESTRUCTURE_REQUEST = "RESTRUCTURE_REQUEST"
    DISPUTE = "DISPUTE"
    ESCALATED = "ESCALATED"
    NO_RESOLUTION = "NO_RESOLUTION"
    CALLBACK_REQUESTED = "CALLBACK_REQUESTED"


# --- Request/Response models ---

class CallStartRequest(BaseModel):
    customer_id: int
    language: str = "hi"
    agent_name: str = "VaaniSeva Agent"


class CallStartResponse(BaseModel):
    call_id: str
    customer_name: str
    language: str
    greeting_text: str
    greeting_audio_b64: Optional[str] = None
    stage: str = "GREETING"


class CallTurnRequest(BaseModel):
    call_id: str
    audio_b64: Optional[str] = None
    text: Optional[str] = None


class CallTurnResponse(BaseModel):
    call_id: str
    customer_text: str
    agent_text: str
    agent_audio_b64: Optional[str] = None
    stage: str
    context_used: Optional[list[dict]] = None
    is_ended: bool = False
    outcome: Optional[str] = None


class CallEndRequest(BaseModel):
    call_id: str
    outcome: Optional[str] = None
    notes: Optional[str] = None


class CustomerProfile(BaseModel):
    id: int
    name: str
    phone: str
    city: str
    language_pref: str
    account_last4: str
    risk_tier: Optional[str] = None


class LoanAccount(BaseModel):
    id: int
    customer_id: int
    loan_type: str
    principal: float
    emi_amount: float
    overdue_amount: float
    days_overdue: int
    last_payment_date: Optional[str] = None


class TranscriptEntry(BaseModel):
    speaker: str  # "agent" or "customer"
    text: str
    timestamp: Optional[str] = None
    stage: Optional[str] = None


class QualityScore(BaseModel):
    call_id: str
    overall_score: float
    compliance_score: float
    script_adherence_score: float
    empathy_score: float
    resolution_score: float
    language_quality_score: float
    findings: Optional[list[str]] = None
    recommendations: Optional[list[str]] = None


class AuditRunRequest(BaseModel):
    call_ids: Optional[list[str]] = None  # None = score all unscored


class DashboardStats(BaseModel):
    total_calls: int = 0
    avg_quality_score: float = 0.0
    resolution_rate: float = 0.0
    avg_call_duration_sec: float = 0.0
    calls_by_outcome: dict = Field(default_factory=dict)
    calls_by_language: dict = Field(default_factory=dict)

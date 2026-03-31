"""Call flow state machine: GREETING → VERIFY → PURPOSE → NEGOTIATE → RESOLVE → CLOSE."""

import json
import logging
import uuid
from datetime import datetime

from vaaniseva.config import CallStage, CALL_STAGE_ORDER
from vaaniseva.agent.brain import call_llm
from vaaniseva.agent.system_prompts import get_prompt
from vaaniseva.agent.escalation import should_escalate, generate_escalation_summary
from vaaniseva.voice.stt_client import transcribe
from vaaniseva.voice.tts_client import synthesize
from vaaniseva.voice.audio_utils import strip_data_uri, detect_lang_from_text
from vaaniseva.models import CallTurnResponse

logger = logging.getLogger(__name__)


class CallSession:
    """Manages state for a single call."""

    def __init__(
        self,
        call_id: str,
        customer: dict,
        loans: list[dict],
        language: str = "hi",
        agent_name: str = "VaaniSeva Agent",
        call_purpose: str = "LOAN_RECOVERY",
    ):
        self.call_id = call_id
        self.customer = customer
        self.loans = loans
        self.language = language
        self.agent_name = agent_name
        self.call_purpose = call_purpose
        self.stage = CallStage.GREETING
        self.conversation: list[dict] = []  # {"role": ..., "content": ...}
        self.transcript: list[dict] = []  # Full transcript with metadata
        self.turn_count = 0
        self.outcome = None
        self.is_ended = False
        self.started_at = datetime.utcnow().isoformat()
        self.context_used: list[dict] = []  # RAG/SQL context for live view

    @property
    def primary_loan(self) -> dict:
        """Get the most overdue loan for this customer."""
        if not self.loans:
            return {}
        return max(self.loans, key=lambda l: l.get("days_overdue", 0))

    def _prompt_kwargs(self, rag_context: str = "") -> dict:
        """Build template kwargs for system prompts."""
        loan = self.primary_loan
        existing_loans = ", ".join(
            f"{l.get('loan_type')} (₹{l.get('emi_amount', 0):,.0f}/mo)"
            for l in self.loans
        ) or "None"
        return {
            "agent_name": self.agent_name,
            "customer_name": self.customer.get("name", "Customer"),
            "account_last4": self.customer.get("account_last4", "****"),
            "customer_city": self.customer.get("city", ""),
            "risk_tier": self.customer.get("risk_tier", "MEDIUM"),
            "existing_loans": existing_loans,
            "loan_type": loan.get("loan_type", "Personal"),
            "overdue_amount": f"{loan.get('overdue_amount', 0):,.0f}",
            "days_overdue": loan.get("days_overdue", 0),
            "emi_amount": f"{loan.get('emi_amount', 0):,.0f}",
            "rag_context": rag_context or "No additional context available.",
        }

    def generate_greeting(self) -> tuple[str, str | None]:
        """Generate the opening greeting. Returns (text, audio_b64)."""
        name = self.customer.get("name", "Customer")

        # Scripted greetings per purpose — no LLM needed, natural and consistent
        greetings = {
            "LOAN_RECOVERY": f"Namaste {name} ji, main VaaniSeva se Ria bol rahi hoon. Aapke loan account ke regarding ek important update hai. Kya aap abhi baat kar sakte hain?",
            "PRODUCT_OFFERING": f"Namaste {name} ji, main VaaniSeva se Ria bol rahi hoon. Aapke liye ek special offer hai jo aapke profile ke hisaab se taiyaar kiya gaya hai. Kya aapke paas do minute hain?",
            "SERVICE_FOLLOWUP": f"Namaste {name} ji, main VaaniSeva se Ria bol rahi hoon. Aapki recent loan experience ke baare mein feedback lena chahti thi. Kya aap apna experience share kar sakte hain?",
        }
        greeting = greetings.get(self.call_purpose, greetings["LOAN_RECOVERY"])
        audio = synthesize(greeting, self.language)
        self.conversation.append({"role": "assistant", "content": greeting})
        self.transcript.append({
            "speaker": "agent",
            "text": greeting,
            "timestamp": datetime.utcnow().isoformat(),
            "stage": self.stage,
        })
        return greeting, audio

    def process_turn(
        self,
        audio_b64: str | None = None,
        text: str | None = None,
        rag_context: str = "",
        sql_context: list[dict] | None = None,
    ) -> CallTurnResponse:
        """
        Process one turn of the conversation.

        Either audio_b64 or text must be provided.
        """
        if self.is_ended:
            return CallTurnResponse(
                call_id=self.call_id,
                customer_text="",
                agent_text="Call has ended.",
                stage=self.stage,
                is_ended=True,
                outcome=self.outcome,
            )

        # Step 1: Get customer text (STT or direct text)
        if audio_b64:
            audio_b64 = strip_data_uri(audio_b64)
            customer_text, detected_lang = transcribe(audio_b64)
            if detected_lang and detected_lang != "unknown":
                self.language = detected_lang
        elif text:
            customer_text = text
            detected_lang = detect_lang_from_text(text)
            if detected_lang:
                self.language = detected_lang
        else:
            raise ValueError("Either audio_b64 or text must be provided")

        if not customer_text.strip():
            return CallTurnResponse(
                call_id=self.call_id,
                customer_text="",
                agent_text="Mujhe samajh nahi aaya. Kya aap dobara bol sakte hain?",
                stage=self.stage,
            )

        self.turn_count += 1

        # Record customer turn
        self.conversation.append({"role": "user", "content": customer_text})
        self.transcript.append({
            "speaker": "customer",
            "text": customer_text,
            "timestamp": datetime.utcnow().isoformat(),
            "stage": self.stage,
        })

        # Step 2: Check escalation
        escalate, reason = should_escalate(
            customer_text, self.conversation, self.stage, self.turn_count
        )
        if escalate:
            self.stage = CallStage.ESCALATION
            self.outcome = "ESCALATED"

        # Step 3: Advance stage based on conversation progress
        if not escalate:
            self._maybe_advance_stage(customer_text)

        # Step 4: Build context for live view
        self.context_used = []
        if rag_context:
            self.context_used.append({"type": "RAG", "content": rag_context[:500]})
        if sql_context:
            self.context_used.append({"type": "SQL", "content": str(sql_context)[:500]})

        # Step 5: Get agent response
        prompt_kwargs = self._prompt_kwargs(rag_context=rag_context)
        system_prompt = get_prompt(self.stage, call_purpose=self.call_purpose, **prompt_kwargs)
        agent_text = call_llm(
            system_prompt=system_prompt,
            messages=self.conversation,
            max_tokens=300,
        )

        # Step 6: TTS
        audio = synthesize(agent_text, self.language)

        # Record agent turn
        self.conversation.append({"role": "assistant", "content": agent_text})
        self.transcript.append({
            "speaker": "agent",
            "text": agent_text,
            "timestamp": datetime.utcnow().isoformat(),
            "stage": self.stage,
        })

        # Check if call should end
        if self.stage in (CallStage.CLOSING, CallStage.ESCALATION):
            self.is_ended = True

        return CallTurnResponse(
            call_id=self.call_id,
            customer_text=customer_text,
            agent_text=agent_text,
            agent_audio_b64=audio,
            stage=self.stage,
            context_used=self.context_used,
            is_ended=self.is_ended,
            outcome=self.outcome,
        )

    def _maybe_advance_stage(self, customer_text: str):
        """Heuristic stage advancement based on conversation context."""
        text_lower = customer_text.lower()
        current_idx = CALL_STAGE_ORDER.index(self.stage) if self.stage in CALL_STAGE_ORDER else 0

        if self.stage == CallStage.GREETING:
            # Customer responded to greeting — advance to next stage
            # Any meaningful response means they're on the line
            if len(text_lower) > 2 or any(w in text_lower for w in [
                "haan", "yes", "ji", "bol", "speaking", "main", "batao", "boliye",
                "bataiye", "tell", "kya", "kaun", "hello", "hi", "namaste",
                "बताइए", "हां", "जी", "बोलिए", "हाँ",
            ]):
                self.stage = CallStage.IDENTITY_VERIFICATION

        elif self.stage == CallStage.IDENTITY_VERIFICATION:
            # Any response advances — for phone calls, caller ID is sufficient
            if len(text_lower) > 1:
                self.stage = CallStage.PURPOSE

        elif self.stage == CallStage.PURPOSE:
            # After purpose is stated, customer's response moves to negotiation
            if self.turn_count >= 2:
                self.stage = CallStage.NEGOTIATION

        elif self.stage == CallStage.NEGOTIATION:
            # Customer agrees to something
            agreement_words = ["theek hai", "ok", "haan", "agreed", "done", "kar dunga", "kar deti", "pay", "bhej"]
            if any(w in text_lower for w in agreement_words):
                self.stage = CallStage.RESOLUTION

        elif self.stage == CallStage.RESOLUTION:
            # After resolution confirmed, close
            self.stage = CallStage.CLOSING

    def end_call(self, outcome: str | None = None, notes: str | None = None) -> dict:
        """End the call and return summary."""
        self.is_ended = True
        if outcome:
            self.outcome = outcome
        return {
            "call_id": self.call_id,
            "customer_id": self.customer.get("id"),
            "customer_name": self.customer.get("name"),
            "stage_reached": self.stage,
            "outcome": self.outcome,
            "turn_count": self.turn_count,
            "language": self.language,
            "started_at": self.started_at,
            "ended_at": datetime.utcnow().isoformat(),
            "transcript": self.transcript,
            "notes": notes,
        }


# In-memory session store (per-process)
_sessions: dict[str, CallSession] = {}


def create_session(
    customer: dict,
    loans: list[dict],
    language: str = "hi",
    agent_name: str = "VaaniSeva Agent",
    call_purpose: str = "LOAN_RECOVERY",
) -> CallSession:
    """Create a new call session."""
    call_id = str(uuid.uuid4())[:8]
    session = CallSession(
        call_id=call_id,
        customer=customer,
        loans=loans,
        language=language,
        agent_name=agent_name,
        call_purpose=call_purpose,
    )
    _sessions[call_id] = session
    return session


def get_session(call_id: str) -> CallSession | None:
    """Get an existing call session."""
    return _sessions.get(call_id)


def remove_session(call_id: str):
    """Remove a call session from memory."""
    _sessions.pop(call_id, None)

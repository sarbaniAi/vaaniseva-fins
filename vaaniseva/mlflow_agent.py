"""VaaniSeva MLflow Agent — wraps the call flow as an MLflow pyfunc model.

Supports:
- MLflow model registry (UC)
- MLflow tracing (auto-logged spans for STT, LLM, TTS)
- MLflow evaluate() for quality assessment
"""

import json
import logging
import os
import re

import mlflow
import requests

logger = logging.getLogger(__name__)

# Sarvam config
SARVAM_API_KEY = os.environ.get("SARVAM_API_KEY", "")
SARVAM_API_BASE = "https://api.sarvam.ai"
SARVAM_LLM_MODEL = "sarvam-m"


class VaaniSevaAgent(mlflow.pyfunc.PythonModel):
    """MLflow-compatible VaaniSeva collections agent.

    Input: {"messages": [...], "custom_inputs": {"call_purpose": "...", "customer_context": "..."}}
    Output: {"choices": [{"message": {"role": "assistant", "content": "..."}}], "custom_outputs": {...}}
    """

    def load_context(self, context):
        """Called when the model is loaded."""
        self.sarvam_api_key = os.environ.get("SARVAM_API_KEY", "")

    @mlflow.trace(name="vaaniseva_predict")
    def predict(self, context, model_input, params=None):
        """Process a single turn of conversation.

        Args:
            model_input: dict or DataFrame with columns:
                - messages: list of {"role": str, "content": str}
                - custom_inputs (optional): {"call_purpose": str, "customer_context": str}
        """
        # Handle DataFrame input
        if hasattr(model_input, "to_dict"):
            rows = model_input.to_dict(orient="records")
            return [self._process_single(r) for r in rows]

        return self._process_single(model_input)

    def _process_single(self, input_data):
        """Process a single request."""
        if isinstance(input_data, str):
            input_data = json.loads(input_data)

        messages = input_data.get("messages", [])
        custom = input_data.get("custom_inputs", {})
        call_purpose = custom.get("call_purpose", "LOAN_RECOVERY")
        customer_context = custom.get("customer_context", "")

        # Build system prompt based on purpose
        system_prompt = self._get_system_prompt(call_purpose, customer_context)

        # Call LLM
        agent_response = self._call_llm(system_prompt, messages)

        return {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": agent_response,
                }
            }],
            "custom_outputs": {
                "call_purpose": call_purpose,
                "model": SARVAM_LLM_MODEL,
            },
        }

    @mlflow.trace(name="sarvam_llm_call", span_type="LLM")
    def _call_llm(self, system_prompt, messages):
        """Call Sarvam-105B LLM with MLflow tracing."""
        # Strip leading assistant messages (Sarvam requirement)
        trimmed = list(messages)
        while trimmed and trimmed[0].get("role") == "assistant":
            trimmed.pop(0)

        if not trimmed:
            trimmed = [{"role": "user", "content": "Begin the conversation."}]

        full_messages = [{"role": "system", "content": system_prompt}] + trimmed

        resp = requests.post(
            f"{SARVAM_API_BASE}/v1/chat/completions",
            headers={
                "api-subscription-key": self.sarvam_api_key or SARVAM_API_KEY,
                "Content-Type": "application/json",
            },
            json={
                "model": SARVAM_LLM_MODEL,
                "messages": full_messages,
                "max_tokens": 300,
                "temperature": 0.7,
            },
            timeout=30,
        )

        if resp.status_code != 200:
            raise RuntimeError(f"Sarvam API error {resp.status_code}: {resp.text[:300]}")

        content = resp.json()["choices"][0]["message"]["content"]
        # Strip <think> blocks
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        return content

    def _get_system_prompt(self, call_purpose, customer_context=""):
        """Get a concise system prompt for the given purpose."""
        base = (
            "You are Ria, a friendly female agent at VaaniSeva, an Indian NBFC. "
            "Output ONLY what you would SAY on the phone. No reasoning, no explanations. "
            "Respond in the SAME language the customer speaks. "
            "Keep responses to 1-2 short sentences. Use 'ji' respectfully. "
            "Follow RBI Fair Practices Code.\n"
        )

        purpose_prompts = {
            "LOAN_RECOVERY": (
                base + "PURPOSE: You are calling about an overdue EMI payment. "
                "Be empathetic but clear about the overdue amount. "
                "Offer resolution: immediate payment, partial payment, or EMI restructuring. "
                "Never threaten or intimidate.\n"
            ),
            "PRODUCT_OFFERING": (
                base + "PURPOSE: You are calling to offer a pre-approved financial product. "
                "Be consultative, match recommendations to customer profile. "
                "If not interested, respect their decision gracefully.\n"
            ),
            "SERVICE_FOLLOWUP": (
                base + "PURPOSE: You are calling for a service followup / satisfaction check. "
                "Ask about their experience, collect feedback (1-10), resolve concerns.\n"
            ),
        }

        prompt = purpose_prompts.get(call_purpose, purpose_prompts["LOAN_RECOVERY"])
        if customer_context:
            prompt += f"\nCUSTOMER CONTEXT:\n{customer_context}\n"
        return prompt

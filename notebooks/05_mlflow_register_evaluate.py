# Databricks notebook source
# MAGIC %md
# MAGIC # VaaniSeva — MLflow Agent Registration & Evaluation
# MAGIC
# MAGIC Registers VaaniSeva as an MLflow model in Unity Catalog and runs evaluations.

# COMMAND ----------

# MAGIC %pip install mlflow>=2.18.0 databricks-sdk requests
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

import os
import mlflow

# Configuration
CATALOG = "sarbanimaiti_catalog"
SCHEMA = "vaaniseva"
MODEL_NAME = f"{CATALOG}.{SCHEMA}.vaaniseva_agent"
EXPERIMENT_NAME = f"/Users/{spark.sql('SELECT current_user()').first()[0]}/vaaniseva_experiment"

mlflow.set_registry_uri("databricks-uc")
mlflow.set_experiment(EXPERIMENT_NAME)
print(f"Model: {MODEL_NAME}")
print(f"Experiment: {EXPERIMENT_NAME}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1: Log the agent model

# COMMAND ----------

import sys
sys.path.insert(0, "/Workspace/Users/sarbani.maiti@databricks.com/sarvam-voice-agent")

from vaaniseva.mlflow_agent import VaaniSevaAgent

# COMMAND ----------

# Infer signature from a real prediction
from mlflow.models.signature import infer_signature

input_example = {
    "messages": [
        {"role": "user", "content": "Haan, main Rajesh bol raha hoon"}
    ],
    "custom_inputs": {
        "call_purpose": "LOAN_RECOVERY",
        "customer_context": "Customer: Rajesh Kumar, Overdue: ₹37,500, 45 days, Personal Loan"
    }
}

agent = VaaniSevaAgent()
agent.load_context(None)
output_example = agent.predict(None, input_example)
signature = infer_signature(input_example, output_example)
print("Signature inferred successfully")

# COMMAND ----------

with mlflow.start_run(run_name="vaaniseva_agent_v1") as run:
    mlflow.pyfunc.log_model(
        artifact_path="vaaniseva_agent",
        python_model=VaaniSevaAgent(),
        signature=signature,
        pip_requirements=[
            "mlflow>=2.18.0",
            "requests>=2.31.0",
        ],
        input_example=input_example,
        registered_model_name=MODEL_NAME,
        tags={
            "domain": "BFSI",
            "use_case": "outbound_collections",
            "llm": "sarvam-105b",
            "languages": "hi,en,ta,te,kn,ml,bn,gu,mr,pa,od",
            "sovereignty": "india-hosted",
        },
    )

    mlflow.log_params({
        "llm_model": "sarvam-m",
        "llm_provider": "sarvam_ai",
        "max_tokens": 300,
        "temperature": 0.7,
        "call_purposes": "LOAN_RECOVERY,PRODUCT_OFFERING,SERVICE_FOLLOWUP",
        "stt_model": "saaras:v3",
        "tts_model": "bulbul:v2",
    })

    print(f"Run ID: {run.info.run_id}")
    print(f"Model registered: {MODEL_NAME}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2: Test the registered model

# COMMAND ----------

import mlflow

# Load the model
model = mlflow.pyfunc.load_model(f"models:/{MODEL_NAME}/1")

# Test with loan recovery scenario
result = model.predict({
    "messages": [
        {"role": "user", "content": "Haan boliye, kaun bol raha hai?"}
    ],
    "custom_inputs": {
        "call_purpose": "LOAN_RECOVERY",
        "customer_context": "Customer: Rajesh Kumar, Delhi. Personal Loan overdue ₹37,500 for 45 days. EMI: ₹12,500."
    }
})

print("Agent response:", result["choices"][0]["message"]["content"])

# COMMAND ----------

# Test product offering
result2 = model.predict({
    "messages": [
        {"role": "user", "content": "Yes, speaking. What is this about?"}
    ],
    "custom_inputs": {
        "call_purpose": "PRODUCT_OFFERING",
        "customer_context": "Customer: Amit Patel, Ahmedabad. Good payment history. Existing: Personal Loan ₹6,000/mo. Risk: LOW."
    }
})

print("Agent response:", result2["choices"][0]["message"]["content"])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3: Build evaluation dataset

# COMMAND ----------

import pandas as pd

# Evaluation scenarios covering all 3 call purposes
eval_data = pd.DataFrame([
    # Loan Recovery scenarios
    {
        "inputs": '{"messages": [{"role": "user", "content": "Haan, main Rajesh bol raha hoon. Kya baat hai?"}], "custom_inputs": {"call_purpose": "LOAN_RECOVERY", "customer_context": "Customer: Rajesh Kumar, Delhi. Personal Loan overdue ₹37,500 for 45 days."}}',
        "ground_truth": "Agent should acknowledge identity, verify with last 4 digits, then disclose overdue amount respectfully.",
        "category": "loan_recovery",
    },
    {
        "inputs": '{"messages": [{"role": "user", "content": "Mujhe paise nahi hain, main job kho chuka hoon"}], "custom_inputs": {"call_purpose": "LOAN_RECOVERY", "customer_context": "Customer: Sunita Devi, Lucknow. Gold Loan overdue ₹25,500 for 90 days."}}',
        "ground_truth": "Agent should show empathy, acknowledge hardship, and offer EMI restructuring or moratorium option.",
        "category": "loan_recovery_hardship",
    },
    {
        "inputs": '{"messages": [{"role": "user", "content": "Main supervisor se baat karna chahta hoon"}], "custom_inputs": {"call_purpose": "LOAN_RECOVERY", "customer_context": "Customer: Vikram Singh, Jaipur. Business Loan overdue ₹135,000 for 75 days."}}',
        "ground_truth": "Agent should acknowledge escalation request, offer supervisor callback within 4 hours, and document the request.",
        "category": "escalation",
    },
    {
        "inputs": '{"messages": [{"role": "user", "content": "Theek hai, main kal tak ₹20,000 bhej dunga"}], "custom_inputs": {"call_purpose": "LOAN_RECOVERY", "customer_context": "Customer: Deepak Verma, Bhopal. Business Loan overdue ₹105,000 for 85 days."}}',
        "ground_truth": "Agent should confirm the partial payment commitment, mention remaining balance, and confirm next steps.",
        "category": "resolution",
    },
    # Product Offering scenarios
    {
        "inputs": '{"messages": [{"role": "user", "content": "Haan boliye, kya offer hai?"}], "custom_inputs": {"call_purpose": "PRODUCT_OFFERING", "customer_context": "Customer: Amit Patel, Ahmedabad. Good payment history. Risk: LOW. Existing: Personal Loan ₹6,000/mo."}}',
        "ground_truth": "Agent should warmly present a relevant pre-approved product based on customer profile, such as home loan or credit card.",
        "category": "product_offering",
    },
    {
        "inputs": '{"messages": [{"role": "user", "content": "Nahi, mujhe koi loan nahi chahiye abhi"}], "custom_inputs": {"call_purpose": "PRODUCT_OFFERING", "customer_context": "Customer: Geeta Bhat, Bangalore. Risk: LOW."}}',
        "ground_truth": "Agent should respect the customer decision gracefully, offer to send details for future reference, and close politely.",
        "category": "product_offering_rejection",
    },
    {
        "inputs": '{"messages": [{"role": "user", "content": "Interest rate kya hoga? Aur kitna time lagega?"}], "custom_inputs": {"call_purpose": "PRODUCT_OFFERING", "customer_context": "Customer: Sandeep Jain, Ahmedabad. Interested in pre-approved personal loan."}}',
        "ground_truth": "Agent should provide interest rate range (10.49-24%), tenure options (12-60 months), and explain the quick approval process.",
        "category": "product_details",
    },
    # Service Followup scenarios
    {
        "inputs": '{"messages": [{"role": "user", "content": "Haan, loan process smooth tha, but app mein kuch dikkat aa rahi hai"}], "custom_inputs": {"call_purpose": "SERVICE_FOLLOWUP", "customer_context": "Customer: Kavita Nair, Kochi. Home Loan disbursed recently."}}',
        "ground_truth": "Agent should acknowledge positive feedback, ask for details about the app issue, and offer to log a complaint or provide workaround.",
        "category": "service_followup",
    },
    {
        "inputs": '{"messages": [{"role": "user", "content": "7 out of 10. Documentation process bahut lamba tha"}], "custom_inputs": {"call_purpose": "SERVICE_FOLLOWUP", "customer_context": "Customer: Manoj Tiwari, Varanasi. Education Loan."}}',
        "ground_truth": "Agent should thank for the rating, acknowledge the documentation concern, and note the feedback for improvement.",
        "category": "service_feedback",
    },
    # Multilingual scenarios
    {
        "inputs": '{"messages": [{"role": "user", "content": "Naan Pooja pesuren. Enna vishayam?"}], "custom_inputs": {"call_purpose": "LOAN_RECOVERY", "customer_context": "Customer: Pooja Iyer, Chennai. Education Loan overdue ₹12,000 for 18 days. Language: Tamil."}}',
        "ground_truth": "Agent should respond in Tamil, verify identity, and then disclose the overdue EMI respectfully.",
        "category": "multilingual_tamil",
    },
])

display(eval_data)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4: Run MLflow Evaluate

# COMMAND ----------

# Load model for evaluation
model_uri = f"models:/{MODEL_NAME}/1"

with mlflow.start_run(run_name="vaaniseva_evaluation_v1") as eval_run:
    eval_results = mlflow.evaluate(
        model=model_uri,
        data=eval_data,
        targets="ground_truth",
        model_type="question-answering",
        evaluators="default",
        extra_metrics=[],
        evaluator_config={
            "col_mapping": {
                "inputs": "inputs",
                "targets": "ground_truth",
            }
        },
    )

    print(f"\nEvaluation Results:")
    print(f"Metrics: {eval_results.metrics}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5: Custom LLM-as-Judge Evaluation (Collections Quality)

# COMMAND ----------

from mlflow.metrics.genai import make_genai_metric

# Custom metric: RBI Compliance Score
rbi_compliance = make_genai_metric(
    name="rbi_compliance",
    definition=(
        "Evaluate whether the agent's response follows RBI Fair Practices Code for debt collection. "
        "The agent should: (1) Not threaten or intimidate, (2) Be respectful, "
        "(3) Not disclose debt to third parties, (4) Offer viable resolution options."
    ),
    grading_prompt=(
        "Score the agent response from 1-5 on RBI compliance:\n"
        "5: Fully compliant, respectful, offers solutions\n"
        "4: Mostly compliant, minor gaps\n"
        "3: Partially compliant, some concerns\n"
        "2: Multiple compliance issues\n"
        "1: Clearly non-compliant (threats, intimidation, privacy breach)\n\n"
        "Agent response: {output}\n"
        "Expected behavior: {targets}\n"
    ),
    model="endpoints:/databricks-claude-sonnet-4",
    parameters={"temperature": 0.0},
    aggregations=["mean", "min"],
    greater_is_better=True,
)

# Custom metric: Empathy & Tone
empathy_tone = make_genai_metric(
    name="empathy_tone",
    definition=(
        "Evaluate the agent's empathy and tone. The agent should acknowledge customer feelings, "
        "use respectful language (ji suffix), and adapt tone based on customer's emotional state."
    ),
    grading_prompt=(
        "Score the agent response from 1-5 on empathy and tone:\n"
        "5: Highly empathetic, warm, respectful\n"
        "4: Good empathy, appropriate tone\n"
        "3: Neutral tone, minimal empathy\n"
        "2: Cold or dismissive\n"
        "1: Rude, aggressive, or threatening\n\n"
        "Agent response: {output}\n"
        "Expected behavior: {targets}\n"
    ),
    model="endpoints:/databricks-claude-sonnet-4",
    parameters={"temperature": 0.0},
    aggregations=["mean", "min"],
    greater_is_better=True,
)

# Custom metric: Language Consistency
language_quality = make_genai_metric(
    name="language_quality",
    definition=(
        "Evaluate whether the agent responds in the same language as the customer "
        "and maintains clear, voice-friendly output (concise, no jargon)."
    ),
    grading_prompt=(
        "Score from 1-5 on language quality:\n"
        "5: Same language as customer, concise, voice-ready\n"
        "4: Correct language, mostly concise\n"
        "3: Correct language but too verbose or has jargon\n"
        "2: Wrong language or confusing code-mix\n"
        "1: Completely wrong language or unintelligible\n\n"
        "Agent response: {output}\n"
        "Expected behavior: {targets}\n"
    ),
    model="endpoints:/databricks-claude-sonnet-4",
    parameters={"temperature": 0.0},
    aggregations=["mean", "min"],
    greater_is_better=True,
)

# COMMAND ----------

with mlflow.start_run(run_name="vaaniseva_custom_eval_v1") as custom_eval_run:
    custom_results = mlflow.evaluate(
        model=model_uri,
        data=eval_data,
        targets="ground_truth",
        model_type="question-answering",
        extra_metrics=[rbi_compliance, empathy_tone, language_quality],
        evaluator_config={
            "col_mapping": {
                "inputs": "inputs",
                "targets": "ground_truth",
            }
        },
    )

    print("\nCustom Evaluation Results:")
    for k, v in custom_results.metrics.items():
        print(f"  {k}: {v}")

# COMMAND ----------

# View per-row results
display(custom_results.tables["eval_results_table"])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary
# MAGIC
# MAGIC | Resource | Location |
# MAGIC |----------|----------|
# MAGIC | **Model** | `sarbanimaiti_catalog.vaaniseva.vaaniseva_agent` (UC) |
# MAGIC | **Experiment** | `vaaniseva_experiment` |
# MAGIC | **Eval Metrics** | RBI Compliance, Empathy/Tone, Language Quality |
# MAGIC | **10 eval scenarios** | Loan Recovery, Product Offering, Service Followup, Multilingual |

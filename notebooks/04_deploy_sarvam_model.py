# Databricks notebook source
# MAGIC %md
# MAGIC # VaaniSeva — Deploy Sarvam-30B on Model Serving
# MAGIC
# MAGIC This notebook deploys the Sarvam-30B model on Databricks Model Serving
# MAGIC as a fallback LLM for sovereignty story.
# MAGIC
# MAGIC **Note:** This reuses the deployment from the Yatra voice agent project.
# MAGIC If `sarvam-30b-serving` is already running, skip this notebook.

# COMMAND ----------

# MAGIC %pip install databricks-sdk mlflow
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

from databricks.sdk import WorkspaceClient
w = WorkspaceClient()

ENDPOINT_NAME = "sarvam-30b-serving"
CATALOG = "sarbanimaiti_catalog"
SCHEMA = "sarvam_voice_agent"
MODEL = "sarvam_30b"

# COMMAND ----------

# MAGIC %md
# MAGIC ## Check if endpoint already exists

# COMMAND ----------

try:
    ep = w.serving_endpoints.get(ENDPOINT_NAME)
    state = ep.state.ready if ep.state else "UNKNOWN"
    print(f"Endpoint '{ENDPOINT_NAME}' exists. State: {state}")
    print(f"URL: {ep.config.served_entities[0].entity_name if ep.config.served_entities else 'N/A'}")
    print("\nEndpoint is already deployed! You can skip the rest of this notebook.")
except Exception:
    print(f"Endpoint '{ENDPOINT_NAME}' does not exist. Create it below.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Deploy (if needed)
# MAGIC
# MAGIC Sarvam-30B is available in the Databricks Marketplace or can be registered
# MAGIC as a custom model. The deployment from the Yatra project should already be active.
# MAGIC
# MAGIC If you need to deploy fresh:
# MAGIC
# MAGIC 1. **Option A: Marketplace** — Search "Sarvam" in the Databricks Marketplace
# MAGIC 2. **Option B: Custom deploy** — Download weights and register with MLflow
# MAGIC
# MAGIC For the Buildathon, the primary LLM is Sarvam-105B via API (free tier, 128K context).
# MAGIC The 30B endpoint is the sovereignty fallback story.

# COMMAND ----------

# Test the endpoint (if it exists)
import requests
import os

host = os.environ.get("DATABRICKS_HOST", "")
token = os.environ.get("DATABRICKS_TOKEN", "")

if host and token:
    try:
        resp = requests.post(
            f"{host}/serving-endpoints/{ENDPOINT_NAME}/invocations",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "Say hello in Hindi."}
                ],
                "max_tokens": 50,
            },
            timeout=30,
        )
        if resp.status_code == 200:
            print("Endpoint test successful!")
            print(resp.json()["choices"][0]["message"]["content"])
        else:
            print(f"Endpoint returned {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"Test failed: {e}")
else:
    print("Set DATABRICKS_HOST and DATABRICKS_TOKEN to test the endpoint.")

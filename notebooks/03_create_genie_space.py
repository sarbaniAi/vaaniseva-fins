# Databricks notebook source
# MAGIC %md
# MAGIC # VaaniSeva — Genie Space Setup Guide
# MAGIC
# MAGIC This notebook guides you through setting up a Genie Space for natural language to SQL
# MAGIC queries over the VaaniSeva loan data. The Genie Space is a **showcase feature** for judges —
# MAGIC the agent uses direct SQL for live calls.
# MAGIC
# MAGIC ## Steps (Manual via UI)
# MAGIC
# MAGIC 1. **Create a SQL Warehouse** (if you don't have one)
# MAGIC    - Go to SQL Warehouses → Create
# MAGIC    - Size: 2X-Small (for demo)
# MAGIC
# MAGIC 2. **Create Genie Space**
# MAGIC    - Go to Genie → New Space
# MAGIC    - Name: "VaaniSeva Loan Data Explorer"
# MAGIC    - Description: "Ask questions about customer loans, payment history, and collections data"
# MAGIC    - Add tables:
# MAGIC      - `vaaniseva.customer_profiles`
# MAGIC      - `vaaniseva.loan_accounts`
# MAGIC      - `vaaniseva.call_logs`
# MAGIC      - `vaaniseva.quality_scores`
# MAGIC
# MAGIC 3. **Add Instructions to Genie Space**
# MAGIC    ```
# MAGIC    You are a data assistant for VaaniSeva, an Indian BFSI collections system.
# MAGIC    Key tables:
# MAGIC    - customer_profiles: Customer info (name, city, language, risk_tier)
# MAGIC    - loan_accounts: Loan details (type, EMI, overdue_amount, days_overdue)
# MAGIC    - call_logs: Collection call records (outcome, stage, turn_count)
# MAGIC    - quality_scores: AI quality audit scores per call
# MAGIC
# MAGIC    Common questions:
# MAGIC    - Which customers have the highest overdue amounts?
# MAGIC    - What's the average quality score by language?
# MAGIC    - How many calls resulted in promise-to-pay?
# MAGIC    - Show me the top 10 overdue loans by city
# MAGIC    ```
# MAGIC
# MAGIC 4. **Test with sample queries:**
# MAGIC    - "Show me all customers in Mumbai with overdue loans"
# MAGIC    - "What is the total overdue amount by loan type?"
# MAGIC    - "Which agents have the highest quality scores?"
# MAGIC
# MAGIC 5. **Copy the Genie Space ID** from the URL:
# MAGIC    `https://<workspace>/genie/rooms/<SPACE_ID>`
# MAGIC
# MAGIC 6. **Update app.yaml:**
# MAGIC    ```yaml
# MAGIC    - name: GENIE_SPACE_ID
# MAGIC      value: "<your-space-id>"
# MAGIC    ```

# COMMAND ----------

# You can also create Genie Space programmatically:
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# List existing Genie Spaces
# spaces = w.genie.list_spaces()
# for s in spaces:
#     print(f"{s.space_id}: {s.title}")

print("Follow the manual steps above to create the Genie Space via UI.")
print("This provides the best demo experience for judges.")

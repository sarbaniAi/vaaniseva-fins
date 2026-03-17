# VaaniSeva — Sovereign AI Voice Agent for Indian BFSI Collections

**APJ Industries Buildathon 2026** | Sovereign AI + Databricks Platform

## Target Industry
Indian Banking, Financial Services & Insurance (BFSI) — specifically Non-Banking Financial Companies (NBFCs) like Bajaj Finance, Shriram Finance, and Muthoot Finance.

## Problem
Indian NBFCs make millions of outbound collections calls monthly. Current systems lack:
- Multilingual capability (India has 22 official languages)
- Compliance monitoring against RBI Fair Practices Code
- Real-time quality assurance
- Data sovereignty (data must stay in India)

## Solution
VaaniSeva is a sovereign AI voice agent that:
1. **Conducts collections calls** in the customer's preferred language (Hindi, English, Tamil, Telugu, and 7 more)
2. **Follows a structured call flow**: Greeting → Identity Verification → Purpose → Negotiation → Resolution → Closing
3. **Retrieves context in real-time**: RBI policies via Vector Search, loan data via SQL
4. **Scores every call** against a 5-category compliance rubric using LLM evaluation

## Architecture

| Component | Technology | Location |
|-----------|-----------|----------|
| Speech-to-Text | Sarvam Saaras v3 | India |
| Text-to-Speech | Sarvam Bulbul v3 | India |
| Agent Brain (primary) | Sarvam-105B API | India |
| Agent Brain (fallback) | Sarvam-30B on Databricks | India |
| Database | Databricks Lakebase (Postgres) | India |
| Knowledge Retrieval | UC Vector Search | India |
| Structured Data | Direct SQL via Lakebase | India |
| App Platform | Databricks Apps | India |

**Zero data leaves India. Full data sovereignty.**

## Databricks Features Used
- **Lakebase**: PostgreSQL-compatible database for customer/loan data, call logs, quality scores
- **UC Vector Search**: Policy documents and FAQ retrieval for RAG
- **Model Serving**: Sarvam-30B self-hosted LLM (sovereignty fallback)
- **Databricks Apps**: Full-stack deployment with FastAPI
- **DAB (Databricks Asset Bundles)**: One-command deployment
- **Genie Space**: Natural language data exploration (showcase)

## 3 Persona Views

1. **Customer Simulator**: Select a customer, start a voice/text call, interact with the agent
2. **Agent Live View**: Real-time transcript, call stage visualization, RAG/SQL context panel
3. **Quality Auditor**: Compliance scoring dashboard, rubric breakdown, batch audit runner

## Deployment

```bash
# 1. Configure Databricks CLI
databricks configure

# 2. Deploy the bundle
databricks bundle deploy -t dev

# 3. Run setup notebooks (in workspace)
# - 00_setup_lakebase.py     → Create tables
# - 01_generate_synthetic_data.py → Seed data
# - 02_setup_vector_search.py    → Create VS index
# - 04_deploy_sarvam_model.py    → Check/deploy Sarvam-30B

# 4. Update app.yaml with your Lakebase host, VS endpoint, etc.

# 5. Redeploy
databricks bundle deploy -t dev
```

Target deployment time: **<15 minutes** on a clean FEVM workspace.

## Data Requirements
- Sarvam AI API key (free tier available)
- Databricks workspace with Unity Catalog
- Lakebase instance
- Vector Search endpoint

## Known Limitations
- Audio is REST-based (not WebSocket streaming) — acceptable for demo
- Single-process session store (sufficient for demo scale)
- Sarvam-105B free tier has rate limits
- Browser mic access requires HTTPS (Databricks Apps provides this)

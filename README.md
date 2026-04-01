# VaaniSeva — Sovereign AI Voice & WhatsApp Agent for Indian BFSI Collections

**Databricks + Sarvam AI + Twilio** | 100% Data Sovereignty on Indian Infrastructure

---

## What is VaaniSeva?

An AI-powered collections agent that conducts **voice calls** and **WhatsApp conversations** with loan customers in **22 Indian languages**. Built on Databricks Lakebase for real-time customer data, Sarvam AI for Indian language intelligence, and Twilio for telephony/messaging.

### Channels
- **Voice Calls** — Outbound collections calls with 7-stage call flow (Greeting → Verify → Purpose → Negotiate → Resolve → Close)
- **WhatsApp** — Interactive collections menu (payments, EMI details, restructuring, AI chat)

### Key Features
- Real-time customer data from **Databricks Lakebase** (sub-100ms queries)
- **Sarvam AI** STT/TTS/LLM for 22 Indian languages
- **5-category RBI compliance** quality scoring (LLM evaluator)
- 4 UI views: Customer Simulator, Agent Live View, Quality Auditor, WhatsApp

---

## Quick Start (30 min)

```bash
# 1. Clone
git clone https://github.com/sarbaniAi/vaaniseva-fins.git
cd vaaniseva-fins

# 2. Configure
cp env.template .env
# Edit .env with your Databricks, Sarvam, and Twilio credentials

# 3. Authenticate
databricks auth login --host <workspace-url> --profile DEFAULT

# 4. Setup & Deploy (Lakebase + data + app)
chmod +x setup.sh
./setup.sh

# 5. Manual: Configure Twilio Functions (see INSTALL.md Step 4)
```

**Full installation guide:** [INSTALL.md](INSTALL.md)

---

## Architecture

```
Customer Phone/WhatsApp
         │
    Twilio (Voice + WhatsApp)
         │
         ├── Voice: Inline TwiML (no webhooks needed)
         └── WhatsApp: Twilio Function relay (34 lines)
                  │ HTTPS + OAuth
                  ▼
         Databricks App (FastAPI)
                  │
         ┌───────┼───────┐
         ▼       ▼       ▼
    Lakebase  Sarvam AI  Model Serving
    (50 customers  (STT/TTS/  (propensity,
     80 loans)      LLM)       risk score)
```

| Component | Technology | Data Residency |
|-----------|-----------|---------------|
| App Platform | Databricks Apps (FastAPI) | Azure Central India |
| Database | Lakebase Autoscaling (PostgreSQL) | Azure |
| STT | Sarvam Saaras v3 (22 languages) | India |
| LLM | Sarvam-M (105B) / Sarvam-30B | India |
| TTS | Sarvam Bulbul v2 (11 voices) | India |
| Voice Calls | Twilio Programmable Voice | Global |
| WhatsApp | Twilio WhatsApp API | Global |
| Relay | Twilio Functions (serverless) | AWS |

---

## Databricks Products Used

| Product | Role |
|---------|------|
| **Lakebase** | Customer 360, loan data, call logs, quality scores |
| **Databricks Apps** | Full-stack FastAPI deployment with OAuth |
| **Model Serving** | Self-hosted Sarvam-30B (optional) |
| **DAB (Asset Bundles)** | One-command deployment |
| **UC Vector Search** | Policy/compliance RAG (optional) |
| **Genie Space** | NL-to-SQL showcase (optional) |

---

## Data Model (Lakebase)

| Table | Rows | Purpose |
|-------|------|---------|
| `customer_profiles` | 50 | Indian names, cities, languages, risk tiers |
| `loan_accounts` | ~80 | Personal, Home, Car, Education, Business, Gold |
| `payment_history` | ~600 | Payment records with modes and statuses |
| `call_queue` | 30 | Priority queue for outbound calls |
| `knowledge_base` | 30 | RBI compliance, scripts, policies |
| `call_logs` | dynamic | Transcripts, stages, outcomes |
| `quality_scores` | dynamic | 5-category RBI compliance scoring |

---

## Project Structure

```
├── setup.sh                    # One-command setup (Lakebase + data + deploy)
├── env.template                # Environment variable template
├── INSTALL.md                  # Detailed installation guide
├── app.py                      # FastAPI entrypoint
├── databricks.yml              # DAB bundle config
├── twilio_function.js          # WhatsApp relay (paste into Twilio Console)
├── twilio_audio_function.js    # Sarvam TTS relay (paste into Twilio Console)
├── scripts/                    # Setup helpers
├── notebooks/                  # Alternative: run setup in Databricks notebooks
├── vaaniseva/                  # Main Python package
│   ├── agent/                  # Call flow state machine + LLM
│   ├── audit/                  # Quality scoring (RBI rubric)
│   ├── retrieval/              # Lakebase queries + RAG
│   ├── voice/                  # Sarvam STT/TTS clients
│   └── routes/                 # FastAPI endpoints (voice, WhatsApp, customers, audit)
└── static/                     # Web UI (4 tabs)
```

---

## Known Limitations

- Voice latency is ~3.9s per turn (REST-based, not WebSocket streaming)
- Single-process session store (demo scale)
- Sarvam-M free tier has rate limits
- Twilio sandbox: 50 WhatsApp messages/day
- OAuth tokens expire hourly (manual refresh for Twilio Functions)

## Production Roadmap

See the [Design Patterns document](https://docs.google.com/document/d/1aVF7ZkYiMD5xOVVJMPsUwFwt1cqkfhVjSu769jPaa9c/edit) for recommended production patterns:
- **WebSocket streaming** with Pipecat + Exotel for <1.5s voice latency
- **BSP integration** (Gupshup/Kaleyra) for WhatsApp compliance
- **WhatsApp Flows** for structured payment journeys

---

## License

Internal use — Databricks Field Engineering

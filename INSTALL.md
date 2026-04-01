# VaaniSeva — Installation Guide

Complete guide to deploy VaaniSeva (Voice + WhatsApp BFSI Collections Agent) on a new Databricks workspace.

**Time estimate:** ~30 minutes (15 min automated + 15 min Twilio manual setup)

---

## Prerequisites

| Requirement | How to Get |
|------------|-----------|
| **Databricks Workspace** (Azure) | FE-VM or customer workspace with serverless enabled |
| **Databricks CLI v0.285+** | `brew install databricks` or [install docs](https://docs.databricks.com/dev-tools/cli/install.html) |
| **psql client** | `brew install postgresql@16` |
| **Python 3.10+** | `brew install python@3.12` |
| **Twilio Account** | [twilio.com/try-twilio](https://www.twilio.com/try-twilio) (free trial works) |
| **Sarvam AI API Key** | [dashboard.sarvam.ai](https://dashboard.sarvam.ai) (free tier: 100 calls/day) |

---

## Step 1: Clone & Configure (2 min)

```bash
git clone https://github.com/sarbaniAi/vaaniseva-fins.git
cd vaaniseva-fins

# Create your .env from template
cp env.template .env
```

Edit `.env` and fill in:
- `DATABRICKS_HOST` — your workspace URL (e.g., `https://adb-xxxx.yy.azuredatabricks.net`)
- `DATABRICKS_PROFILE` — CLI profile name
- `SARVAM_API_KEY` — from Sarvam dashboard
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER` — from Twilio Console

---

## Step 2: Authenticate Databricks CLI (1 min)

```bash
databricks auth login --host <your-workspace-url> --profile <profile-name>

# Verify
databricks current-user me -p <profile-name>
```

---

## Step 3: Run Automated Setup (10 min)

```bash
chmod +x setup.sh
./setup.sh
```

This will:
1. Create a Lakebase autoscaling project (`vaaniseva`)
2. Create the database and 7 tables
3. Seed 50 customers, ~80 loans, ~600 payments, 30 call queue entries, 30 KB docs
4. Generate `app.yaml.local` from your `.env`
5. Deploy the Databricks App via DAB

**Alternative: Run steps individually:**
```bash
./setup.sh --lakebase-only    # Just Lakebase
./setup.sh --data-only        # Just seed data
./setup.sh --deploy-only      # Just deploy app
```

**Alternative: Use notebooks (if psql is unavailable):**
1. Upload `notebooks/` to your Databricks workspace
2. Edit `CONN_HOST` in each notebook to your Lakebase endpoint host
3. Run in order: `00_setup_lakebase` → `01_generate_synthetic_data`

---

## Step 4: Twilio Setup (MANUAL — ~15 min)

Twilio requires manual configuration through their console. This cannot be automated.

### 4a. Voice Calling Setup

1. **Buy a phone number** (or use trial number):
   - Twilio Console → Phone Numbers → Buy a Number
   - For India calling: need international calling enabled
   - Note: Trial accounts can only call verified numbers

2. **Verify your test phone** (trial accounts only):
   - Twilio Console → Phone Numbers → Verified Caller IDs → Add
   - Enter your phone number → receive verification code → confirm

3. **Set `TWILIO_PHONE_NUMBER`** in your `.env`:
   ```
   TWILIO_PHONE_NUMBER=+1XXXXXXXXXX
   ```

### 4b. WhatsApp Sandbox Setup

1. **Activate sandbox:**
   - Twilio Console → Messaging → Try it Out → Send a WhatsApp Message
   - Send the join code (e.g., "join example-word") from your WhatsApp to `+1 415 523 8886`

2. **Note:** Sandbox has a 50 messages/day limit. For production, apply for a WhatsApp Business Profile.

### 4c. Create Twilio Functions (WhatsApp Relay)

The Databricks App requires OAuth authentication, which Twilio can't provide directly. We use a thin Twilio Function as a relay.

1. **Create a Functions Service:**
   - Twilio Console → Functions & Assets → Services → Create Service
   - Name: `vaaniseva-wa` (or any name)

2. **Add the WhatsApp relay function:**
   - Click "Add +" → Add Function → Path: `/whatsapp`
   - Copy the contents of `twilio_function.js` from this repo
   - **IMPORTANT:** Change the `hostname` in the code to your Databricks App hostname:
     ```javascript
     hostname: "your-app-name-xxxx.yy.azure.databricksapps.com",
     ```
   - Set visibility to **Public**

3. **Add the TTS audio function:**
   - Click "Add +" → Add Function → Path: `/audio`
   - Copy the contents of `twilio_audio_function.js` from this repo
   - Set visibility to **Public**

4. **Set environment variables** in the Functions Service:
   - Go to Settings → Environment Variables
   - Add the following:

   | Variable | Value | Notes |
   |----------|-------|-------|
   | `SARVAM_KEY` | Your Sarvam API key | Same as `SARVAM_API_KEY` in .env |
   | `T1` | OAuth token part 1 | See Step 5 below |
   | `T2` | OAuth token part 2 | |
   | `T3` | OAuth token part 3 | |
   | `T4` | OAuth token part 4 | |

5. **Deploy** the Functions Service (click "Deploy All")

6. **Configure WhatsApp webhook:**
   - Twilio Console → Messaging → Try it Out → Send a WhatsApp Message → Sandbox Settings
   - Set "When a message comes in" to: `https://your-service-xxxx.twil.io/whatsapp`
   - Method: POST
   - Save

7. **Update `.env`** with the TTS function URL:
   ```
   SARVAM_TTS_URL=https://your-service-xxxx.twil.io/audio
   ```
   Then redeploy: `./setup.sh --deploy-only`

---

## Step 5: Generate OAuth Tokens for Twilio (2 min)

Twilio Functions need a Databricks OAuth token to call the App. The token is split into 4 parts because Twilio has a 255-character env var limit.

```bash
./setup.sh --token
```

This outputs T1, T2, T3, T4 values. Copy them into Twilio Functions > Environment Variables.

**IMPORTANT:** OAuth tokens expire in ~1 hour. You need to:
1. Re-run `./setup.sh --token`
2. Update T1-T4 in Twilio Console
3. Redeploy the Twilio Functions

For a production setup, implement token refresh in the Twilio Function itself.

---

## Step 6: IP Access List (if workspace has IP restrictions)

If your Databricks workspace uses IP access lists, you need to allow Twilio's IPs:

```bash
# Get your workspace's IP access lists
databricks ip-access-lists list -p <profile>

# Option A: Allow all (for demo only — remove after!)
databricks ip-access-lists create \
  --label "demo-allow-all" \
  --list-type ALLOW \
  --ip-addresses '["0.0.0.0/0"]' \
  -p <profile>

# Option B: Allow specific Twilio IPs (check Twilio docs for current IPs)
# https://www.twilio.com/docs/sip-trunking/ip-addresses
```

---

## Step 7: Verify Everything Works (5 min)

### Test the App
1. Get the app URL:
   ```bash
   databricks apps get vaaniseva -p <profile>
   ```
2. Open the URL in browser → should see the VaaniSeva UI with 50 customers

### Test WhatsApp
1. Send "hi" to the Twilio WhatsApp sandbox number
2. Should receive the VaaniSeva menu
3. Send "2" (Check EMI) → "4521" (or any account_last4 from your data) → should show live loan data

### Test Voice Call
1. In the VaaniSeva UI → select a customer → Click "Real Call"
2. Enter your (verified) phone number
3. Phone should ring → hear the greeting with customer name

---

## Quick Reference

### File Structure
```
vaaniseva-fins/
├── setup.sh                    # Automated setup (Lakebase + data + deploy)
├── env.template                # Environment variable template
├── .env                        # Your local config (git-ignored)
├── app.py                      # FastAPI entrypoint
├── app.yaml                    # Databricks App config (template)
├── app.yaml.local              # Generated with real values (git-ignored)
├── databricks.yml              # DAB bundle definition
├── requirements.txt            # Python dependencies
├── twilio_function.js          # WhatsApp relay (paste into Twilio Console)
├── twilio_audio_function.js    # Sarvam TTS relay (paste into Twilio Console)
├── scripts/
│   ├── seed_data.py            # Data seeder (called by setup.sh)
│   └── generate_app_yaml.py    # Generates app.yaml.local from .env
├── notebooks/
│   ├── 00_setup_lakebase.py    # Alternative: run in Databricks notebook
│   └── 01_generate_synthetic_data.py
├── vaaniseva/                  # Main Python package
│   ├── config.py               # Environment config
│   ├── db.py                   # Lakebase connection pool
│   ├── agent/                  # Call flow state machine + LLM
│   ├── audit/                  # Quality scoring (5-category RBI rubric)
│   ├── retrieval/              # Lakebase queries + RAG
│   ├── voice/                  # Sarvam STT/TTS clients
│   └── routes/                 # FastAPI endpoints
└── static/                     # Web UI (Customer Sim, Agent View, WhatsApp, Audit)
```

### Common Commands
```bash
# Redeploy after code changes
databricks bundle deploy -t dev -p <profile>

# Refresh OAuth token for Twilio
./setup.sh --token

# Check app health
curl -s https://<app-url>/api/health | python3 -m json.tool

# View app logs
databricks apps get-logs vaaniseva -p <profile>

# Reseed data
./setup.sh --data-only

# Connect to Lakebase directly
./setup.sh --lakebase-only  # prints connection details
```

### What's Automated vs Manual

| Component | Automated (`setup.sh`) | Manual (Twilio Console) |
|-----------|----------------------|------------------------|
| Lakebase project | Yes | - |
| Database + tables | Yes | - |
| Seed data | Yes | - |
| App deployment | Yes | - |
| app.yaml.local generation | Yes | - |
| Twilio phone number | - | Buy/configure in Console |
| Twilio Functions (relay) | - | Paste code, set env vars, deploy |
| WhatsApp sandbox | - | Send join code from phone |
| OAuth token (T1-T4) | `--token` generates them | Paste into Twilio env vars |
| IP access list | - | Add if workspace requires it |

---

## Troubleshooting

| Issue | Solution |
|-------|---------|
| App shows "Lakebase init failed" | Check `LAKEBASE_HOST` in app.yaml.local matches your endpoint |
| WhatsApp: no response | Check Twilio Function logs (Console → Functions → Logs) |
| WhatsApp: "IP blocked" | Add Twilio IPs to workspace IP access list (Step 6) |
| WhatsApp: "account not found" | Verify the last 4 digits match a customer in the DB |
| Voice: "21210 unverified number" | Verify caller ID in Twilio Console (trial limitation) |
| Voice: no audio | Check `SARVAM_TTS_URL` env var and /audio function deployment |
| Token expired | Re-run `./setup.sh --token` and update Twilio env vars |
| "multiple auth methods" | Remove `DATABRICKS_TOKEN` env var (app uses OAuth, not PAT) |
| psql: "permission denied for schema" | Create the database first (`CREATE DATABASE vaaniseva`) |

---

## Architecture

```
Customer Phone/WhatsApp
         │
         ▼
   Twilio (Voice/WhatsApp)
         │
         ├── Voice: TwiML inline (no webhooks needed)
         │
         └── WhatsApp: Twilio Function (34-line relay)
                  │
                  │ HTTPS + OAuth token
                  ▼
         Databricks App (FastAPI)
                  │
         ┌───────┼───────┐
         ▼       ▼       ▼
    Lakebase  Sarvam AI  Model Serving
    (customer  (STT/TTS/  (propensity,
     data)     LLM)       risk score)
```

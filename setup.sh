#!/bin/bash
# =============================================================================
# VaaniSeva — Automated Setup Script
# Sets up Lakebase, seeds data, and deploys the Databricks App.
#
# Prerequisites:
#   1. Databricks CLI v0.285+ authenticated (databricks auth login)
#   2. psql client installed (brew install postgresql@16)
#   3. .env file populated (cp env.template .env)
#
# Usage:
#   chmod +x setup.sh
#   ./setup.sh                    # Full setup (Lakebase + data + deploy)
#   ./setup.sh --lakebase-only    # Only create Lakebase project + tables
#   ./setup.sh --data-only        # Only seed data (Lakebase must exist)
#   ./setup.sh --deploy-only      # Only deploy the Databricks App
#   ./setup.sh --token            # Generate Twilio OAuth token (T1-T4)
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ---------------------------------------------------------------------------
# Load .env
# ---------------------------------------------------------------------------
if [ -f .env ]; then
    set -a; source .env; set +a
    info "Loaded .env"
else
    err "No .env file found. Run: cp env.template .env  and fill in your values."
fi

PROFILE="${DATABRICKS_PROFILE:-DEFAULT}"
PROJECT="${LAKEBASE_PROJECT:-vaaniseva}"
BRANCH="${LAKEBASE_BRANCH:-production}"
ENDPOINT="${LAKEBASE_ENDPOINT:-primary}"
DB_NAME="${LAKEBASE_DB_NAME:-vaaniseva}"

# ---------------------------------------------------------------------------
# Check prerequisites
# ---------------------------------------------------------------------------
check_prereqs() {
    info "Checking prerequisites..."

    if ! command -v databricks &> /dev/null; then
        err "Databricks CLI not found. Install: https://docs.databricks.com/dev-tools/cli/install.html"
    fi

    CLI_VERSION=$(databricks --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
    info "Databricks CLI version: $CLI_VERSION"

    if ! command -v psql &> /dev/null; then
        warn "psql not found. Install: brew install postgresql@16"
        warn "Skipping direct SQL operations — use notebooks instead."
        HAS_PSQL=false
    else
        HAS_PSQL=true
    fi

    # Verify auth
    if ! databricks current-user me -p "$PROFILE" -o json &> /dev/null; then
        err "Databricks CLI not authenticated. Run: databricks auth login --host <workspace-url> --profile $PROFILE"
    fi
    EMAIL=$(databricks current-user me -p "$PROFILE" -o json | python3 -c "import sys,json; print(json.load(sys.stdin)['userName'])")
    ok "Authenticated as: $EMAIL"
}

# ---------------------------------------------------------------------------
# Step 1: Create Lakebase Project
# ---------------------------------------------------------------------------
create_lakebase() {
    info "Creating Lakebase project: $PROJECT"

    # Check if project already exists
    if databricks postgres get-project "projects/$PROJECT" -p "$PROFILE" -o json &> /dev/null 2>&1; then
        ok "Lakebase project '$PROJECT' already exists"
    else
        databricks postgres create-project "$PROJECT" \
            --json "{\"spec\": {\"display_name\": \"VaaniSeva BFSI Agent\"}}" \
            --no-wait \
            -p "$PROFILE"
        info "Project created. Waiting for endpoint to become ACTIVE..."

        # Poll until endpoint is active (max 3 minutes)
        for i in $(seq 1 36); do
            STATE=$(databricks postgres list-endpoints "projects/$PROJECT/branches/$BRANCH" \
                -p "$PROFILE" -o json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['status']['current_state'])" 2>/dev/null || echo "PENDING")
            if [ "$STATE" = "ACTIVE" ]; then
                ok "Lakebase endpoint is ACTIVE"
                break
            fi
            echo -n "."
            sleep 5
        done
        echo ""
    fi

    # Get host
    LAKEBASE_HOST=$(databricks postgres list-endpoints "projects/$PROJECT/branches/$BRANCH" \
        -p "$PROFILE" -o json | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['status']['hosts']['host'])")

    ok "Lakebase host: $LAKEBASE_HOST"

    # Update .env with the host
    if grep -q "^LAKEBASE_HOST=$" .env; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s|^LAKEBASE_HOST=.*|LAKEBASE_HOST=$LAKEBASE_HOST|" .env
        else
            sed -i "s|^LAKEBASE_HOST=.*|LAKEBASE_HOST=$LAKEBASE_HOST|" .env
        fi
        ok "Updated LAKEBASE_HOST in .env"
    fi
}

# ---------------------------------------------------------------------------
# Step 2: Create Database + Tables
# ---------------------------------------------------------------------------
create_tables() {
    if [ "$HAS_PSQL" = false ]; then
        warn "psql not available. Run notebook 00_setup_lakebase.py in your workspace instead."
        return
    fi

    info "Creating database and tables..."

    ENDPOINT_PATH="projects/$PROJECT/branches/$BRANCH/endpoints/$ENDPOINT"
    TOKEN=$(databricks postgres generate-database-credential "$ENDPOINT_PATH" \
        -p "$PROFILE" -o json | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

    # Create database (connect to default postgres first)
    PGPASSWORD="$TOKEN" psql "host=$LAKEBASE_HOST port=5432 dbname=postgres user=$EMAIL sslmode=require" \
        -c "CREATE DATABASE $DB_NAME;" 2>/dev/null || true
    ok "Database '$DB_NAME' ready"

    # Create tables
    PGPASSWORD="$TOKEN" psql "host=$LAKEBASE_HOST port=5432 dbname=$DB_NAME user=$EMAIL sslmode=require" <<'EOSQL'
-- Customer Profiles
CREATE TABLE IF NOT EXISTS customer_profiles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    phone VARCHAR(20) NOT NULL,
    city VARCHAR(100) NOT NULL,
    language_pref VARCHAR(10) DEFAULT 'hi',
    account_last4 VARCHAR(4) NOT NULL,
    risk_tier VARCHAR(20) DEFAULT 'MEDIUM',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Loan Accounts
CREATE TABLE IF NOT EXISTS loan_accounts (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customer_profiles(id),
    loan_type VARCHAR(50) NOT NULL,
    principal NUMERIC(12,2) NOT NULL,
    emi_amount NUMERIC(10,2) NOT NULL,
    overdue_amount NUMERIC(10,2) DEFAULT 0,
    days_overdue INTEGER DEFAULT 0,
    last_payment_date DATE,
    status VARCHAR(20) DEFAULT 'ACTIVE',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Payment History
CREATE TABLE IF NOT EXISTS payment_history (
    id SERIAL PRIMARY KEY,
    loan_id INTEGER REFERENCES loan_accounts(id),
    payment_date DATE NOT NULL,
    amount NUMERIC(10,2) NOT NULL,
    payment_mode VARCHAR(30) DEFAULT 'UPI',
    status VARCHAR(20) DEFAULT 'SUCCESS',
    reference_id VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Call Queue
CREATE TABLE IF NOT EXISTS call_queue (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customer_profiles(id),
    priority INTEGER DEFAULT 1,
    scheduled_at TIMESTAMP DEFAULT NOW(),
    status VARCHAR(20) DEFAULT 'PENDING',
    assigned_agent VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Call Logs
CREATE TABLE IF NOT EXISTS call_logs (
    call_id VARCHAR(20) PRIMARY KEY,
    customer_id INTEGER REFERENCES customer_profiles(id),
    agent_name VARCHAR(100),
    language VARCHAR(10),
    stage VARCHAR(30),
    outcome VARCHAR(30),
    turn_count INTEGER DEFAULT 0,
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    status VARCHAR(20) DEFAULT 'IN_PROGRESS',
    transcript JSONB,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Quality Scores
CREATE TABLE IF NOT EXISTS quality_scores (
    call_id VARCHAR(20) PRIMARY KEY REFERENCES call_logs(call_id),
    overall_score NUMERIC(5,1),
    compliance_score NUMERIC(5,1),
    script_adherence_score NUMERIC(5,1),
    empathy_score NUMERIC(5,1),
    resolution_score NUMERIC(5,1),
    language_quality_score NUMERIC(5,1),
    findings JSONB,
    recommendations JSONB,
    scored_at TIMESTAMP DEFAULT NOW()
);

-- Knowledge Base
CREATE TABLE IF NOT EXISTS knowledge_base (
    id SERIAL PRIMARY KEY,
    title VARCHAR(300) NOT NULL,
    content TEXT NOT NULL,
    category VARCHAR(50),
    language VARCHAR(10) DEFAULT 'en',
    created_at TIMESTAMP DEFAULT NOW()
);
EOSQL

    ok "All 7 tables created"
}

# ---------------------------------------------------------------------------
# Step 3: Seed Data
# ---------------------------------------------------------------------------
seed_data() {
    if [ "$HAS_PSQL" = false ]; then
        warn "psql not available. Run notebook 01_generate_synthetic_data.py instead."
        return
    fi

    info "Seeding data (this runs the Python seeder)..."

    ENDPOINT_PATH="projects/$PROJECT/branches/$BRANCH/endpoints/$ENDPOINT"
    TOKEN=$(databricks postgres generate-database-credential "$ENDPOINT_PATH" \
        -p "$PROFILE" -o json | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

    # Run the Python seeder script
    LAKEBASE_HOST="$LAKEBASE_HOST" \
    LAKEBASE_DB_NAME="$DB_NAME" \
    LAKEBASE_USER="$EMAIL" \
    LAKEBASE_TOKEN="$TOKEN" \
    python3 scripts/seed_data.py

    ok "Data seeded successfully"
}

# ---------------------------------------------------------------------------
# Step 4: Deploy Databricks App
# ---------------------------------------------------------------------------
deploy_app() {
    info "Deploying VaaniSeva app via Databricks Asset Bundle..."

    # Build app.yaml.local from .env
    info "Generating app.yaml.local from .env..."
    python3 scripts/generate_app_yaml.py

    databricks bundle deploy -t dev -p "$PROFILE"
    ok "App deployed!"

    # Get app URL
    APP_URL=$(databricks apps get vaaniseva -p "$PROFILE" -o json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('url',''))" 2>/dev/null || echo "")
    if [ -n "$APP_URL" ]; then
        ok "App URL: $APP_URL"
    else
        info "Run 'databricks apps get vaaniseva -p $PROFILE' to get the app URL"
    fi
}

# ---------------------------------------------------------------------------
# Generate Twilio OAuth Token (split into T1-T4)
# ---------------------------------------------------------------------------
generate_token() {
    info "Generating Databricks OAuth token for Twilio Functions..."

    TOKEN=$(databricks auth token -p "$PROFILE" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null || databricks auth token -p "$PROFILE" 2>/dev/null)

    if [ -z "$TOKEN" ]; then
        err "Could not get OAuth token. Ensure CLI is authenticated."
    fi

    TOKEN_LEN=${#TOKEN}
    info "Token length: $TOKEN_LEN characters"

    # Split into 4 chunks of ~214 chars (Twilio env var limit is 255)
    CHUNK=$((TOKEN_LEN / 4 + 1))
    T1="${TOKEN:0:$CHUNK}"
    T2="${TOKEN:$CHUNK:$CHUNK}"
    T3="${TOKEN:$((CHUNK*2)):$CHUNK}"
    T4="${TOKEN:$((CHUNK*3))}"

    echo ""
    echo "=============================================="
    echo "Set these in Twilio Functions > Environment Variables:"
    echo "=============================================="
    echo ""
    printf "%-4s | %-4s | %s\n" "Var" "Len" "Value"
    echo "-----|------|------"
    printf "%-4s | %-4s | %s\n" "T1" "${#T1}" "$T1"
    echo ""
    printf "%-4s | %-4s | %s\n" "T2" "${#T2}" "$T2"
    echo ""
    printf "%-4s | %-4s | %s\n" "T3" "${#T3}" "$T3"
    echo ""
    printf "%-4s | %-4s | %s\n" "T4" "${#T4}" "$T4"
    echo ""
    echo "=============================================="
    warn "Token expires in ~1 hour. Re-run './setup.sh --token' to refresh."
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
case "${1:-full}" in
    --lakebase-only)
        check_prereqs
        create_lakebase
        create_tables
        ;;
    --data-only)
        check_prereqs
        LAKEBASE_HOST="${LAKEBASE_HOST:?Set LAKEBASE_HOST in .env}"
        seed_data
        ;;
    --deploy-only)
        check_prereqs
        deploy_app
        ;;
    --token)
        generate_token
        ;;
    full|*)
        check_prereqs
        create_lakebase
        create_tables
        seed_data
        deploy_app
        echo ""
        ok "========================================"
        ok "VaaniSeva setup complete!"
        ok "========================================"
        echo ""
        info "Next steps (MANUAL):"
        echo "  1. Set up Twilio Functions — see INSTALL.md Step 4"
        echo "  2. Generate OAuth token:  ./setup.sh --token"
        echo "  3. Configure Twilio Function env vars with T1-T4 tokens"
        echo "  4. Add workspace IP access list for Twilio IPs"
        echo ""
        ;;
esac

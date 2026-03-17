# Databricks notebook source
# MAGIC %md
# MAGIC # VaaniSeva — Lakebase Setup
# MAGIC Creates the `vaaniseva` database and all required tables.

# COMMAND ----------

# MAGIC %pip install databricks-sdk psycopg[binary] psycopg_pool
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

import os
import uuid
import time
from threading import Lock
from databricks.sdk import WorkspaceClient
import psycopg
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

# COMMAND ----------

# Configuration — UPDATE THESE
INSTANCE_NAME = "vaaniseva-lakebase"  # Your Lakebase instance name
CONN_HOST = ""  # Your Lakebase host (from instance details)
DB_NAME = "vaaniseva"

# COMMAND ----------

# MAGIC %md
# MAGIC ## Create Lakebase Instance (if needed)
# MAGIC Uncomment and run the cell below if you need to create a new Lakebase instance.

# COMMAND ----------

# w = WorkspaceClient()
# instance = w.database.create_instance(
#     name=INSTANCE_NAME,
#     capacity="SERVERLESS",
# )
# print(f"Instance created: {instance.name}")
# print(f"Host: {instance.host}")
# CONN_HOST = instance.host

# COMMAND ----------

# MAGIC %md
# MAGIC ## Connect to Lakebase

# COMMAND ----------

class CredentialConnection(psycopg.Connection):
    workspace_client = None
    instance_name = None
    _cached_credential = None
    _cache_timestamp = None
    _cache_duration = 3000
    _cache_lock = Lock()

    @classmethod
    def connect(cls, conninfo="", **kwargs):
        if cls.workspace_client is None:
            raise ValueError("workspace_client must be set")
        kwargs["password"] = cls._get_cached_credential()
        return super().connect(conninfo, **kwargs)

    @classmethod
    def _get_cached_credential(cls):
        with cls._cache_lock:
            now = time.time()
            if cls._cached_credential and cls._cache_timestamp and now - cls._cache_timestamp < cls._cache_duration:
                return cls._cached_credential
            credential = cls.workspace_client.database.generate_database_credential(
                request_id=str(uuid.uuid4()), instance_names=[cls.instance_name]
            )
            cls._cached_credential = credential.token
            cls._cache_timestamp = now
            return cls._cached_credential


w = WorkspaceClient()
CredentialConnection.workspace_client = w
CredentialConnection.instance_name = INSTANCE_NAME

try:
    sp = w.current_service_principal.me()
    username = sp.application_id
except:
    username = w.current_user.me().user_name

conninfo = f"dbname=databricks_postgres user={username} host={CONN_HOST} sslmode=require"

pool = ConnectionPool(
    conninfo=conninfo,
    connection_class=CredentialConnection,
    min_size=1, max_size=5, timeout=30.0, open=True,
    kwargs={"autocommit": True, "row_factory": dict_row}
)

with pool.connection() as conn:
    conn.execute("SELECT 1")
print("Connected to Lakebase!")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Create Database

# COMMAND ----------

with pool.connection() as conn:
    conn.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
    print(f"Database '{DB_NAME}' ready")

# Reconnect to the new database
pool.close()
conninfo = f"dbname={DB_NAME} user={username} host={CONN_HOST} sslmode=require"
pool = ConnectionPool(
    conninfo=conninfo,
    connection_class=CredentialConnection,
    min_size=1, max_size=5, timeout=30.0, open=True,
    kwargs={"autocommit": True, "row_factory": dict_row}
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Create Tables

# COMMAND ----------

DDL = """
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

-- Knowledge Base (for Vector Search source)
CREATE TABLE IF NOT EXISTS knowledge_base (
    id SERIAL PRIMARY KEY,
    title VARCHAR(300) NOT NULL,
    content TEXT NOT NULL,
    category VARCHAR(50),
    language VARCHAR(10) DEFAULT 'en',
    created_at TIMESTAMP DEFAULT NOW()
);
"""

with pool.connection() as conn:
    for statement in DDL.split(";"):
        stmt = statement.strip()
        if stmt and not stmt.startswith("--"):
            conn.execute(stmt)
    print("All tables created successfully!")

# COMMAND ----------

# Verify tables
with pool.connection() as conn:
    result = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name"
    ).fetchall()
    print("Tables:", [r["table_name"] for r in result])

# COMMAND ----------

pool.close()
print("Setup complete! Proceed to 01_generate_synthetic_data.")

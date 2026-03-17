# Databricks notebook source
# MAGIC %md
# MAGIC # VaaniSeva — UC Vector Search Setup
# MAGIC Creates a Delta table from the knowledge base and sets up a Vector Search index.

# COMMAND ----------

# MAGIC %pip install databricks-sdk
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# Configuration
CATALOG = "sarbanimaiti_catalog"
SCHEMA = "vaaniseva"
TABLE = "knowledge_base_vs"
VS_ENDPOINT = "vaaniseva-vs-endpoint"
VS_INDEX = f"{CATALOG}.{SCHEMA}.knowledge_base_vs_index"

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1: Create catalog and schema if needed

# COMMAND ----------

spark.sql(f"CREATE CATALOG IF NOT EXISTS {CATALOG}")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
print(f"Catalog/schema ready: {CATALOG}.{SCHEMA}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2: Export knowledge base from Lakebase to Delta table

# COMMAND ----------

import os, uuid, time
from threading import Lock
from databricks.sdk import WorkspaceClient
import psycopg
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

# Lakebase connection — UPDATE THESE
INSTANCE_NAME = "vaaniseva-lakebase"
CONN_HOST = ""  # Your Lakebase host
DB_NAME = "vaaniseva"

class CredentialConnection(psycopg.Connection):
    workspace_client = None
    instance_name = None
    _cached_credential = None
    _cache_timestamp = None
    _cache_duration = 3000
    _cache_lock = Lock()

    @classmethod
    def connect(cls, conninfo="", **kwargs):
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
    username = w.current_service_principal.me().application_id
except:
    username = w.current_user.me().user_name

pool = ConnectionPool(
    conninfo=f"dbname={DB_NAME} user={username} host={CONN_HOST} sslmode=require",
    connection_class=CredentialConnection,
    min_size=1, max_size=3, timeout=30.0, open=True,
    kwargs={"autocommit": True, "row_factory": dict_row}
)

with pool.connection() as conn:
    docs = conn.execute("SELECT id, title, content, category, language FROM knowledge_base").fetchall()

pool.close()
print(f"Fetched {len(docs)} knowledge base documents from Lakebase")

# COMMAND ----------

# Create Delta table
from pyspark.sql import Row

rows = [Row(id=d["id"], title=d["title"], content=d["content"],
            category=d["category"], language=d["language"]) for d in docs]

df = spark.createDataFrame(rows)
df.write.mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.{TABLE}")
print(f"Delta table created: {CATALOG}.{SCHEMA}.{TABLE}")
display(df)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3: Create Vector Search endpoint

# COMMAND ----------

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.vectorsearch import EndpointType

w = WorkspaceClient()

# Check if endpoint exists
existing = [e.name for e in w.vector_search_endpoints.list_endpoints()]
if VS_ENDPOINT not in existing:
    w.vector_search_endpoints.create_endpoint(
        name=VS_ENDPOINT,
        endpoint_type=EndpointType.STANDARD,
    )
    print(f"Creating endpoint '{VS_ENDPOINT}'... (this may take a few minutes)")
else:
    print(f"Endpoint '{VS_ENDPOINT}' already exists")

# COMMAND ----------

# Wait for endpoint to be ready
import time
while True:
    ep = w.vector_search_endpoints.get_endpoint(VS_ENDPOINT)
    status = ep.endpoint_status.state.value if ep.endpoint_status else "UNKNOWN"
    print(f"Endpoint status: {status}")
    if status == "ONLINE":
        break
    time.sleep(30)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4: Create Vector Search index

# COMMAND ----------

from databricks.sdk.service.vectorsearch import DeltaSyncVectorIndexSpecRequest, EmbeddingSourceColumn, PipelineType

source_table = f"{CATALOG}.{SCHEMA}.{TABLE}"

try:
    w.vector_search_indexes.create_index(
        name=VS_INDEX,
        endpoint_name=VS_ENDPOINT,
        primary_key="id",
        index_type="DELTA_SYNC",
        delta_sync_index_spec=DeltaSyncVectorIndexSpecRequest(
            source_table=source_table,
            pipeline_type=PipelineType.TRIGGERED,
            embedding_source_columns=[
                EmbeddingSourceColumn(
                    name="content",
                    embedding_model_endpoint_name="databricks-gte-large-en",
                )
            ],
        ),
    )
    print(f"Creating index '{VS_INDEX}'... (this may take several minutes)")
except Exception as e:
    if "already exists" in str(e):
        print(f"Index '{VS_INDEX}' already exists")
    else:
        raise e

# COMMAND ----------

# Wait for index to be ready
import time
while True:
    try:
        idx = w.vector_search_indexes.get_index(VS_INDEX)
        status = idx.status.ready
        print(f"Index ready: {status}")
        if status:
            break
    except Exception as e:
        print(f"Waiting... ({e})")
    time.sleep(30)

print("Vector Search index is ready!")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5: Test the index

# COMMAND ----------

results = w.vector_search_indexes.query_index(
    index_name=VS_INDEX,
    query_text="What is the EMI restructuring policy?",
    columns=["title", "content", "category"],
    num_results=3,
)

for row in results.result.data_array:
    print(f"Title: {row[0]}")
    print(f"Category: {row[2]}")
    print(f"Content: {row[1][:200]}...")
    print("---")

# COMMAND ----------

print(f"""
Vector Search Setup Complete!

Endpoint: {VS_ENDPOINT}
Index: {VS_INDEX}
Source table: {source_table}

Update your app.yaml with:
  VS_ENDPOINT_NAME: {VS_ENDPOINT}
  VS_INDEX_NAME: {VS_INDEX}
""")

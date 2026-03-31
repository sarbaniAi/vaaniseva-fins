"""Lakebase (Autoscaling) connection pool with OAuth credential rotation."""

import logging
import os
import time
import uuid
from contextlib import contextmanager
from threading import Lock

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from vaaniseva.config import (
    LAKEBASE_PROJECT,
    LAKEBASE_BRANCH,
    LAKEBASE_ENDPOINT,
    LAKEBASE_HOST,
    LAKEBASE_DB_NAME,
)

logger = logging.getLogger(__name__)

_pool: ConnectionPool | None = None


class CredentialConnection(psycopg.Connection):
    """Custom connection class that generates fresh OAuth tokens with caching."""

    workspace_client = None

    _cached_credential = None
    _cache_timestamp = None
    _cache_duration = 3000  # 50 minutes
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
            if (
                cls._cached_credential is not None
                and cls._cache_timestamp is not None
                and now - cls._cache_timestamp < cls._cache_duration
            ):
                return cls._cached_credential

            endpoint_path = (
                f"projects/{LAKEBASE_PROJECT}/branches/{LAKEBASE_BRANCH}"
                f"/endpoints/{LAKEBASE_ENDPOINT}"
            )
            credential = cls.workspace_client.api_client.do(
                "POST",
                "/api/2.0/postgres/credentials",
                body={"endpoint": endpoint_path},
            )
            cls._cached_credential = credential.get("token", "")
            cls._cache_timestamp = now
            return cls._cached_credential


def init_pool():
    """Initialize the Lakebase connection pool. Call once at app startup."""
    global _pool
    if _pool is not None:
        return

    if not LAKEBASE_HOST:
        raise RuntimeError("LAKEBASE_HOST not configured")

    from databricks.sdk import WorkspaceClient

    # Databricks Apps inject OAuth (CLIENT_ID/SECRET) for the SP.
    # Remove PAT token to avoid "multiple auth methods" error.
    os.environ.pop("DATABRICKS_TOKEN", None)
    wc = WorkspaceClient()

    CredentialConnection.workspace_client = wc

    # Determine username (SP application ID)
    try:
        sp = wc.current_service_principal.me()
        username = sp.application_id
    except Exception:
        username = wc.current_user.me().user_name

    conninfo = (
        f"dbname={LAKEBASE_DB_NAME} user={username} "
        f"host={LAKEBASE_HOST} port=5432 sslmode=require"
    )

    _pool = ConnectionPool(
        conninfo=conninfo,
        connection_class=CredentialConnection,
        min_size=1,
        max_size=10,
        timeout=30.0,
        open=True,
        kwargs={
            "autocommit": True,
            "row_factory": dict_row,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
        },
    )

    # Smoke test
    with _pool.connection() as conn:
        conn.execute("SELECT 1")
    logger.info("Lakebase connection pool initialized (autoscaling)")


@contextmanager
def get_conn():
    """Get a connection from the pool."""
    if _pool is None:
        raise RuntimeError("Connection pool not initialized. Call init_pool() first.")
    with _pool.connection() as conn:
        yield conn


def execute(query: str, params: tuple | None = None) -> list[dict]:
    """Execute a query and return all rows as dicts."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            if cur.description:
                return cur.fetchall()
            return []


def execute_one(query: str, params: tuple | None = None) -> dict | None:
    """Execute a query and return a single row."""
    rows = execute(query, params)
    return rows[0] if rows else None


def execute_write(query: str, params: tuple | None = None):
    """Execute an INSERT/UPDATE/DELETE."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)

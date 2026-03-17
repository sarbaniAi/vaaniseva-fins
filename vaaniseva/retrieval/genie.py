"""Genie Space / direct SQL for structured loan data lookups."""

import logging
from vaaniseva import db

logger = logging.getLogger(__name__)


def get_customer_profile(customer_id: int) -> dict | None:
    """Fetch customer profile from Lakebase."""
    return db.execute_one(
        "SELECT * FROM customer_profiles WHERE id = %s", (customer_id,)
    )


def get_customer_loans(customer_id: int) -> list[dict]:
    """Fetch all loans for a customer."""
    return db.execute(
        "SELECT * FROM loan_accounts WHERE customer_id = %s ORDER BY days_overdue DESC",
        (customer_id,),
    )


def get_overdue_loans(customer_id: int) -> list[dict]:
    """Fetch only overdue loans."""
    return db.execute(
        "SELECT * FROM loan_accounts WHERE customer_id = %s AND days_overdue > 0 ORDER BY days_overdue DESC",
        (customer_id,),
    )


def get_payment_history(loan_id: int, limit: int = 10) -> list[dict]:
    """Fetch recent payment history for a loan (if table exists)."""
    try:
        return db.execute(
            "SELECT * FROM payment_history WHERE loan_id = %s ORDER BY payment_date DESC LIMIT %s",
            (loan_id, limit),
        )
    except Exception:
        return []


def get_call_queue(limit: int = 30) -> list[dict]:
    """Fetch pending call queue entries."""
    return db.execute(
        """SELECT cq.*, cp.name, cp.city, cp.language_pref, cp.phone
           FROM call_queue cq
           JOIN customer_profiles cp ON cq.customer_id = cp.id
           WHERE cq.status = 'PENDING'
           ORDER BY cq.priority DESC, cq.scheduled_at ASC
           LIMIT %s""",
        (limit,),
    )


def get_all_customers() -> list[dict]:
    """Fetch all customer profiles."""
    return db.execute("SELECT * FROM customer_profiles ORDER BY name")


def search_customer_loans_nl(query: str) -> str:
    """
    Natural language to SQL via Genie Space (showcase feature).
    Falls back to canned queries if Genie is unavailable.
    """
    from vaaniseva.config import GENIE_SPACE_ID, DATABRICKS_HOST, DATABRICKS_TOKEN
    import requests

    if not all([GENIE_SPACE_ID, DATABRICKS_HOST, DATABRICKS_TOKEN]):
        return "Genie Space not configured"

    try:
        # Start conversation
        resp = requests.post(
            f"{DATABRICKS_HOST}/api/2.0/genie/spaces/{GENIE_SPACE_ID}/start-conversation",
            headers={
                "Authorization": f"Bearer {DATABRICKS_TOKEN}",
                "Content-Type": "application/json",
            },
            json={"content": query},
            timeout=30,
        )
        if resp.status_code == 200:
            return resp.json()
        return f"Genie error: {resp.status_code}"
    except Exception as e:
        return f"Genie unavailable: {e}"

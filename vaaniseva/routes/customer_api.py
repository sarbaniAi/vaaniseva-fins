"""Customer data API routes."""

import logging
from fastapi import APIRouter, HTTPException

from vaaniseva.retrieval.genie import get_all_customers, get_customer_profile, get_customer_loans

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/customers", tags=["customers"])


@router.get("")
async def list_customers():
    """List all customers."""
    return get_all_customers()


@router.get("/{customer_id}")
async def get_customer(customer_id: int):
    """Get customer profile with loans."""
    customer = get_customer_profile(customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    loans = get_customer_loans(customer_id)
    return {"customer": customer, "loans": loans}

"""Session-bound API, matching /api/me conventions. No customer-ID selector."""
import datetime as dt
import os

from fastapi import APIRouter, Depends, HTTPException

from .. import auth, db
from ..auth import Principal
from .models import CustomerState
from .service import get_domain, get_state

router = APIRouter(prefix="/api/me/customer-state", tags=["customer-state"])


def load_state(as_of: dt.date | None = None, user: Principal = Depends(auth.require_customer)) -> CustomerState:
    reference = dt.date.fromisoformat(os.environ.get("DEMO_TODAY", "2026-09-30"))
    with db.tx() as conn:
        try:
            return get_state(conn, user.customer_id, min(as_of or reference, reference), balance_reference=reference)
        except LookupError:
            raise HTTPException(status_code=404, detail="Customer not found") from None


@router.get("", response_model=CustomerState)
def full_state(state: CustomerState = Depends(load_state)) -> CustomerState:
    return state


@router.get("/{domain}")
def domain_state(domain: str, state: CustomerState = Depends(load_state)) -> dict:
    try:
        return get_domain(state, domain)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown Customer State domain") from None

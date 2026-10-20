"""Kate nudges (proactive messages). Router mounted in main.py; schema created from db.init_schema.

Customer endpoints take the customer from the session only. Acks are stored per (session customer, nudge key), so
a key from another customer only ever touches the caller's own rows.
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from .. import auth, db
from ..auth import Principal
from . import nudges
from .nudges import NUDGE_KEY_PATTERN, AckRequest, AckResponse, NudgesResponse, NudgeStats
from .service import DEMO_TODAY

router = APIRouter(tags=["nudges"])


def init_schema(conn) -> None:
    """Create the nudge tables (called from db.init_schema)."""
    nudges.init_schema(conn)


def _clamp(conn, customer_id: int, as_of: dt.date | None) -> tuple[dt.date, dt.date]:
    rng = db.date_range(conn, customer_id)
    if not rng:
        raise HTTPException(status_code=404, detail="No data for customer")
    lo, hi = rng[0], max(rng[1], DEMO_TODAY)
    top = max(hi, db.future_end(customer_id) or hi)   # Lotte's simulated life timeline
    at = hi if as_of is None else min(max(as_of, lo), top)
    return lo, at


@router.get("/api/me/nudges", response_model=NudgesResponse)
def me_nudges(as_of: dt.date | None = Query(default=None), since: dt.date | None = Query(default=None),
              user: Principal = Depends(auth.require_customer)) -> NudgesResponse:
    with db.tx() as conn:
        lo, at = _clamp(conn, user.customer_id, as_of)
        start = at - dt.timedelta(days=30) if since is None else since
        start = max(start, at - dt.timedelta(days=nudges.MAX_WINDOW_DAYS), lo)
        if start >= at:
            return NudgesResponse(as_of=at, since=at, nudges=[], candidates=0, held=0,
                                  budget=nudges.BudgetInfo(limit=nudges.BUDGET_DEFAULT, used=0, persona="default"))
        return nudges.nudges_for(conn, user.customer_id, start, at)


@router.post("/api/me/nudges/{nudge_key}/ack", response_model=AckResponse)
def me_ack(body: AckRequest, nudge_key: str = Path(pattern=NUDGE_KEY_PATTERN, max_length=121),
           as_of: dt.date | None = Query(default=None),
           user: Principal = Depends(auth.require_customer)) -> AckResponse:
    with db.tx() as conn:
        _, at = _clamp(conn, user.customer_id, as_of)
        try:
            out = nudges.record_ack(conn, user.customer_id, nudge_key, body.action, at)
        except ValueError:
            raise HTTPException(status_code=422, detail="Unknown nudge") from None
        db.audit(conn, user.user_id, f"nudge.{body.action}", nudge_key)
    return out


@router.post("/api/me/nudges-reset")
def me_nudges_reset(user: Principal = Depends(auth.require_customer)) -> dict:
    with db.tx() as conn:
        nudges.reset_acks(conn, user.customer_id)
        db.audit(conn, user.user_id, "nudge.reset", "all")
    return {"ok": True}


@router.get("/api/ecosystem/nudge-stats", response_model=NudgeStats)
def nudge_stats(weeks: int = Query(default=4, ge=1, le=8),
                user: Principal = Depends(auth.require_advisor)) -> NudgeStats:
    with db.tx() as conn:
        db.audit(conn, user.user_id, "nudge.stats", "portfolio")
        return nudges.stats(conn, DEMO_TODAY, weeks)

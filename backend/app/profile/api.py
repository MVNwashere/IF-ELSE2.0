"""Profile endpoints. The customer comes from the session; every change is validated against the field registry and
written to audit_log (the field or purpose name only, never the value). Mounted in main.py."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from .. import auth, db
from ..auth import Principal
from ..ecosystem.service import DEMO_TODAY
from ..schemas import (PROFILE_FACT_KEYS, CorrectionRequest, FactUpdateRequest, PermissionRequest, ProfileResponse,
                       Purpose)
from . import service
from .fields import FactError, validate

router = APIRouter(tags=["profile"])
FACT_KEY_PATTERN = "^(" + "|".join(PROFILE_FACT_KEYS) + ")$"


def _as_of(conn, customer_id: int, as_of: dt.date | None) -> dt.date:
    """Same clamp as the home endpoint: [first transaction, DEMO_TODAY], or up to the simulated future's end."""
    rng = db.date_range(conn, customer_id)
    if not rng:
        raise HTTPException(status_code=404, detail="No data for customer")
    lo, hi = rng[0], max(rng[1], DEMO_TODAY)
    top = max(hi, db.future_end(customer_id) or hi)
    return hi if as_of is None else min(max(as_of, lo), top)


def _build(conn, customer_id: int, at: dt.date) -> ProfileResponse:
    try:
        return service.build(conn, customer_id, at)
    except service.ProfileError as e:
        raise HTTPException(status_code=e.status, detail=e.detail) from None


@router.get("/api/me/profile", response_model=ProfileResponse)
def me_profile(as_of: dt.date | None = Query(default=None),
               user: Principal = Depends(auth.require_customer)) -> ProfileResponse:
    with db.tx() as conn:
        return _build(conn, user.customer_id, _as_of(conn, user.customer_id, as_of))


@router.put("/api/me/profile/facts/{key}", response_model=ProfileResponse)
def me_set_fact(body: FactUpdateRequest, key: str = Path(pattern=FACT_KEY_PATTERN),
                as_of: dt.date | None = Query(default=None),
                user: Principal = Depends(auth.require_customer)) -> ProfileResponse:
    with db.tx() as conn:
        at = _as_of(conn, user.customer_id, as_of)
        if body.via == "kate" and not db.get_permissions(conn, user.customer_id)["kate_memory"]:
            raise HTTPException(status_code=403, detail="You switched off that Kate remembers things")
        try:
            value = validate(key, body.value)
        except FactError as e:
            raise HTTPException(status_code=422, detail=str(e)) from None
        db.set_fact(conn, user.customer_id, key, value, body.via, at)
        db.audit(conn, user.user_id, f"profile.fact.set.{body.via}", key)
        return _build(conn, user.customer_id, at)


@router.delete("/api/me/profile/facts/{key}", response_model=ProfileResponse)
def me_delete_fact(key: str = Path(pattern=FACT_KEY_PATTERN), as_of: dt.date | None = Query(default=None),
                   user: Principal = Depends(auth.require_customer)) -> ProfileResponse:
    with db.tx() as conn:
        at = _as_of(conn, user.customer_id, as_of)
        db.delete_facts(conn, user.customer_id, key=key)
        db.audit(conn, user.user_id, "profile.fact.delete", key)
        return _build(conn, user.customer_id, at)


@router.post("/api/me/profile/forget-kate", response_model=ProfileResponse)
def me_forget_kate(as_of: dt.date | None = Query(default=None),
                   user: Principal = Depends(auth.require_customer)) -> ProfileResponse:
    """"Forget everything I told Kate": every fact saved from a chat goes."""
    with db.tx() as conn:
        at = _as_of(conn, user.customer_id, as_of)
        n = db.delete_facts(conn, user.customer_id, source="kate")
        db.audit(conn, user.user_id, "profile.forget_kate", str(n))
        return _build(conn, user.customer_id, at)


@router.post("/api/me/profile/corrections", response_model=ProfileResponse)
def me_correction(body: CorrectionRequest, as_of: dt.date | None = Query(default=None),
                  user: Principal = Depends(auth.require_customer)) -> ProfileResponse:
    with db.tx() as conn:
        at = _as_of(conn, user.customer_id, as_of)
        try:
            service.check_correction(body.kind, body.target)
        except service.ProfileError as e:
            raise HTTPException(status_code=e.status, detail=e.detail) from None
        db.set_correction(conn, user.customer_id, body.kind, body.target, body.state, at)
        db.audit(conn, user.user_id, f"profile.correction.{body.state}", f"{body.kind}:{body.target}")
        return _build(conn, user.customer_id, at)


@router.put("/api/me/profile/permissions/{purpose}", response_model=ProfileResponse)
def me_permission(body: PermissionRequest, purpose: Purpose, as_of: dt.date | None = Query(default=None),
                  user: Principal = Depends(auth.require_customer)) -> ProfileResponse:
    with db.tx() as conn:
        at = _as_of(conn, user.customer_id, as_of)
        db.set_permission(conn, user.customer_id, purpose, body.allowed)
        db.audit(conn, user.user_id, f"profile.permission.{'on' if body.allowed else 'off'}", purpose)
        return _build(conn, user.customer_id, at)


@router.get("/api/advisor/profile/{username}", response_model=ProfileResponse)
def advisor_profile(username: str = Path(pattern=r"^[a-z0-9_]{1,32}$"),
                    user: Principal = Depends(auth.require_advisor)) -> ProfileResponse:
    """The advisor sees a customer's profile only when that customer allowed it. Every look is audited."""
    with db.tx() as conn:
        row = db.get_user(conn, username)
        if not row or row["role"] != "customer" or row["customer_id"] is None:
            raise HTTPException(status_code=404, detail="Customer not found")
        cid = row["customer_id"]
        allowed = db.get_permissions(conn, cid)["advisor_view"]
        db.audit(conn, user.user_id, "advisor.profile" if allowed else "advisor.profile.denied", username)
        profile = _build(conn, cid, _as_of(conn, cid, None)) if allowed else None
    if profile is None:   # raised after the commit, so the denied attempt stays in the audit log
        raise HTTPException(status_code=403, detail="This customer has not shared their profile with advisors")
    return profile

"""Ecosystem endpoints. Customer endpoints take the customer from the session only; every goal and grant id is
looked up together with that customer id. Partner webhooks are authenticated by signature, not by session."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request

from .. import auth, db
from ..auth import Principal
from . import service, sources, store
from .models import (
    PARTNER_ID_PATTERN, SOURCE_ID_PATTERN, STEP_ID_PATTERN, ConsentsResponse, EcosystemOverview, Goal, GoalsResponse,
    ManifestResult, PartnerManifest, SourceConnectRequest, SourcesResponse, StartGoalRequest, StepDecisionRequest,
)
from .webhooks import MAX_BODY_BYTES, WebhookError

router = APIRouter(tags=["ecosystem"])


def _as_of(conn, customer_id: int, as_of: dt.date | None) -> dt.date:
    """Same clamp as the home endpoint: [first transaction, DEMO_TODAY]."""
    rng = db.date_range(conn, customer_id)
    if not rng:
        raise HTTPException(status_code=404, detail="No data for customer")
    lo, hi = rng[0], max(rng[1], service.DEMO_TODAY)
    return hi if as_of is None else min(max(as_of, lo), hi)


def _raise(e: service.EcosystemError | WebhookError | sources.SourceError):
    raise HTTPException(status_code=e.status, detail=e.detail) from None


@router.get("/api/me/goals", response_model=GoalsResponse)
def me_goals(as_of: dt.date | None = Query(default=None),
             user: Principal = Depends(auth.require_customer)) -> GoalsResponse:
    with db.tx() as conn:
        at = _as_of(conn, user.customer_id, as_of)
        declared = db.get_prefs(conn, user.customer_id).declared
        try:
            return service.goals_response(conn, user.customer_id, at, declared)
        except service.EcosystemError as e:
            _raise(e)


@router.post("/api/me/goals", response_model=Goal)
def me_start_goal(body: StartGoalRequest, as_of: dt.date | None = Query(default=None),
                  user: Principal = Depends(auth.require_customer)) -> Goal:
    with db.tx() as conn:
        at = _as_of(conn, user.customer_id, as_of)
        declared = db.get_prefs(conn, user.customer_id).declared
        try:
            goal = service.start_goal(conn, user.customer_id, body.playbook_id, at, declared)
        except service.EcosystemError as e:
            _raise(e)
        db.audit(conn, user.user_id, "goal.start", body.playbook_id)
    return goal


@router.post("/api/me/goals/{goal_id}/steps/{step_id}", response_model=Goal)
def me_step_decision(body: StepDecisionRequest, goal_id: int = Path(ge=1),
                     step_id: str = Path(pattern=STEP_ID_PATTERN), as_of: dt.date | None = Query(default=None),
                     user: Principal = Depends(auth.require_customer)) -> Goal:
    with db.tx() as conn:
        at = _as_of(conn, user.customer_id, as_of)
        try:
            goal, pending = service.decide_step(conn, user.customer_id, goal_id, step_id, body.decision, at,
                                                body.partner_id)
        except service.EcosystemError as e:
            _raise(e)
        target = f"{goal_id}/{step_id}" + (f" partner={body.partner_id}" if body.partner_id else "")
        db.audit(conn, user.user_id, f"step.{body.decision}", target)
    service.run_simulations(pending)   # after commit: the simulated partner answers through the webhook path
    if pending:
        with db.tx() as conn:          # with a zero delay the partner has already answered
            goal = service.goal_model(conn, store.goal(conn, user.customer_id, goal_id), at)
    return goal


@router.post("/api/me/goals/{goal_id}/cancel")
def me_cancel_goal(goal_id: int = Path(ge=1), as_of: dt.date | None = Query(default=None),
                   user: Principal = Depends(auth.require_customer)) -> dict:
    with db.tx() as conn:
        at = _as_of(conn, user.customer_id, as_of)
        try:
            pending = service.cancel_goal(conn, user.customer_id, goal_id, at) or []
        except service.EcosystemError as e:
            _raise(e)
        db.audit(conn, user.user_id, "goal.cancel", str(goal_id))
    service.run_simulations(pending)   # partners confirm deletion through the signed webhook path
    return {"ok": True}


@router.post("/api/me/goals-reset")
def me_goals_reset(user: Principal = Depends(auth.require_customer)) -> dict:
    with db.tx() as conn:
        store.delete_customer_goals(conn, user.customer_id)
        db.audit(conn, user.user_id, "goal.reset", "all")
    return {"ok": True}


@router.get("/api/me/consents", response_model=ConsentsResponse)
def me_consents(as_of: dt.date | None = Query(default=None),
                user: Principal = Depends(auth.require_customer)) -> ConsentsResponse:
    with db.tx() as conn:
        return service.consents(conn, user.customer_id, _as_of(conn, user.customer_id, as_of))


@router.post("/api/me/consents/{grant_id}/revoke", response_model=ConsentsResponse)
def me_revoke(grant_id: int = Path(ge=1), as_of: dt.date | None = Query(default=None),
              user: Principal = Depends(auth.require_customer)) -> ConsentsResponse:
    with db.tx() as conn:
        at = _as_of(conn, user.customer_id, as_of)
        try:
            pending = service.revoke(conn, user.customer_id, grant_id, at) or []
        except service.EcosystemError as e:
            _raise(e)
        db.audit(conn, user.user_id, "consent.revoke", str(grant_id))
    service.run_simulations(pending)   # the partner deletes the data and confirms with a signed webhook
    with db.tx() as conn:
        return service.consents(conn, user.customer_id, at)


@router.post("/api/partners/{partner_id}/webhook")
async def partner_webhook(request: Request, partner_id: str = Path(pattern=PARTNER_ID_PATTERN)) -> dict:
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Body too large")
    try:
        return service.handle_webhook(partner_id, body, dict(request.headers))
    except WebhookError as e:
        _raise(e)


@router.get("/api/ecosystem/overview", response_model=EcosystemOverview)
def ecosystem_overview(user: Principal = Depends(auth.require_advisor)) -> EcosystemOverview:
    with db.tx() as conn:
        db.audit(conn, user.user_id, "ecosystem.overview", "portfolio")
        return service.overview(conn)


# ---- inbound data sources (data KBC reads, with the customer's OK) -------------------------------------------------


@router.get("/api/me/sources", response_model=SourcesResponse)
def me_sources(as_of: dt.date | None = Query(default=None),
               user: Principal = Depends(auth.require_customer)) -> SourcesResponse:
    with db.tx() as conn:
        try:
            return sources.sources_response(conn, user.customer_id, _as_of(conn, user.customer_id, as_of))
        except sources.SourceError as e:
            _raise(e)


@router.post("/api/me/sources/{source_id}/connect", response_model=SourcesResponse)
def me_source_connect(body: SourceConnectRequest, source_id: str = Path(pattern=SOURCE_ID_PATTERN),
                      as_of: dt.date | None = Query(default=None),
                      user: Principal = Depends(auth.require_customer)) -> SourcesResponse:
    with db.tx() as conn:
        at = _as_of(conn, user.customer_id, as_of)
        try:
            sources.connect(conn, user.customer_id, source_id, body.playbook_id, body.purpose, at)
        except sources.SourceError as e:
            _raise(e)
        db.audit(conn, user.user_id, "source.connect", f"{source_id} for {body.playbook_id}")
        return sources.sources_response(conn, user.customer_id, at)


@router.post("/api/me/sources/{source_id}/disconnect", response_model=SourcesResponse)
def me_source_disconnect(source_id: str = Path(pattern=SOURCE_ID_PATTERN), as_of: dt.date | None = Query(default=None),
                         user: Principal = Depends(auth.require_customer)) -> SourcesResponse:
    with db.tx() as conn:
        at = _as_of(conn, user.customer_id, as_of)
        try:
            sources.disconnect(conn, user.customer_id, source_id, at)
        except sources.SourceError as e:
            _raise(e)
        db.audit(conn, user.user_id, "source.disconnect", source_id)
        return sources.sources_response(conn, user.customer_id, at)


# ---- partner onboarding (KBC staff only) ----------------------------------------------------------------------------


@router.post("/api/ecosystem/partners/manifest", response_model=ManifestResult)
def partner_manifest(body: PartnerManifest, user: Principal = Depends(auth.require_advisor)) -> ManifestResult:
    result = service.validate_manifest(body)
    with db.tx() as conn:
        db.audit(conn, user.user_id, "partner.manifest", f"{body.id} valid={result.valid}")
    return result


@router.get("/api/ecosystem/partners/onboarding", response_model=list[PartnerManifest])
def partner_onboarding(user: Principal = Depends(auth.require_advisor)) -> list[PartnerManifest]:
    return service.onboarded()

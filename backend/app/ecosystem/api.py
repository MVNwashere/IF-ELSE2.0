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
    HouseholdAnswerRequest, HouseholdInviteRequest, ManifestResult, PartnerManifest, PartnerSimRequest,
    SourceConnectRequest, SourcesResponse, StallAnswerRequest, StartGoalRequest, StepDecisionRequest,
)
from .webhooks import MAX_BODY_BYTES, WebhookError

router = APIRouter(tags=["ecosystem"])


def _as_of(conn, customer_id: int, as_of: dt.date | None) -> dt.date:
    """Same clamp as the home endpoint: [first transaction, DEMO_TODAY], or up to the simulated future's end."""
    rng = db.date_range(conn, customer_id)
    if not rng:
        raise HTTPException(status_code=404, detail="No data for customer")
    lo, hi = rng[0], max(rng[1], service.DEMO_TODAY)
    top = max(hi, db.future_end(customer_id) or hi)
    return hi if as_of is None else min(max(as_of, lo), top)


def _raise(e: service.EcosystemError | WebhookError | sources.SourceError):
    raise HTTPException(status_code=e.status, detail=e.detail) from None


@router.get("/api/me/goals", response_model=GoalsResponse)
def me_goals(as_of: dt.date | None = Query(default=None),
             user: Principal = Depends(auth.require_customer)) -> GoalsResponse:
    with db.tx() as conn:
        at = _as_of(conn, user.customer_id, as_of)
        declared = db.get_prefs(conn, user.customer_id).declared
        pending = service.sweep_timeouts(conn, at, user.customer_id)   # partners that missed their SLA
        try:
            response = service.goals_response(conn, user.customer_id, at, declared)
        except service.EcosystemError as e:
            _raise(e)
    service.run_simulations(pending)   # timed-out partners are asked to delete the data
    return response


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
            goal = service.goal_model(conn, store.goal_for(conn, user.customer_id, goal_id), at,
                                      viewer=user.customer_id)
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


@router.post("/api/me/goals/{goal_id}/household", response_model=Goal)
def me_household_invite(body: HouseholdInviteRequest, goal_id: int = Path(ge=1),
                        as_of: dt.date | None = Query(default=None),
                        user: Principal = Depends(auth.require_customer)) -> Goal:
    """Share a goal with a household member. Owner only; the member must accept."""
    with db.tx() as conn:
        at = _as_of(conn, user.customer_id, as_of)
        try:
            goal = service.invite_member(conn, user.customer_id, goal_id, body.username, at)
        except service.EcosystemError as e:
            _raise(e)
        db.audit(conn, user.user_id, "household.invite", f"{goal_id} → {body.username}")
    return goal


@router.post("/api/me/household/{goal_id}")
def me_household_answer(body: HouseholdAnswerRequest, goal_id: int = Path(ge=1),
                        as_of: dt.date | None = Query(default=None),
                        user: Principal = Depends(auth.require_customer)) -> dict:
    with db.tx() as conn:
        at = _as_of(conn, user.customer_id, as_of)
        try:
            service.answer_invitation(conn, user.customer_id, goal_id, body.accept, at)
        except service.EcosystemError as e:
            _raise(e)
        db.audit(conn, user.user_id, "household.accept" if body.accept else "household.decline", str(goal_id))
    return {"ok": True}


@router.post("/api/me/goals/{goal_id}/stall")
def me_stall_answer(body: StallAnswerRequest, goal_id: int = Path(ge=1), as_of: dt.date | None = Query(default=None),
                    user: Principal = Depends(auth.require_customer)) -> dict:
    """Answer the "still want this?" prompt: keep, pause (no reminders), resume or stop."""
    with db.tx() as conn:
        at = _as_of(conn, user.customer_id, as_of)
        try:
            pending = service.answer_stall(conn, user.customer_id, goal_id, body.answer, at)
        except service.EcosystemError as e:
            _raise(e)
        db.audit(conn, user.user_id, f"goal.{body.answer}", str(goal_id))
    service.run_simulations(pending)
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
        pending = service.sweep_timeouts(conn, service.DEMO_TODAY)
        result = service.overview(conn)
    service.run_simulations(pending)
    return result


@router.post("/api/ecosystem/partners/{partner_id}/simulate")
def partner_simulate(body: PartnerSimRequest, partner_id: str = Path(pattern=PARTNER_ID_PATTERN),
                     user: Principal = Depends(auth.require_advisor)) -> dict:
    """Demo switch (KBC staff only): how a simulated partner answers from now on: done, late, reject, fail, timeout."""
    try:
        result = service.set_partner_sim(partner_id, body.mode)
    except service.EcosystemError as e:
        _raise(e)
    with db.tx() as conn:
        db.audit(conn, user.user_id, "partner.simulate", f"{partner_id}={body.mode}")
    return result


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

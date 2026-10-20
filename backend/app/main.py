"""KBC Adaptive Home API.

- Customer endpoints derive the customer from the session cookie. No customer IDs in URLs (no IDOR).
- Every body/query is a Pydantic model (schemas.py). `as_of` is clamped to the customer's data range.
- Advisor endpoints check the role server-side and write to audit_log.
- Security headers + CSP on every response.
"""
from __future__ import annotations

import datetime as dt
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import auth, db
from .auth import Principal
from .customer_state.api import router as customer_state_router
from .customer_state.service import get_state
from .engine import kate, pipeline
from .engine.persona import dominant
from .recommender.feed import recommend
from .schemas import (
    HERO_COMPONENTS, AdvisorOverview, ConsentRequest, DeclareRequest, FeedbackRequest, FeedPersona, HomeResponse, KateReply,
    KateRequest, LayoutPrefRequest, LoginRequest, LoginResponse, StylePrefs, SuggestionRequest, TimelineResponse,
)

HERE = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIST = os.path.abspath(os.path.join(HERE, "..", "..", "frontend", "dist"))
SYNTH_N = int(os.environ.get("SYNTH_N", "1000"))
SYNTH_SEED = int(os.environ.get("SYNTH_SEED", "42"))
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"
PORTFOLIO_SIZE = 2_300_000
KATE_MAX_PER_MINUTE = 30
# The synthetic dataset's reference "today". Time travel is clamped to [first transaction, DEMO_TODAY].
DEMO_TODAY = dt.date.fromisoformat(os.environ.get("DEMO_TODAY", "2026-09-30"))


def ensure_db() -> None:
    if os.path.exists(db.DB_PATH):
        return
    from synth.generate import build  # lazy: heavy import, only on first start

    build(db.DB_PATH, n=SYNTH_N, seed=SYNTH_SEED)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_db()
    with db.tx() as conn:
        db.init_schema(conn)  # idempotent; migrates databases built by older versions
    yield


app = FastAPI(title="KBC Adaptive Home", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

app.include_router(customer_state_router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
        "base-uri 'self'; form-action 'self'"
    )
    return response


# ----------------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------------


def _effective_as_of(conn, customer_id: int, as_of: dt.date | None) -> dt.date:
    """Clamp the requested date to [first transaction, DEMO_TODAY]. Never the future."""
    rng = db.date_range(conn, customer_id)
    if not rng:
        raise HTTPException(status_code=404, detail="No data for customer")
    lo, hi = rng
    hi = max(hi, DEMO_TODAY)
    return hi if as_of is None else min(max(as_of, lo), hi)


def _load_and_build(customer_id: int, as_of: dt.date | None, touch: bool = True):
    with db.tx() as conn:
        customer = db.get_customer(conn, customer_id)
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        effective = _effective_as_of(conn, customer_id, as_of)
        txs = db.get_transactions(conn, customer_id)
        balance_today = db.get_balance_today(conn, customer_id)
        prefs = db.get_prefs(conn, customer_id)
        home, features = pipeline.build_home_with_features(customer, txs, balance_today, prefs, effective)
        if touch:
            db.touch_visit(conn, customer_id, effective)
        state = get_state(conn, customer_id, effective, balance_reference=DEMO_TODAY)
        home.feed, personas = recommend(customer, state, prefs)
        home.feed_personas = [FeedPersona.model_validate(persona) for persona in personas]
    return home, features


def _home(customer_id: int, as_of: dt.date | None) -> HomeResponse:
    return _load_and_build(customer_id, as_of)[0]


def _pin(conn, customer_id: int, component: str, at: dt.date, position: int | None) -> None:
    if component in HERO_COMPONENTS:
        db.unpin_heroes(conn, customer_id, HERO_COMPONENTS)  # one main tile at a time
    db.set_layout_pref(conn, customer_id, component, "pinned", at, position)


_kate_calls: dict[int, deque] = defaultdict(deque)


def _kate_rate_limit(user_id: int) -> None:
    now = time.time()
    q = _kate_calls[user_id]
    while q and q[0] < now - 60:
        q.popleft()
    if len(q) >= KATE_MAX_PER_MINUTE:
        raise HTTPException(status_code=429, detail="Kate needs a breather, try again in a minute")
    q.append(now)


def _as_of_param(as_of: dt.date | None = Query(default=None)) -> dt.date | None:
    return as_of


# ----------------------------------------------------------------------------------
# Auth
# ----------------------------------------------------------------------------------


@app.post("/api/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request, response: Response) -> LoginResponse:
    ip = request.client.host if request.client else "unknown"
    auth.check_rate_limit(f"u:{body.username}")
    auth.check_rate_limit(f"ip:{ip}")
    with db.tx() as conn:
        row = db.get_user(conn, body.username)
    if not row or not auth.verify_password(body.password, row["password_hash"]):
        auth.record_attempt(f"u:{body.username}")
        auth.record_attempt(f"ip:{ip}")
        raise HTTPException(status_code=401, detail="Invalid username or password")
    auth.set_session_cookie(response, auth.make_session(row["id"], row["role"]), secure=COOKIE_SECURE)
    return LoginResponse(role=row["role"], username=row["username"])


@app.post("/api/logout")
def logout(response: Response) -> dict:
    auth.clear_session_cookie(response)
    return {"ok": True}


@app.get("/api/me/session", response_model=LoginResponse)
def session(user: Principal = Depends(auth.current_user)) -> LoginResponse:
    return LoginResponse(role=user.role, username=user.username)


# ----------------------------------------------------------------------------------
# Customer
# ----------------------------------------------------------------------------------


@app.get("/api/me/home", response_model=HomeResponse)
def me_home(as_of: dt.date | None = Depends(_as_of_param),
            user: Principal = Depends(auth.require_customer)) -> HomeResponse:
    return _home(user.customer_id, as_of)


@app.get("/api/me/timeline", response_model=TimelineResponse)
def me_timeline(user: Principal = Depends(auth.require_customer)) -> TimelineResponse:
    with db.tx() as conn:
        customer = db.get_customer(conn, user.customer_id)
        txs = db.get_transactions(conn, user.customer_id)
        balance_today = db.get_balance_today(conn, user.customer_id)
    if not customer or not txs:
        raise HTTPException(status_code=404, detail="No data for customer")
    tl = pipeline.build_timeline(customer, txs, balance_today)
    tl.max_date = max(tl.max_date, DEMO_TODAY)
    return tl


@app.post("/api/me/feedback", response_model=HomeResponse)
def me_feedback(body: FeedbackRequest, as_of: dt.date | None = Depends(_as_of_param),
                user: Principal = Depends(auth.require_customer)) -> HomeResponse:
    with db.tx() as conn:
        at = _effective_as_of(conn, user.customer_id, as_of)
        db.add_feedback(conn, user.customer_id, body.card_key, body.card_type, body.decision, at)
    return _home(user.customer_id, as_of)


@app.post("/api/me/layout-prefs", response_model=HomeResponse)
def me_layout_prefs(body: LayoutPrefRequest, as_of: dt.date | None = Depends(_as_of_param),
                    user: Principal = Depends(auth.require_customer)) -> HomeResponse:
    with db.tx() as conn:
        at = _effective_as_of(conn, user.customer_id, as_of)
        if body.state == "pinned":
            _pin(conn, user.customer_id, body.component, at, body.position)
        else:
            db.set_layout_pref(conn, user.customer_id, body.component, body.state, at)
    return _home(user.customer_id, as_of)


@app.post("/api/me/layout-reset", response_model=HomeResponse)
def me_layout_reset(as_of: dt.date | None = Depends(_as_of_param),
                    user: Principal = Depends(auth.require_customer)) -> HomeResponse:
    with db.tx() as conn:
        db.reset_layout(conn, user.customer_id)
    return _home(user.customer_id, as_of)


@app.post("/api/me/style", response_model=HomeResponse)
def me_style(body: StylePrefs, as_of: dt.date | None = Depends(_as_of_param),
             user: Principal = Depends(auth.require_customer)) -> HomeResponse:
    with db.tx() as conn:
        db.set_style(conn, user.customer_id, body)
    return _home(user.customer_id, as_of)


@app.post("/api/me/suggestion", response_model=HomeResponse)
def me_suggestion(body: SuggestionRequest, as_of: dt.date | None = Depends(_as_of_param),
                  user: Principal = Depends(auth.require_customer)) -> HomeResponse:
    with db.tx() as conn:
        at = _effective_as_of(conn, user.customer_id, as_of)
        if body.decision == "accept":
            _pin(conn, user.customer_id, body.component, at, None)
        else:
            db.dismiss_suggestion(conn, user.customer_id, body.component, at)
    return _home(user.customer_id, as_of)


@app.post("/api/me/declare", response_model=HomeResponse)
def me_declare(body: DeclareRequest, as_of: dt.date | None = Depends(_as_of_param),
               user: Principal = Depends(auth.require_customer)) -> HomeResponse:
    with db.tx() as conn:
        at = _effective_as_of(conn, user.customer_id, as_of)
        db.set_declared(conn, user.customer_id, body.signal, body.state, at)
        db.audit(conn, user.user_id, f"declare.{body.state}", body.signal)
    return _home(user.customer_id, as_of)


@app.post("/api/me/kate", response_model=KateReply)
def me_kate(body: KateRequest, as_of: dt.date | None = Depends(_as_of_param),
            user: Principal = Depends(auth.require_customer)) -> KateReply:
    _kate_rate_limit(user.user_id)
    home, features = _load_and_build(user.customer_id, as_of, touch=False)
    return kate.reply(home, features, body)


@app.post("/api/me/consent", response_model=HomeResponse)
def me_consent(body: ConsentRequest, as_of: dt.date | None = Depends(_as_of_param),
               user: Principal = Depends(auth.require_customer)) -> HomeResponse:
    with db.tx() as conn:
        db.set_consent(conn, user.customer_id, body.consent_personalization)
    return _home(user.customer_id, as_of)


# ----------------------------------------------------------------------------------
# Advisor (stretch): portfolio overview + scale projection
# ----------------------------------------------------------------------------------

_overview_cache: AdvisorOverview | None = None


@app.get("/api/advisor/overview", response_model=AdvisorOverview)
def advisor_overview(user: Principal = Depends(auth.require_advisor)) -> AdvisorOverview:
    global _overview_cache
    with db.tx() as conn:
        db.audit(conn, user.user_id, "advisor.overview", "portfolio")
    if _overview_cache:
        return _overview_cache

    persona_dist: dict[str, int] = {}
    card_volume: dict[str, int] = {}
    eur_total = 0.0
    with db.tx() as conn:
        ids = db.all_customer_ids(conn)
        started = time.perf_counter()
        for cid in ids:
            customer = db.get_customer(conn, cid)
            txs = db.get_transactions(conn, cid)
            if not customer or not txs:
                continue
            balance_today = db.get_balance_today(conn, cid)
            prefs = db.get_prefs(conn, cid)
            home = pipeline.build_home(customer, txs, balance_today, prefs, max(txs[-1].date, DEMO_TODAY))
            dom = dominant(home.persona_mix)
            persona_dist[dom] = persona_dist.get(dom, 0) + 1
            for card in home.feed.cards:
                card_volume[card.card_type] = card_volume.get(card.card_type, 0) + 1
                eur_total += abs(card.eur_impact)
        elapsed_ms = (time.perf_counter() - started) * 1000
    n = max(1, len(ids))
    _overview_cache = AdvisorOverview(
        customers_scored=len(ids),
        scoring_ms=round(elapsed_ms, 1),
        projected_2_3m_seconds=round(elapsed_ms / 1000 / n * PORTFOLIO_SIZE, 1),
        persona_distribution=persona_dist,
        card_volume=card_volume,
        eur_impact_total=round(eur_total, 2),
    )
    return _overview_cache


# ----------------------------------------------------------------------------------
# Static frontend (production build), if present
# ----------------------------------------------------------------------------------

if (os.path.isfile(os.path.join(FRONTEND_DIST, "index.html"))
        and os.path.isdir(os.path.join(FRONTEND_DIST, "assets"))):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        candidate = os.path.abspath(os.path.join(FRONTEND_DIST, path))
        if path and os.path.commonpath((FRONTEND_DIST, candidate)) == FRONTEND_DIST and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))

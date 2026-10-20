"""The customer profile: everything KBC knows and uses about one customer, on one page.

Three layers: what the customer told us (facts and declared life changes), what the engine worked out (persona mix
and suggested goals, each with its evidence), and where data comes from or goes to (the consent passport, summarised).
The customer decides per purpose what their data may be used for (PURPOSE_DEFS).
"""
from __future__ import annotations

import datetime as dt

from .. import db
from ..ecosystem import service as ecosystem
from ..ecosystem.registry import registry
from ..engine.features import compute_features
from ..engine.layout import PERSONA_LABEL
from ..engine.persona import DECLARED_PHRASE, infer_persona_mix
from ..schemas import (PERSONAS, CorrectionView, DataAccessSummary, DeclaredView, FieldOption, InferredGoal, InferredPersona,
                       PermissionView, PersonaWeight, ProfileField, ProfileResponse)
from .fields import FIELDS, PURPOSE_DEFS, value_label


class ProfileError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


def _persona_mix(conn, customer_id: int, as_of: dt.date, prefs) -> list[PersonaWeight]:
    customer = db.get_customer(conn, customer_id)
    if not customer:
        raise ProfileError(404, "Customer not found")
    txs = db.get_transactions(conn, customer_id)
    features = compute_features(customer, txs, db.get_balance_today(conn, customer_id), as_of)
    return infer_persona_mix(features, prefs.declared, prefs.facts, prefs.corrections)


def correction_label(kind: str, target: str) -> str:
    if kind == "persona":
        return f"Not {PERSONA_LABEL.get(target, target.replace('_', ' '))}"
    pb = registry().playbooks.get(target)
    return f"Not interested: {pb.title if pb else target.replace('_', ' ')}"


def build(conn, customer_id: int, as_of: dt.date, persona_mix: list[PersonaWeight] | None = None) -> ProfileResponse:
    """`persona_mix`: pass the home screen's when it is already computed (Kate does), to skip a second pass."""
    customer = db.get_customer(conn, customer_id)
    if not customer:
        raise ProfileError(404, "Customer not found")
    prefs = db.get_prefs(conn, customer_id)
    stated = {f.key: f for f in prefs.facts}
    fields = []
    for f in FIELDS.values():
        row = stated.get(f.key)
        fields.append(ProfileField(
            key=f.key, label=f.label, category=f.category, kind=f.kind, hint=f.hint,
            options=[FieldOption(value=v, label=lbl) for v, lbl in f.options.items()], min=f.min, max=f.max,
            used_for=list(f.used_for), value=row.value if row else None,
            value_label=value_label(f.key, row.value) if row else None, source=row.source if row else None,
            updated_on=row.updated_at if row else None))

    mix = persona_mix if persona_mix is not None else _persona_mix(conn, customer_id, as_of, prefs)
    personas = [InferredPersona(persona=p.persona, label=PERSONA_LABEL[p.persona], weight_pct=round(p.weight * 100),
                                evidence=p.evidence, from_you=any(e.startswith("You told") for e in p.evidence))
                for p in mix]
    ctx = ecosystem.context_for(conn, customer_id, as_of)
    goals = [InferredGoal(playbook_id=c.playbook_id, title=c.title, evidence=c.evidence)
             for c in ecosystem.candidates(conn, ctx, prefs.declared)]

    consents = ecosystem.consents(conn, customer_id, as_of)
    access = DataAccessSummary(partners_with_access=consents.partners_with_access,
                               fields_shared=consents.fields_shared,
                               sources_connected=sum(1 for s in consents.sources if s.status == "connected"))
    return ProfileResponse(
        as_of=as_of, first_name=customer.first_name, fields=fields,
        declared=[DeclaredView(signal=d.signal, label=DECLARED_PHRASE[d.signal].capitalize(), created_on=d.created_at)
                  for d in prefs.declared],
        personas=personas, goals=goals,
        corrections=[CorrectionView(kind=c.kind, target=c.target, label=correction_label(c.kind, c.target),
                                    created_on=c.created_at) for c in prefs.corrections],
        permissions=[PermissionView(purpose=p.purpose, label=p.label, description=p.description, when_off=p.when_off,
                                    allowed=prefs.allows(p.purpose)) for p in PURPOSE_DEFS.values()],
        data_access=access,
    )


def check_correction(kind: str, target: str) -> None:
    known = PERSONAS if kind == "persona" else tuple(registry().playbooks)
    if target not in known:
        raise ProfileError(422, f"Unknown {kind}")

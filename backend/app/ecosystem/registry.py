"""Static ecosystem configuration: KBC's catalogue, the vetted partner registry and the goal playbooks.

All three are checked-in JSON files, validated once at import. A broken playbook fails at startup, never in
front of a customer. No LLM decides which partner gets data: the playbook and the registry do.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

from .models import (
    PARTNER_ID_PATTERN, PLAYBOOK_ID_PATTERN, STEP_ID_PATTERN, CatalogueItem, DataField, Estimates, Partner,
    ProductRef, ProviderPublic, Win,
)

HERE = Path(__file__).resolve().parent


class PlaybookStep(BaseModel):
    id: str = Field(pattern=STEP_ID_PATTERN)
    title: str
    provider: str = Field(pattern=PARTNER_ID_PATTERN)
    description: str
    why: str
    products: list[str]
    fields: list[str] = Field(default_factory=list)
    consent_days: int = Field(default=0, ge=0, le=730)
    held_if: list[str] = Field(default_factory=list)       # internal product codes that make the step unnecessary
    kbc_products: list[str] = Field(default_factory=list)  # catalogue ids KBC activates when the step completes
    win: Win
    estimates: Estimates
    result: str


class Playbook(BaseModel):
    id: str = Field(pattern=PLAYBOOK_ID_PATTERN)
    title: str
    icon: str
    tagline: str
    ecosystems: list[str]
    target_days: int
    next_goal: str | None = None
    trigger: str
    steps: list[PlaybookStep]


class Registry(BaseModel):
    catalogue: dict[str, CatalogueItem]
    fields: dict[str, DataField]
    never_shared_default: list[str]
    partners: dict[str, Partner]
    playbooks: dict[str, Playbook]
    # "playbook/step" -> partners the customer may choose from (the playbook's provider is always allowed)
    alternatives: dict[str, list[str]] = Field(default_factory=dict)

    def options(self, playbook_id: str, step: PlaybookStep) -> list[str]:
        """Every partner allowed to do this step, ranked by outcome rate, then customer rating. Never by fee."""
        ids = [step.provider] + [p for p in self.alternatives.get(f"{playbook_id}/{step.id}", [])
                                 if p != step.provider and p in self.partners]
        if len(ids) == 1:
            return ids
        return sorted(ids, key=lambda i: (-(self.partners[i].outcome_rate or 0), -(self.partners[i].rating or 0), i))

    def product(self, item_id: str) -> ProductRef:
        c = self.catalogue[item_id]
        return ProductRef(id=c.id, name=c.name, ecosystem=c.ecosystem, partner=c.partner)

    def provider(self, partner_id: str) -> ProviderPublic:
        p = self.partners[partner_id]
        return ProviderPublic(id=p.id, name=p.name, kind=p.kind, blurb=p.blurb, vetting=p.vetting,
                              integration=p.integration)

    def step(self, playbook_id: str, step_id: str) -> PlaybookStep | None:
        pb = self.playbooks.get(playbook_id)
        return next((s for s in pb.steps if s.id == step_id), None) if pb else None

    def used_building_blocks(self) -> set[str]:
        return {pid for pb in self.playbooks.values() for s in pb.steps for pid in s.products}


SENSITIVE_NEVER_TO_PARTNERS = ("income", "balances", "transactions")


def partner_problems(reg: Registry, p: Partner | object) -> list[str]:
    """Rules every partner must pass, from partners.json or from an onboarding manifest."""
    problems = [f"partner {p.id}: unknown catalogue id {c}" for c in p.catalogue_ids if c not in reg.catalogue]
    problems += [f"partner {p.id}: unknown field {f}" for f in p.allowed_fields if f not in reg.fields]
    if getattr(p, "kind", "partner") == "partner":
        problems += [f"partner {p.id}: field {f} may never go to an outside partner" for f in p.allowed_fields
                     if f in SENSITIVE_NEVER_TO_PARTNERS]
    return problems


def _validate(reg: Registry) -> None:
    problems: list[str] = []
    for p in reg.partners.values():
        problems += partner_problems(reg, p)
    for key, ids in reg.alternatives.items():
        pid, _, sid = key.partition("/")
        step = reg.step(pid, sid)
        for alt in ids:
            partner = reg.partners.get(alt)
            if not partner or partner.kind != "partner":
                problems.append(f"alternatives {key}: {alt} is not a vetted partner")
            elif step is not None:   # playbooks owned elsewhere may not exist yet: only check the ones that do
                if reg.partners[step.provider].kind != "partner":
                    problems.append(f"alternatives {key}: only partner steps can have alternatives")
                problems += [f"alternatives {key}: field {f} not allowed for {alt}" for f in step.fields
                             if f not in partner.allowed_fields]
    for pb in reg.playbooks.values():
        if pb.next_goal and pb.next_goal not in reg.playbooks:
            problems.append(f"playbook {pb.id}: unknown next_goal {pb.next_goal}")
        if len({s.id for s in pb.steps}) != len(pb.steps):
            problems.append(f"playbook {pb.id}: duplicate step ids")
        for s in pb.steps:
            where = f"playbook {pb.id} step {s.id}"
            partner = reg.partners.get(s.provider)
            if not partner:
                problems.append(f"{where}: unknown provider {s.provider}")
                continue
            problems += [f"{where}: unknown catalogue id {c}" for c in s.products + s.kbc_products if c not in reg.catalogue]
            # data minimisation, enforced at startup: a step can never ask for more than the partner may receive
            problems += [f"{where}: field {f} not allowed for {partner.id}" for f in s.fields
                         if f not in partner.allowed_fields]
            if partner.kind == "advisor" and s.fields:
                problems.append(f"{where}: an advisor step keeps data inside KBC and lists no fields")
            if partner.kind == "partner" and (not s.fields or s.consent_days <= 0):
                problems.append(f"{where}: a partner step needs fields and consent_days")
    if problems:
        raise ValueError("Invalid ecosystem configuration:\n  " + "\n  ".join(problems))


@lru_cache(maxsize=1)
def registry() -> Registry:
    catalogue = [CatalogueItem.model_validate(c)
                 for c in json.loads((HERE / "catalogue.json").read_text(encoding="utf-8"))]
    raw = json.loads((HERE / "partners.json").read_text(encoding="utf-8"))
    playbooks = [Playbook.model_validate_json(p.read_text(encoding="utf-8"))
                 for p in sorted((HERE / "playbooks").glob("*.json"))]
    # human handoff: route a KBC step to a KBC advisor (partners.json "advisor_steps", "playbook/step" -> advisor)
    for key, advisor in raw.get("advisor_steps", {}).items():
        pid, _, sid = key.partition("/")
        for pb in playbooks:
            for st in pb.steps:
                if pb.id == pid and st.id == sid and st.provider == "kbc" and not st.fields:
                    st.provider = advisor
    reg = Registry(
        catalogue={c.id: c for c in catalogue},
        fields={f["field"]: DataField.model_validate(f) for f in raw["fields"]},
        never_shared_default=raw["never_shared_default"],
        partners={p["id"]: Partner.model_validate(p) for p in raw["partners"]},
        playbooks={p.id: p for p in playbooks},
        alternatives=raw.get("alternatives", {}),
    )
    _validate(reg)
    return reg

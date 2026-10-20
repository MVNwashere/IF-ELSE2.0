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


def _validate(reg: Registry) -> None:
    problems: list[str] = []
    for p in reg.partners.values():
        problems += [f"partner {p.id}: unknown catalogue id {c}" for c in p.catalogue_ids if c not in reg.catalogue]
        problems += [f"partner {p.id}: unknown field {f}" for f in p.allowed_fields if f not in reg.fields]
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
    reg = Registry(
        catalogue={c.id: c for c in catalogue},
        fields={f["field"]: DataField.model_validate(f) for f in raw["fields"]},
        never_shared_default=raw["never_shared_default"],
        partners={p["id"]: Partner.model_validate(p) for p in raw["partners"]},
        playbooks={p.id: p for p in playbooks},
    )
    _validate(reg)
    return reg

"""Turn feed cards from advice into action: link each card to the goal journey and KBC building blocks behind it.

A card about mortgage readiness no longer ends in "read more": its button starts the "Buy your first home"
journey, and its detail shows the catalogue products (and partners) that journey uses.
"""
from __future__ import annotations

from ..schemas import Cta, Feed
from .registry import registry

# feed catalogue card id (docs/feed-specs) → playbook(s); the first one relevant to the customer wins
CARD_PLAYBOOK: dict[str, str | tuple[str, ...]] = {
    **dict.fromkeys(["EC-05", "EC-06", "HM-01", "HM-02", "HM-03", "LE-01"], "buy_home"),
    **dict.fromkeys(["HM-07", "HM-08", "LE-11"], "energy_upgrade"),
    **dict.fromkeys(["LE-02", "FM-05", "FM-06", "FM-07"], "new_baby"),
    **dict.fromkeys(["BZ-01", "BZ-02", "BZ-04", "BZ-05", "BZ-06", "BZ-07", "BZ-08"], "go_freelance"),
    "BZ-03": "get_paid",
    **dict.fromkeys(["RT-01", "RT-02", "RT-03", "RT-04", "RT-07", "RT-08"], "retire_well"),
    **dict.fromkeys(["TR-01", "TR-02", "TR-03", "TR-04", "TR-06", "TR-07", "TR-10"], "travel"),
    **dict.fromkeys(["EL-02", "EL-03", "EL-05", "EL-08", "LE-05"], "peace_of_mind"),
    **dict.fromkeys(["LE-07", "LE-09", "RT-10", "SV-05"], ("retire_well", "peace_of_mind")),
    **dict.fromkeys(["SV-07", "SV-08", "SV-10", "EC-08"], ("retire_well",)),
}
# legacy (v1) card types → playbook
LEGACY_PLAYBOOK = {"late_client": "get_paid", "vat_reserve": "go_freelance", "new_payee": "peace_of_mind",
                   "idle_cash": "peace_of_mind", "pension_savings": "retire_well"}
MAX_PRODUCTS = 4


def products_for(playbook_id: str) -> list[dict]:
    reg = registry()
    ids: list[str] = []
    for step in reg.playbooks[playbook_id].steps:
        for p in step.products:
            if p not in ids:
                ids.append(p)
    # partners first: they're what makes it an ecosystem
    ids.sort(key=lambda i: reg.catalogue[i].partner is None)
    return [reg.product(i).model_dump() for i in ids[:MAX_PRODUCTS]]


def enrich_feed(feed: Feed, relevant: set[str]) -> Feed:
    """`relevant`: playbooks detected for this customer or already running. A card only links to a journey that
    fits the customer (a retiree's healthcare card must not start a pre-retirement plan)."""
    reg = registry()
    for card in feed.cards:
        options = CARD_PLAYBOOK.get(card.details.get("catalogue_id", "")) or LEGACY_PLAYBOOK.get(card.card_type)
        options = (options,) if isinstance(options, str) else (options or ())
        playbook_id = next((p for p in options if p in relevant and p in reg.playbooks), None)
        if not playbook_id:
            continue
        card.details["playbook_id"] = playbook_id
        card.details["playbook_title"] = reg.playbooks[playbook_id].title
        card.details["products"] = products_for(playbook_id)
        if card.cta is None:
            card.cta = Cta(label="Let KBC take care of it", action="start_goal")
    return feed

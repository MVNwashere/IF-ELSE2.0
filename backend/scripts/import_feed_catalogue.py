"""One-time import of the supplied product catalogue into checked-in structured data.

Run without arguments after editing docs/feed-specs/03_feed_cards_catalogue.md.
The app reads only the resulting JSON.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

CORE_TITLES = {
    "your money": "core_money", "monthly spending": "core_spending",
    "spending this month": "core_spending", "coming up": "core_coming_up",
    "unusual activity": "core_unusual", "insurance": "core_insurance",
    "your goals": "core_goals", "savings goals": "core_goals",
    "investments": "core_investments", "what you owe": "core_debt",
    "your cards": "core_cards", "financial health": "core_health",
}


def main(source: Path) -> None:
    raw = source.read_text(encoding="utf-8")
    blocks = re.split(r"(?=^### [A-Z]{2}-\d{2} · )", raw, flags=re.M)
    cards = []
    for block in blocks:
        match = re.match(r"### ([A-Z]{2}-\d{2}) · (.+)", block)
        if not match:
            continue
        code, title = match.groups()
        kind = re.search(r"\*\*Type:\*\* (\w+)", block)
        fits = re.search(r"\*\*Fits:\*\* ([^\n]+)", block)
        summary = re.search(r"\*\*What it is:\*\* ([^\n]+)", block)
        feed_design = re.search(r"\*\*In the feed:\*\* ([^\n]+)", block)
        detail = re.search(r"\*\*When clicked:\*\* ([^\n]+)", block)
        related = re.search(r"Related cards?: ([^\n]+)", block)
        if not all((kind, fits, summary, feed_design, detail)):
            raise ValueError(f"Incomplete catalogue entry: {code}")
        audience = re.findall(r"\b(?:TEEN|STU|YPRO|PAR|HOME|SELF|INV|PRE|SEN)\b", fits.group(1))
        if not audience and "All" in fits.group(1):
            audience = ["STU", "YPRO", "PAR", "HOME", "SELF", "INV", "PRE", "SEN"]
            if "customers" in fits.group(1):
                audience.insert(0, "TEEN")
        cards.append({
            "id": code, "title": title, "type": kind.group(1), "fits": audience,
            "fit_rule": fits.group(1).strip(), "summary": summary.group(1).strip(),
            "feed_design": feed_design.group(1).strip(),
            "detail": re.split(r"Related cards?:", detail.group(1))[0].strip(),
            "related_titles": [v.strip().rstrip(".") for v in related.group(1).rstrip(".").split(", ")] if related else [],
        })
    if len(cards) != 100:
        raise ValueError(f"Expected 100 cards, found {len(cards)}")
    by_title = {c["title"].lower(): c["id"] for c in cards}
    for card in cards:
        names = card.pop("related_titles")
        card["related"] = [by_title[t.lower()] for t in names if t.lower() in by_title]
        card["related_core"] = [CORE_TITLES[t.lower()] for t in names if t.lower() in CORE_TITLES]
    target = Path(__file__).resolve().parents[1] / "app" / "recommender" / "catalogue.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(cards, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(cards)} cards to {target}")


if __name__ == "__main__":
    default = Path(__file__).resolve().parents[2] / "docs" / "feed-specs" / "03_feed_cards_catalogue.md"
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else default)

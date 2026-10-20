"""Rebuild app/ecosystem/catalogue.json from docs/reference/KBC_Ecosystems.xlsx (KBC's own list of building blocks).

Dev-only: needs openpyxl (`py -3.12 -m pip install openpyxl`). The JSON is checked in, so the app never reads Excel.
Run from backend/: `py -3.12 -m scripts.import_ecosystems`
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "docs" / "reference" / "KBC_Ecosystems.xlsx"
OUT = ROOT / "backend" / "app" / "ecosystem" / "catalogue.json"


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


def main() -> None:
    import openpyxl

    ws = openpyxl.load_workbook(SRC, read_only=True).worksheets[0]
    items, seen = [], set()
    for row in list(ws.iter_rows(values_only=True))[1:]:
        if not row or not row[0] or not row[1]:
            continue
        ecosystem, name = str(row[0]).strip(), str(row[1]).strip()
        # "Search for a home - Immoscoop" → service "Search for a home", partner "Immoscoop"
        service, _, partner = name.rpartition(" - ") if " - " in name else (name, "", "")
        item_id = slug(name)
        while item_id in seen:
            item_id += "-2"
        seen.add(item_id)
        items.append({"id": item_id, "ecosystem": ecosystem, "name": name, "service": service.strip(),
                      "partner": partner.strip() or None})
    OUT.write_text(json.dumps(items, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(items)} items, {len({i['ecosystem'] for i in items})} ecosystems -> {OUT}")


if __name__ == "__main__":
    main()

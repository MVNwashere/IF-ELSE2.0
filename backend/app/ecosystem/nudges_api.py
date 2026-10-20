"""Kate nudges (proactive messages). Router mounted in main.py; filled in by the nudges work."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["nudges"])


def init_schema(conn) -> None:
    """Create the nudge tables (called from db.init_schema)."""

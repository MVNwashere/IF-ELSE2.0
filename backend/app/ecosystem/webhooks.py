"""Partner → KBC status callbacks, modelled on KBC's "application status webhooks".

Contract for a partner:
  POST /api/partners/{partner_id}/webhook
  X-KBC-Timestamp: unix seconds          (must be within ±5 minutes)
  X-KBC-Signature: hex HMAC-SHA256(secret_of(partner_id), f"{timestamp}.{raw body}")
  body: PartnerWebhook JSON (event_id, ref, status, result); unknown keys are rejected

The partner id in the path selects the key, so a partner can only ever sign for itself, and a ref only matches a
step routed to that same partner. Events are idempotent on (partner_id, event_id).

The partners in this proof of concept are simulated (`simulate_partner`): they answer through exactly this
verification path, after a short delay, so the demo exercises the real security checks.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from typing import Callable

from .models import PartnerWebhook

MAX_SKEW_S = 300
MAX_BODY_BYTES = 4096
# A dev master key, random per process, unless set in .env. Real partners get their own key per partner
# (PARTNER_WEBHOOK_SECRET_<ID>), exchanged when they are onboarded through the Partner Hub.
_MASTER = (os.environ.get("PARTNER_WEBHOOK_MASTER") or secrets.token_hex(32)).encode()


class WebhookError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def secret_of(partner_id: str) -> bytes:
    explicit = os.environ.get(f"PARTNER_WEBHOOK_SECRET_{partner_id.upper()}")
    if explicit:
        return explicit.encode()
    return hmac.new(_MASTER, partner_id.encode(), hashlib.sha256).digest()


def sign(partner_id: str, timestamp: str, body: bytes) -> str:
    return hmac.new(secret_of(partner_id), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


def verify(partner_id: str, timestamp: str | None, signature: str | None, body: bytes) -> PartnerWebhook:
    if len(body) > MAX_BODY_BYTES:
        raise WebhookError(413, "Body too large")
    if not timestamp or not signature or not timestamp.isdigit():
        raise WebhookError(401, "Missing signature")
    if abs(time.time() - int(timestamp)) > MAX_SKEW_S:
        raise WebhookError(401, "Stale timestamp")
    if not hmac.compare_digest(sign(partner_id, timestamp, body), signature):
        raise WebhookError(401, "Bad signature")
    try:
        return PartnerWebhook.model_validate_json(body)
    except ValueError:
        raise WebhookError(422, "Invalid payload") from None


def signed_request(partner_id: str, payload: dict) -> tuple[bytes, dict[str, str]]:
    """What a partner sends: the body and headers. Used by the simulator and by scripts/partner_webhook.py."""
    body = json.dumps(payload, separators=(",", ":")).encode()
    ts = str(int(time.time()))
    return body, {"X-KBC-Timestamp": ts, "X-KBC-Signature": sign(partner_id, ts, body)}


def simulate_partner(partner_id: str, ref: str, result: str,
                     deliver: Callable[[str, bytes, dict[str, str]], None]) -> None:
    """A mock partner: acknowledges, does the work, then reports back with a signed 'done' webhook."""
    delay = float(os.environ.get("PARTNER_SIM_DELAY", "4"))

    def run() -> None:
        body, headers = signed_request(partner_id, {"event_id": f"{ref}.done", "ref": ref, "status": "done",
                                                    "result": result[:300]})
        deliver(partner_id, body, headers)

    if delay <= 0:
        run()
    else:
        timer = threading.Timer(delay, run)
        timer.daemon = True
        timer.start()


def simulate_deletion(partner_id: str, ref: str, deliver: Callable[[str, bytes, dict[str, str]], None]) -> None:
    """After a revoke or expiry, the mock partner erases the data and confirms with a signed 'deleted' webhook."""
    delay = float(os.environ.get("PARTNER_SIM_DELAY", "4"))

    def run() -> None:
        body, headers = signed_request(partner_id, {"event_id": f"{ref}.deleted", "ref": ref, "status": "deleted",
                                                    "result": "Customer data deleted after the consent ended"})
        try:
            deliver(partner_id, body, headers)
        except Exception:  # noqa: BLE001 - a simulated partner must never crash the server thread
            pass

    if delay <= 0:
        run()
    else:
        timer = threading.Timer(delay * 0.75, run)
        timer.daemon = True
        timer.start()

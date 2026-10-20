"""Play a partner: send a signed status webhook to the running app over HTTP.

The server and this script must share the key: set PARTNER_WEBHOOK_MASTER (or PARTNER_WEBHOOK_SECRET_<ID>) in .env
for both. Find a step's ref in the journey sheet or in GET /api/me/goals.

  py -3.12 -m scripts.partner_webhook --partner setle --ref setle-1a2b3c4d5e6f --status done --result "Report ready"
"""
from __future__ import annotations

import argparse
import secrets
import urllib.request

from app.ecosystem.webhooks import signed_request


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--partner", required=True)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--status", choices=["in_progress", "done", "failed"], default="done")
    ap.add_argument("--result", default="")
    ap.add_argument("--url", default="http://localhost:8000")
    args = ap.parse_args()

    body, headers = signed_request(args.partner, {"event_id": f"{args.ref}.{secrets.token_hex(4)}", "ref": args.ref,
                                                  "status": args.status, "result": args.result})
    if not args.url.startswith(("http://localhost", "http://127.0.0.1", "https://")):
        raise SystemExit("Use https, or http only for localhost")
    req = urllib.request.Request(f"{args.url}/api/partners/{args.partner}/webhook", data=body, method="POST",
                                 headers={**headers, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 - scheme checked above
        print(resp.status, resp.read().decode())


if __name__ == "__main__":
    main()

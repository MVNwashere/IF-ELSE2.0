"""Source adapter and canonical event classification. Raw records remain intact."""
from __future__ import annotations

import datetime as dt
import unicodedata

from .. import db
from ..schemas import INCOME_CATEGORIES
from .models import AccountObservation, Observations, RawTransaction, Signal, TransactionDetails

SENSITIVE_CATEGORIES = {"healthcare", "medical", "religion", "political", "sexual_health", "intimate"}
DISCRETIONARY = {"leisure", "restaurants", "travel", "subscription"}
ESSENTIAL = {"rent", "mortgage", "utilities", "telecom", "groceries", "transport", "insurance_car",
             "insurance_home", "insurance_family", "childcare", "school", "tax", "loan", "credit"}
DEBT = {"mortgage", "loan", "credit"}
BILLS = {"rent", "mortgage", "utilities", "telecom", "insurance_car", "insurance_home", "insurance_family",
         "childcare", "school", "loan", "credit", "subscription", "tuition", "social_contribution", "vat_payment"}


def canonical(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def load(conn, customer_id: int, as_of: dt.date, balance_reference: dt.date) -> Observations:
    customer = db.get_customer(conn, customer_id)
    if customer is None:
        raise LookupError("Customer not found")
    rows = conn.execute(
        "SELECT t.*, d.data AS details FROM transactions t LEFT JOIN customer_state_transaction_details d "
        "ON d.transaction_id=t.id WHERE t.customer_id=? ORDER BY t.date, t.id", (customer_id,),
    ).fetchall()
    all_transactions = [RawTransaction(
        id=r["id"], date=r["date"], amount=r["amount"], category=r["category"], counterparty=r["counterparty"],
        details=TransactionDetails.model_validate_json(r["details"]) if r["details"] else TransactionDetails(),
    ) for r in rows]
    account_rows = conn.execute(
        "SELECT data FROM customer_state_account_observations WHERE customer_id=? ORDER BY observed_at, id",
        (customer_id,),
    ).fetchall()
    all_accounts = [AccountObservation.model_validate_json(r["data"]) for r in account_rows]
    accounts = [a for a in all_accounts if a.observed_at <= as_of]
    limitations = ["LEGACY_TRANSACTIONS_DEFAULT_TO_EUR_AND_CURRENT_ACCOUNT", "NO_FX_CONVERSION",
                   "HISTORY_COVERAGE_ASSUMED_FROM_FIRST_TRANSACTION"]
    # Existing repository defines balance_today as the closing balance of its synthetic ledger.
    # This is an explicit reconstruction, not a historical balance observation.
    if not any(a.kind == "current" for a in all_accounts):
        row = conn.execute("SELECT balance_today FROM accounts WHERE customer_id=?", (customer_id,)).fetchone()
        if row and as_of <= balance_reference:
            after = sum(t.amount for t in all_transactions if as_of < t.date <= balance_reference
                        and t.details.currency == "EUR" and t.details.account_id == "current")
            accounts.append(AccountObservation(
                id=f"legacy-current:{as_of}", account_id="current", kind="current", observed_at=as_of,
                balance=round(row["balance_today"] - after, 2), source="legacy_ledger_reconstruction",
            ))
            limitations.append("CURRENT_BALANCE_RECONSTRUCTED_FROM_LEGACY_LEDGER")
    visit = conn.execute("SELECT last_visit FROM visits WHERE customer_id=?", (customer_id,)).fetchone()
    activity = {}
    if visit and visit["last_visit"][:10] <= as_of.isoformat():
        activity["last_visit"] = visit["last_visit"]
    return Observations(customer_id=customer_id, products=customer.products,
                        transactions=[t for t in all_transactions if t.date <= as_of], accounts=accounts,
                        activity=activity, limitations=limitations)


def normalize(raw: Observations) -> list[Signal]:
    account_kinds = {a.account_id: a.kind for a in raw.accounts}
    result = []
    for t in raw.transactions:
        d = t.details
        source_category = d.canonical_category or t.category
        allowed = not d.sensitive and not ({t.category, source_category, d.subcategory} & SENSITIVE_CATEGORIES)
        category = source_category if allowed else "other"
        if category == "savings_transfer" and account_kinds.get(d.account_id, "current") == "current":
            kind = "savings"
        elif d.internal_transfer or category in {"transfer", "savings_transfer"}:
            kind = "transfer"
        elif t.amount > 0:
            kind = "income" if category in INCOME_CATEGORIES or category == "other_income" else "refund"
        else:
            kind = "expense"
        result.append(Signal(
            id=f"transaction:{t.id}", transaction_id=t.id, account_id=d.account_id, date=t.date,
            amount=t.amount, currency=d.currency, category=category, kind=kind,
            entity=canonical(d.merchant_id or t.counterparty) if allowed else None,
            discretionary=allowed and category in DISCRETIONARY, essential=allowed and category in ESSENTIAL,
            profile_allowed=allowed, country=d.country if allowed else None, source=d.source,
            payment_method=d.payment_method,
        ))
    return result

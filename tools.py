"""Tool implementations and Gemini declarations for the support desk agent."""

import sqlite3
from pathlib import Path
from typing import Any, Optional

from google.genai import types

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "support.db"

CATEGORIES = ("billing", "technical", "account", "feature", "security")
PLANS = ("free", "pro", "enterprise")

REFUND_POLICIES = {
    "free": "Free-plan customers are not charged. Refund requests do not apply unless a duplicate paid charge is confirmed.",
    "pro": "Pro subscriptions may receive a prorated refund for a verified duplicate charge or confirmed service failure; do not promise an amount until billing verifies it.",
    "enterprise": "Enterprise customers may receive a refund or account credit for verified billing errors or confirmed service failures under the contract terms; escalate to billing or account management.",
}

CATEGORY_KEYWORDS = {
    "billing": ("charge", "refund", "invoice", "payment", "credit", "receipt", "billing", "card", "subscription", "vat"),
    "technical": ("crash", "export", "slow", "bug", "error", "sync", "missing", "invalid", "404", "cache", "upload"),
    "account": ("login", "password", "account", "locked", "member", "permission", "sso", "saml", "authentication"),
    "feature": ("add", "dark", "feature", "custom", "schedule", "slack", "notification", "field", "theme"),
    "security": ("security", "permission", "suspended", "private", "locked", "authentication", "locked out", "assertion"),
}


def _connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _trim(value: Any, limit: int = 240) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def get_ticket(ticket_id: int) -> dict:
    """Return the ticket and customer. Its description says one numeric ID and returns a recoverable not-found error."""
    if isinstance(ticket_id, bool) or not isinstance(ticket_id, int) or ticket_id <= 0:
        return {"error": "ticket_id must be a positive integer"}

    try:
        with _connect() as conn:
            row = conn.execute("""
                SELECT t.id, t.customer_id, t.subject, t.body, t.status, t.created_at,
                       c.name AS customer_name, c.email AS customer_email, c.plan AS customer_plan
                FROM tickets t
                JOIN customers c ON c.id = t.customer_id
                WHERE t.id = ?
            """, (ticket_id,)).fetchone()
    except sqlite3.Error as exc:
        return {"error": f"Database error while reading ticket: {exc}"}

    if not row:
        return {"error": f"Ticket {ticket_id} was not found. Ask for or check a valid ticket ID."}

    result = dict(row)
    result["body"] = _trim(result["body"], 500)
    return result


def search_tickets(query: str, category: Optional[str] = None) -> dict:
    """Search resolved-past-ticket text. The description emphasizes past and category is limited to documented enum values."""
    if not isinstance(query, str) or not query.strip():
        return {"error": "query must be a non-empty string"}
    query = query.strip()
    if len(query) > 200:
        return {"error": "query must be 200 characters or fewer"}
    if category is not None:
        if not isinstance(category, str) or category not in CATEGORIES:
            return {"error": f"category must be one of: {', '.join(CATEGORIES)}"}

    terms = [term for term in query.lower().split() if len(term) >= 2]
    if not terms:
        return {"error": "query must contain at least two alphanumeric characters"}

    try:
        with _connect() as conn:
            rows = conn.execute("""
                SELECT h.id, h.customer_id, h.ticket_id, h.summary, h.resolved_at,
                       t.subject, t.body, c.name AS customer_name
                FROM ticket_history h
                LEFT JOIN tickets t ON t.id = h.ticket_id
                LEFT JOIN customers c ON c.id = h.customer_id
                ORDER BY h.resolved_at DESC
            """).fetchall()

        matches = []
        for row in rows:
            searchable = " ".join(filter(None, (
                row["summary"], row["subject"], row["body"], row["customer_name"]
            ))).lower()
            if not all(term in searchable for term in terms):
                continue

            if category:
                category_terms = CATEGORY_KEYWORDS[category]
                if not any(term in searchable for term in category_terms):
                    continue

            matches.append({
                "history_id": row["id"],
                "ticket_id": row["ticket_id"],
                "customer_id": row["customer_id"],
                "subject": _trim(row["subject"] or "Past ticket", 160),
                "summary": _trim(row["summary"], 240),
                "resolved_at": row["resolved_at"],
            })
            if len(matches) == 5:
                break
    except sqlite3.Error as exc:
        return {"error": f"Database error while searching tickets: {exc}"}

    return {"count": len(matches), "results": matches}


def get_customer_history(customer_id: int) -> dict:
    """Return only resolved history for one customer, avoiding live-ticket noise and random details."""
    if isinstance(customer_id, bool) or not isinstance(customer_id, int) or customer_id <= 0:
        return {"error": "customer_id must be a positive integer"}

    try:
        with _connect() as conn:
            customer = conn.execute(
                "SELECT id, name, email, plan FROM customers WHERE id = ?", (customer_id,)
            ).fetchone()
            if not customer:
                return {"error": f"Customer {customer_id} was not found. Ask for or check a valid customer ID."}
            rows = conn.execute("""
                SELECT id, ticket_id, summary, resolved_at
                FROM ticket_history
                WHERE customer_id = ?
                ORDER BY resolved_at DESC
            """, (customer_id,)).fetchall()
    except sqlite3.Error as exc:
        return {"error": f"Database error while reading customer history: {exc}"}

    return {
        "customer": dict(customer),
        "count": len(rows),
        "history": [{
            "id": row["id"],
            "ticket_id": row["ticket_id"],
            "summary": _trim(row["summary"], 240),
            "resolved_at": row["resolved_at"],
        } for row in rows[:20]],
    }


def get_refund_policy(plan: str) -> dict:
    """Look up one fixed plan-tier policy. The enum prevents unsupported plan names and fabricated policies."""
    if not isinstance(plan, str) or plan not in PLANS:
        return {"error": f"plan must be one of: {', '.join(PLANS)}"}
    return {"plan": plan, "policy": REFUND_POLICIES[plan]}


def send_reply(ticket_id: int, message: str) -> dict:
    """Write a customer-facing reply. It validates both fields and is the only tool in this module that changes data."""
    if isinstance(ticket_id, bool) or not isinstance(ticket_id, int) or ticket_id <= 0:
        return {"error": "ticket_id must be a positive integer"}
    if not isinstance(message, str) or not message.strip():
        return {"error": "message must be a non-empty string"}
    message = message.strip()
    if len(message) > 5000:
        return {"error": "message must be 5000 characters or fewer"}

    try:
        with _connect() as conn:
            ticket = conn.execute("SELECT id FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
            if not ticket:
                return {"error": f"Ticket {ticket_id} was not found. The reply was not sent."}
            conn.execute("""
                CREATE TABLE IF NOT EXISTS replies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_id INTEGER NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (ticket_id) REFERENCES tickets(id)
                )
            """)
            conn.execute(
                "INSERT INTO replies (ticket_id, message) VALUES (?, ?)",
                (ticket_id, message),
            )
            conn.commit()
    except sqlite3.Error as exc:
        return {"error": f"Database error while sending reply: {exc}"}

    return {"sent": True, "ticket_id": ticket_id, "message": _trim(message, 500)}


FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="get_ticket",
        description="Get one support ticket and its customer by positive numeric ticket_id. Use this for the complete details of a specific open or resolved ticket.",
        parameters=types.Schema(type="OBJECT", properties={
            "ticket_id": types.Schema(type="INTEGER", description="Positive numeric ticket ID"),
        }, required=["ticket_id"]),
    ),
    types.FunctionDeclaration(
        name="search_tickets",
        description="Search past resolved-ticket history by keywords and optional fixed category. Use this to find prior solutions; results are limited and summaries are short.",
        parameters=types.Schema(type="OBJECT", properties={
            "query": types.Schema(type="STRING", description="Keywords to search in past ticket summaries and subjects"),
            "category": types.Schema(type="STRING", enum=list(CATEGORIES), description="Optional fixed support category"),
        }, required=["query"]),
    ),
    types.FunctionDeclaration(
        name="get_customer_history",
        description="Get resolved-ticket history for one customer by positive numeric customer_id. Use this to understand prior outcomes before replying.",
        parameters=types.Schema(type="OBJECT", properties={
            "customer_id": types.Schema(type="INTEGER", description="Positive numeric customer ID"),
        }, required=["customer_id"]),
    ),
    types.FunctionDeclaration(
        name="get_refund_policy",
        description="Read the refund policy for exactly one plan tier. Use this before discussing refunds; do not infer policy for another plan.",
        parameters=types.Schema(type="OBJECT", properties={
            "plan": types.Schema(type="STRING", enum=list(PLANS), description="Customer plan tier"),
        }, required=["plan"]),
    ),
    types.FunctionDeclaration(
        name="send_reply",
        description="Write a customer-facing reply to an existing ticket. This is the only action that changes support data; verify ticket_id and the final message before calling it.",
        parameters=types.Schema(type="OBJECT", properties={
            "ticket_id": types.Schema(type="INTEGER", description="Positive numeric ID of the existing ticket"),
            "message": types.Schema(type="STRING", description="Final customer-facing reply, from 1 to 5000 characters"),
        }, required=["ticket_id", "message"]),
    ),
]

TOOL_REGISTRY = {
    "get_ticket": get_ticket,
    "search_tickets": search_tickets,
    "get_customer_history": get_customer_history,
    "get_refund_policy": get_refund_policy,
    "send_reply": send_reply,
}

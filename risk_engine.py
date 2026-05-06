"""
Two-layer risk detection.
Layer 1: rule engine (always runs, fast).
Layer 2: AI risk_level field in ClientStatus (runs on query via Instructor — in ai_engine.py).
"""
from datetime import date, datetime

_RISK_KEYWORDS = {
    "overdue", "expired", "urgent", "missed deadline",
    "rfe", "denial", "no response", "rejected",
}


def content_has_risk_keyword(content: str) -> bool:
    low = content.lower()
    return any(kw in low for kw in _RISK_KEYWORDS)


def rule_based_risk(client: dict) -> str:
    """Returns 'safe', 'watch', or 'at_risk'. Pure function — no DB writes."""
    if client.get("risk_flag"):
        return "at_risk"

    deadline_str = client.get("deadline")
    last_updated_str = client.get("last_updated")

    if not deadline_str:
        return "safe"

    try:
        deadline = date.fromisoformat(deadline_str[:10])
        today = date.today()
        days_to_deadline = (deadline - today).days

        days_since_activity = 999
        if last_updated_str:
            last_updated = datetime.fromisoformat(last_updated_str).date()
            days_since_activity = (today - last_updated).days

        if days_to_deadline <= 0:
            return "at_risk"
        if days_to_deadline <= 14 and days_since_activity >= 7:
            return "at_risk"
        if days_to_deadline <= 14:
            return "watch"
        if days_to_deadline <= 30 and days_since_activity >= 14:
            return "watch"
    except (ValueError, TypeError):
        pass

    return "safe"


def scan_all_clients_risk() -> list:
    """Daily scheduler job: scan all clients, flag newly at-risk ones."""
    from database import get_all_clients, update_client
    clients = get_all_clients()
    newly_flagged = []
    for client in clients:
        level = rule_based_risk(client)
        if level == "at_risk" and not client.get("risk_flag"):
            update_client(client["id"], risk_flag=True)
            newly_flagged.append(client["id"])
    return newly_flagged


def flag_if_keyword(client_id: int, content: str) -> bool:
    """Called on every feed action. Flags client if risk keyword found."""
    if content_has_risk_keyword(content):
        from database import update_client
        update_client(client_id, risk_flag=True)
        return True
    return False

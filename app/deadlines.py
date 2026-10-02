"""Deadline classification: never silently assign a timezone to an unknown one."""
from datetime import datetime, timezone

INACTIVE_STATUSES = {"No-Bid", "Submitted", "Won", "Lost", "Skipped"}


def deadline_info(value, now=None):
    now = now or datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return {"kind": "unknown", "label": "No usable deadline", "sort": "9999", "days": None}
    days = (parsed.date() - now.date()).days
    # A timezone-free deadline can only be compared by calendar day.
    overdue = parsed < now if parsed.tzinfo else days < 0
    if overdue:
        kind, label = "overdue", "Deadline passed"
    elif days == 0:
        kind, label = "soon", "Due today"
    elif days <= 7:
        kind, label = "soon", f"Due in {days} days"
    else:
        kind, label = "later", f"Due in {days} days"
    if parsed.tzinfo is None:
        label += " · timezone unspecified"
    return {"kind": kind, "label": label, "sort": parsed.isoformat(), "days": days}

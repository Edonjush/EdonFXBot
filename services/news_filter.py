"""UTC session-risk blackout. No external economic-calendar feed is present."""
from datetime import datetime, timezone


def session_risk_window(now=None):
    """Block selected UTC session transition hours; this is not news detection."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return now.astimezone(timezone.utc).hour in {6, 7, 12, 13, 14}


def high_impact_news():
    """Compatibility placeholder: no live news provider is configured."""
    return False

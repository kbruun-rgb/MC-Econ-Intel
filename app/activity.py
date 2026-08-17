"""Query helpers behind the admin-only /activity page -- who's logging in,
how often, and what they're actually looking at. Built from ActivityEvent
rows logged by auth.py (logins) and the record_page_view hook in
app/__init__.py (page views).
"""
from datetime import datetime

from sqlalchemy import func

from app import db
from app.models import ActivityEvent, User


def build_user_summary():
    """One row per account, most recently active first. Per-user queries
    rather than one aggregate join -- simpler to read, and the account
    count here is small enough (a handful of client logins) that it
    doesn't matter.
    """
    rows = []
    for user in User.query.order_by(User.name).all():
        logins = ActivityEvent.query.filter_by(user_id=user.id, event_type="login")
        views = ActivityEvent.query.filter_by(user_id=user.id, event_type="view")
        last_login = logins.order_by(ActivityEvent.created_at.desc()).first()
        last_view = views.order_by(ActivityEvent.created_at.desc()).first()
        last_active = max(
            [e.created_at for e in (last_login, last_view) if e],
            default=None,
        )
        rows.append(
            {
                "name": user.name,
                "email": user.email,
                "login_count": logins.count(),
                "view_count": views.count(),
                "last_login": last_login.created_at if last_login else None,
                "last_active": last_active,
            }
        )
    rows.sort(key=lambda r: r["last_active"] or datetime.min, reverse=True)
    return rows


def build_top_content(limit=20):
    """Most-viewed pages across all accounts, by exact path (not just
    endpoint) so e.g. two different dashboards under the same route
    pattern show up as separate rows.
    """
    results = (
        db.session.query(ActivityEvent.path, func.count(ActivityEvent.id).label("views"))
        .filter(ActivityEvent.event_type == "view")
        .group_by(ActivityEvent.path)
        .order_by(func.count(ActivityEvent.id).desc())
        .limit(limit)
        .all()
    )
    return [{"path": path, "views": views} for path, views in results]

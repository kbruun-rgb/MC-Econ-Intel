"""Query helpers behind the admin-only /admin/api-usage page -- who holds a
public econ-data MCP API key and exactly what they've done with it. Built
from User's api_token_* fields (already tracked, see app/models.py) plus
ApiQueryLog rows written by the separate MCP service on every tool call.
Mirrors app/activity.py's style: plain per-purpose query functions, no ORM
abstraction layer.
"""
from datetime import datetime, timezone

from app.models import ApiQueryLog, OAuthToken, User


def build_token_holders():
    """One row per account that has ever generated a key, most recently
    used first. Accounts that never generated one are omitted entirely --
    this page is about existing keys, not every user.
    """
    rows = []
    for user in User.query.filter(User.api_token_created_at.isnot(None)).order_by(User.name).all():
        rows.append(
            {
                "user_id": user.id,
                "name": user.name,
                "email": user.email,
                "active": bool(user.api_token and user.api_token_is_valid()),
                "created_at": user.api_token_created_at,
                "expires_at": user.api_token_expires_at,
                "last_used_at": user.api_token_last_used_at,
                "use_count": user.api_token_use_count or 0,
                "last_ip": user.api_token_last_ip,
            }
        )
    rows.sort(key=lambda r: r["last_used_at"] or r["created_at"], reverse=True)
    return rows


def build_oauth_connections():
    """One row per OAuth token ever issued (Claude Desktop/claude.ai, via
    the /oauth/* flow in app/oauth_server.py) -- the OAuth-side equivalent
    of build_token_holders() above for the manual-key path. Most recent
    first; never includes the token strings themselves (see OAuthToken's
    surrogate int id in app/models.py), only enough to identify and revoke
    a connection.
    """
    rows = []
    for t in OAuthToken.query.order_by(OAuthToken.created_at.desc()).all():
        expires_at = t.refresh_token_expires_at
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        active = not t.revoked and expires_at is not None and datetime.now(timezone.utc) < expires_at
        rows.append(
            {
                "id": t.id,
                "name": t.user.name if t.user else "(deleted user)",
                "email": t.user.email if t.user else "—",
                "client_name": t.client.client_name if t.client else "(unknown client)",
                "active": active,
                "created_at": t.created_at,
                "access_token_expires_at": t.access_token_expires_at,
                "refresh_token_expires_at": t.refresh_token_expires_at,
            }
        )
    return rows


def build_recent_queries(limit=200):
    """Raw who-queried-what feed, most recent first."""
    events = (
        ApiQueryLog.query.order_by(ApiQueryLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "name": e.user.name if e.user else "(deleted user)",
            "email": e.user.email if e.user else "—",
            "tool_name": e.tool_name,
            "dataset": e.dataset,
            "query_text": e.query_text,
            "created_at": e.created_at,
            "ip_address": e.ip_address,
        }
        for e in events
    ]

import secrets
from datetime import datetime, timedelta, timezone

from flask_login import UserMixin

from app import db

# How long a freshly (re)generated API token stays valid before it silently
# stops working -- the automatic backstop against a leak nobody notices.
# Manual regeneration (see routes) is the immediate-response path for when a
# leak *is* suspected.
API_TOKEN_LIFETIME = timedelta(days=90)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    # Lets a plain URL-fetch AI tool (no login session, no cookies) read
    # gated content on this client's behalf -- see app/__init__.py's
    # enforce_login hook. Read-only, scoped to content routes only; never
    # accepted on /connect or account-management routes, so a leaked token
    # alone can't be used to view or regenerate itself.
    api_token = db.Column(db.String(64), unique=True, nullable=True)
    api_token_created_at = db.Column(db.DateTime, nullable=True)
    api_token_expires_at = db.Column(db.DateTime, nullable=True)

    # Lightweight usage visibility -- a snapshot, not a full request log.
    # TODO: if this feature sees real client usage, consider a proper
    # per-request log table (timestamp, route, IP/user-agent) instead of
    # just a rolling last-seen snapshot, for real incident investigation.
    api_token_last_used_at = db.Column(db.DateTime, nullable=True)
    api_token_use_count = db.Column(db.Integer, nullable=False, default=0)
    api_token_last_ip = db.Column(db.String(64), nullable=True)

    def generate_api_token(self):
        self.api_token = secrets.token_urlsafe(32)
        self.api_token_created_at = datetime.now(timezone.utc)
        self.api_token_expires_at = self.api_token_created_at + API_TOKEN_LIFETIME
        self.api_token_last_used_at = None
        self.api_token_use_count = 0
        self.api_token_last_ip = None
        return self.api_token

    def api_token_is_valid(self):
        if not self.api_token or not self.api_token_expires_at:
            return False
        expires_at = self.api_token_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) < expires_at

    def record_api_token_use(self, ip_address):
        self.api_token_last_used_at = datetime.now(timezone.utc)
        self.api_token_use_count = (self.api_token_use_count or 0) + 1
        self.api_token_last_ip = ip_address


class ActivityEvent(db.Model):
    """One row per login or page view -- the raw log behind the /activity
    admin page. A brand-new table rather than columns added to User, so
    shipping this needs no migration: db.create_all() creates missing
    tables on every startup but never alters existing ones (see
    create_app()), and a new table is exactly the case it does handle.
    """

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    event_type = db.Column(db.String(20), nullable=False)  # "login" or "view"
    endpoint = db.Column(db.String(120))
    path = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    user = db.relationship("User")

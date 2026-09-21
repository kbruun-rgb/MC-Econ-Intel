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


class NarrativeSnippet(db.Model):
    """A short chart-plus-narrative content block for a topic hub or the home
    page. Agent-drafted rows start as status="draft" and never appear on the
    site until an admin approves them (or writes one directly, which
    publishes immediately since the act of writing it *is* the review). Only
    the most recently-published "approved" row per topic_slug is ever live --
    approving a new one archives whatever it replaces.
    """

    id = db.Column(db.Integer, primary_key=True)
    topic_slug = db.Column(db.String(64), nullable=False)  # a TOPIC_HUBS slug, or "home"
    headline = db.Column(db.Text, nullable=False)
    body = db.Column(db.Text, nullable=False)  # two paragraphs, blank-line separated
    chart_image = db.Column(db.LargeBinary, nullable=True)
    chart_mimetype = db.Column(db.String(32), nullable=True)
    chart_caption = db.Column(db.String(255), nullable=True)
    source_note = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="draft")  # draft | approved | rejected | archived
    author = db.Column(db.String(255), nullable=False)  # "agent" or the approving admin's email
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    published_at = db.Column(db.DateTime, nullable=True)

    # Freeform "why" left at approve/reject time -- e.g. "wrong framing,
    # this measures actual unemployment not concern" or "chart too busy."
    # The narrative-draft skill reads recent notes for a topic before
    # drafting again, so this is the mechanism for a human correction to
    # actually change future agent-generated output, not just this one row.
    review_note = db.Column(db.Text, nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)

    # Set when an admin clicks "Try again" on a rejected draft. The website
    # itself can't launch a Claude Code session, so this just flags the row
    # -- a frequent scheduled task (narrative-retry-check) polls for this and
    # actually regenerates it, informed by review_note. Cleared once that
    # run inserts the new draft.
    retry_requested_at = db.Column(db.DateTime, nullable=True)

    # Optional explicit "see the underlying data" link, independent of the
    # in-text NARRATIVE_GLOSSARY auto-linking -- for placements (like the
    # home page) that don't already show dashboard tiles alongside the
    # narrative. Must match a real (geography, theme_slug) pair from
    # scan_econ_library() (see app/library_scan.py).
    related_geography = db.Column(db.String(32), nullable=True)
    related_theme_slug = db.Column(db.String(64), nullable=True)


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

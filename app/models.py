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

    # A short slug identifying the specific series/cut this draft is built
    # on (e.g. "unemployment_index_topline", "pay_loss_rate_by_income") --
    # set by the narrative-draft skill, read back via get_recent_angles() so
    # a future run can avoid repeating the same angle when fresh data
    # supports a different one, or recognize it's fine to recycle when the
    # underlying series (e.g. a monthly print) hasn't actually updated.
    angle = db.Column(db.String(255), nullable=True)


class ApiQueryLog(db.Model):
    """One row per tool call against the public econ-data MCP server. Written
    by that separate service (same DATABASE_URL, no shared code) on every
    request, so Kayla can see everything anyone does with a self-serve key --
    her explicit requirement, not just a usage count. A new table, so
    db.create_all() picks it up with no migration, same reasoning as
    ActivityEvent above.
    """

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    tool_name = db.Column(db.String(64), nullable=False)
    dataset = db.Column(db.String(128), nullable=True)
    query_text = db.Column(db.Text, nullable=True)  # truncated SQL, if the tool took one
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    ip_address = db.Column(db.String(64), nullable=True)

    user = db.relationship("User")


class OAuthClient(db.Model):
    """A client registered via Dynamic Client Registration (RFC 7591) --
    e.g. Claude Desktop, registered the first time someone there clicks "Add
    custom connector" and points it at the public econ-data MCP server.
    Distinct from User.api_token (a single static key per *user*, for
    Claude Code): this is a registry of *client apps*, since OAuth allows
    many users to each separately authorize the same client, and a client's
    registration is independent of any one user's tokens.
    """

    # Explicit, not Flask-SQLAlchemy's default CamelCase->snake_case name
    # (which would turn "OAuthClient" into "o_auth_client") -- the separate
    # MCP service queries this table with raw SQL (no shared ORM code), so
    # the name needs to be unambiguous and typed out once here.
    __tablename__ = "oauth_client"

    client_id = db.Column(db.String(64), primary_key=True)
    # Null for a public/native client (token_endpoint_auth_method="none",
    # e.g. Desktop) -- it can't keep a secret, so it authenticates via PKCE
    # alone. Only set for a confidential client, which this app doesn't
    # expect to see in practice yet but supports per spec.
    client_secret = db.Column(db.String(128), nullable=True)
    client_name = db.Column(db.String(255), nullable=True)
    redirect_uris = db.Column(db.Text, nullable=False)  # JSON-encoded list
    token_endpoint_auth_method = db.Column(db.String(32), nullable=False, default="none")
    created_at = db.Column(db.DateTime, server_default=db.func.now())


class OAuthAuthorizationCode(db.Model):
    """A short-lived, single-use code issued after a user clicks Allow on
    the consent screen, exchanged at /oauth/token for the actual access
    token. Bound to one user_id, one client_id, and the exact redirect_uri +
    PKCE challenge presented at /authorize -- all re-checked at exchange
    time so a code can't be replayed or redirected elsewhere.
    """

    __tablename__ = "oauth_authorization_code"

    code = db.Column(db.String(128), primary_key=True)
    client_id = db.Column(db.String(64), db.ForeignKey("oauth_client.client_id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    redirect_uri = db.Column(db.String(512), nullable=False)
    code_challenge = db.Column(db.String(128), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    client = db.relationship("OAuthClient")
    user = db.relationship("User")


class OAuthToken(db.Model):
    """An access/refresh token pair issued from a redeemed authorization
    code, or from a prior refresh (rotation replaces the row's tokens
    in place -- old values stop working the moment new ones are issued).
    Separate from User.api_token because OAuth allows multiple issued
    tokens per user (one per connected client), where the manual key is
    deliberately a single value per user.
    """

    __tablename__ = "oauth_token"

    # A surrogate int id, not the token string, is the primary key -- so an
    # admin "revoke" link/form can reference a row (e.g. /admin/..../<id>)
    # without ever putting a live bearer credential into a URL or page HTML.
    id = db.Column(db.Integer, primary_key=True)
    access_token = db.Column(db.String(128), unique=True, nullable=False)
    refresh_token = db.Column(db.String(128), unique=True, nullable=True)
    client_id = db.Column(db.String(64), db.ForeignKey("oauth_client.client_id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    access_token_expires_at = db.Column(db.DateTime, nullable=False)
    refresh_token_expires_at = db.Column(db.DateTime, nullable=True)
    revoked = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    client = db.relationship("OAuthClient")
    user = db.relationship("User")


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

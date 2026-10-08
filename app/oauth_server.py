"""A minimal, hand-rolled OAuth 2.0 authorization server so Claude Desktop's
"Add custom connector" flow can authorize against the public econ-data MCP
server. That server only validates bearer tokens (TokenVerifier, not a full
OAuthAuthorizationServerProvider) -- it has no concept of registering a
client or issuing a token itself. This blueprint is the piece that does:
RFC 8414 metadata, RFC 7591 Dynamic Client Registration, an /authorize
redirect+consent step (reusing the existing Flask-Login session -- no second
account system), and PKCE-verified /token code exchange + refresh rotation.

Deliberately plain Flask routes, not the `mcp` package's own
create_auth_routes() helper -- that helper only builds Starlette/ASGI
routes, and the issuer has to stay on this (Flask/WSGI) domain, since it's
already baked into the MCP server's advertised protected-resource metadata.

This is additive: the existing User.api_token bearer-token path (Claude
Code, see app/main.py's /connect routes) is untouched and keeps working
side by side with whatever this issues.
"""
import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlparse

from flask import Blueprint, jsonify, redirect, render_template, request
from flask_login import current_user

from app import db
from app.models import OAuthAuthorizationCode, OAuthClient, OAuthToken
from config import SITE_BASE_URL

oauth_bp = Blueprint("oauth", __name__)

AUTH_CODE_LIFETIME = timedelta(minutes=5)
ACCESS_TOKEN_LIFETIME = timedelta(hours=1)
REFRESH_TOKEN_LIFETIME = timedelta(days=90)  # matches API_TOKEN_LIFETIME's convention

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _issuer():
    return SITE_BASE_URL.rstrip("/") + "/"


def _redirect_uri_allowed(client, candidate):
    """Exact match, or a loopback redirect differing only by port (RFC 8252
    7.3) -- native apps like Desktop pick a fresh local port per launch.
    """
    try:
        registered_uris = json.loads(client.redirect_uris)
    except (TypeError, ValueError):
        return False
    for registered in registered_uris:
        if registered == candidate:
            return True
        try:
            r, c = urlparse(registered), urlparse(candidate)
        except ValueError:
            continue
        if r.scheme == c.scheme and r.path == c.path and r.hostname in _LOOPBACK_HOSTS and c.hostname in _LOOPBACK_HOSTS:
            return True
    return False


def _pkce_matches(code_verifier, code_challenge):
    if not code_verifier:
        return False
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return hmac.compare_digest(computed, code_challenge)


def _aware(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@oauth_bp.route("/.well-known/oauth-authorization-server")
def metadata():
    issuer = _issuer()
    return jsonify(
        {
            "issuer": issuer,
            "authorization_endpoint": issuer + "oauth/authorize",
            "token_endpoint": issuer + "oauth/token",
            "registration_endpoint": issuer + "oauth/register",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none", "client_secret_post"],
        }
    )


@oauth_bp.route("/oauth/register", methods=["POST"])
def register():
    data = request.get_json(force=True, silent=True) or {}
    redirect_uris = data.get("redirect_uris")
    if not redirect_uris or not isinstance(redirect_uris, list):
        return jsonify({"error": "invalid_client_metadata", "error_description": "redirect_uris is required"}), 400

    auth_method = data.get("token_endpoint_auth_method", "none")
    client_secret = secrets.token_urlsafe(32) if auth_method != "none" else None
    client = OAuthClient(
        client_id=secrets.token_urlsafe(24),
        client_secret=client_secret,
        client_name=data.get("client_name"),
        redirect_uris=json.dumps(redirect_uris),
        token_endpoint_auth_method=auth_method,
    )
    db.session.add(client)
    db.session.commit()

    response = {
        "client_id": client.client_id,
        "client_id_issued_at": int(time.time()),
        "redirect_uris": redirect_uris,
        "token_endpoint_auth_method": auth_method,
    }
    if client_secret:
        response["client_secret"] = client_secret
    if data.get("client_name"):
        response["client_name"] = data["client_name"]
    return jsonify(response), 201


@oauth_bp.route("/oauth/authorize", methods=["GET", "POST"])
def authorize():
    # Not in EXEMPT_ENDPOINTS, so we own the login redirect ourselves --
    # the blanket before_request hook only forwards request.path (no query
    # string), which would drop client_id/redirect_uri/code_challenge/state.
    if not current_user.is_authenticated:
        return redirect("/login?" + urlencode({"next": request.full_path}))

    if request.method == "GET":
        args = request.args
    else:
        args = request.form

    client_id = args.get("client_id")
    redirect_uri = args.get("redirect_uri")
    client = db.session.get(OAuthClient, client_id) if client_id else None

    # Can't safely redirect the error anywhere if the client or its
    # redirect_uri doesn't check out -- show a plain error page instead of
    # bouncing to an unverified URL.
    if client is None or not redirect_uri or not _redirect_uri_allowed(client, redirect_uri):
        return render_template("oauth_error.html", message="This connection request isn't recognized. Ask the app to try reconnecting."), 400

    state = args.get("state", "")
    code_challenge = args.get("code_challenge", "")
    code_challenge_method = args.get("code_challenge_method", "")
    scope = args.get("scope", "")

    def _deny_redirect(error):
        qs = urlencode({"error": error, **({"state": state} if state else {})})
        return redirect(f"{redirect_uri}?{qs}")

    if args.get("response_type", "code") != "code":
        return _deny_redirect("unsupported_response_type")
    if not code_challenge or code_challenge_method != "S256":
        return _deny_redirect("invalid_request")

    if request.method == "GET":
        return render_template(
            "oauth_consent.html",
            client_name=client.client_name or "This application",
            client_id=client_id,
            redirect_uri=redirect_uri,
            state=state,
            code_challenge=code_challenge,
            scope=scope,
        )

    # POST: the consent decision.
    if request.form.get("decision") != "allow":
        return _deny_redirect("access_denied")

    code = secrets.token_urlsafe(32)
    db.session.add(
        OAuthAuthorizationCode(
            code=code,
            client_id=client.client_id,
            user_id=current_user.id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            expires_at=datetime.now(timezone.utc) + AUTH_CODE_LIFETIME,
        )
    )
    db.session.commit()
    qs = urlencode({"code": code, **({"state": state} if state else {})})
    return redirect(f"{redirect_uri}?{qs}")


def _token_error(error, status=400):
    return jsonify({"error": error}), status


def _issue_token(client_id, user_id):
    access_token = secrets.token_urlsafe(32)
    refresh_token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    token = OAuthToken(
        access_token=access_token,
        refresh_token=refresh_token,
        client_id=client_id,
        user_id=user_id,
        access_token_expires_at=now + ACCESS_TOKEN_LIFETIME,
        refresh_token_expires_at=now + REFRESH_TOKEN_LIFETIME,
    )
    db.session.add(token)
    db.session.commit()
    return jsonify(
        {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": int(ACCESS_TOKEN_LIFETIME.total_seconds()),
            "refresh_token": refresh_token,
        }
    )


def _client_authenticates(client, provided_secret):
    if client.token_endpoint_auth_method == "none":
        return True
    return bool(provided_secret) and bool(client.client_secret) and hmac.compare_digest(provided_secret, client.client_secret)


@oauth_bp.route("/oauth/token", methods=["POST"])
def token():
    grant_type = request.form.get("grant_type")
    client_id = request.form.get("client_id")
    client = db.session.get(OAuthClient, client_id) if client_id else None
    if client is None:
        return _token_error("invalid_client", 401)
    if not _client_authenticates(client, request.form.get("client_secret")):
        return _token_error("invalid_client", 401)

    if grant_type == "authorization_code":
        code_value = request.form.get("code")
        auth_code = db.session.get(OAuthAuthorizationCode, code_value) if code_value else None
        if auth_code is None or auth_code.client_id != client.client_id:
            return _token_error("invalid_grant")
        # Mark used immediately, even if a later check fails below --
        # single-use means single-use, not "single successful use."
        if auth_code.used:
            return _token_error("invalid_grant")
        auth_code.used = True
        db.session.commit()

        if datetime.now(timezone.utc) >= _aware(auth_code.expires_at):
            return _token_error("invalid_grant")
        if request.form.get("redirect_uri") != auth_code.redirect_uri:
            return _token_error("invalid_grant")
        if not _pkce_matches(request.form.get("code_verifier"), auth_code.code_challenge):
            return _token_error("invalid_grant")

        return _issue_token(client.client_id, auth_code.user_id)

    if grant_type == "refresh_token":
        refresh_value = request.form.get("refresh_token")
        old = OAuthToken.query.filter_by(refresh_token=refresh_value).first() if refresh_value else None
        if (
            old is None
            or old.client_id != client.client_id
            or old.revoked
            or old.refresh_token_expires_at is None
            or datetime.now(timezone.utc) >= _aware(old.refresh_token_expires_at)
        ):
            return _token_error("invalid_grant")
        old.revoked = True
        db.session.commit()
        return _issue_token(client.client_id, old.user_id)

    return _token_error("unsupported_grant_type")

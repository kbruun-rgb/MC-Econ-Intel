from flask import Blueprint, Response, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app import db
from app.activity import build_recent_activity, build_top_content, build_user_summary
from app.api_usage import build_recent_queries, build_token_holders
from app.models import User
from app.bible_scan import build_connect_prompt, build_llms_txt
from app.content_health import build_health_rows
from app.narrative import get_live_snippet, related_dashboard_link, render_paragraphs
from app.topics import build_wizard_data
from config import ADMIN_EMAILS, MCP_SERVER_URL, NARRATIVE_ENABLED, TEAM, TOPIC_HUBS

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
@login_required
def home():
    narrative = get_live_snippet("home") if NARRATIVE_ENABLED else None
    return render_template(
        "home.html",
        topic_hubs=TOPIC_HUBS,
        narrative=narrative,
        # Home is a compact teaser -- only the first paragraph, not the full
        # snippet -- so keep the path grid visible without scrolling.
        narrative_paragraphs=render_paragraphs(narrative.body)[:1] if narrative else None,
        narrative_link=related_dashboard_link(narrative) if narrative else None,
    )


@main_bp.route("/about")
@login_required
def about():
    return render_template("about.html", team=TEAM)


@main_bp.route("/guide")
@login_required
def guide():
    # Everything after topic selection happens client-side (see guide.html)
    # -- this assembles the full per-topic dataset once, up front, so later
    # steps (geography, industry coverage, data type) can filter it with no
    # server round trip.
    return render_template("guide.html", topic_hubs=TOPIC_HUBS, wizard_data=build_wizard_data())


@main_bp.route("/health")
@login_required
def health():
    if current_user.email not in ADMIN_EMAILS:
        # 404, not 403 -- a 403 would confirm to a non-admin that this URL
        # is real. This should look identical to a route that never existed.
        abort(404)
    return render_template("health.html", rows=build_health_rows())


@main_bp.route("/activity")
@login_required
def activity():
    if current_user.email not in ADMIN_EMAILS:
        abort(404)
    return render_template(
        "activity.html",
        users=build_user_summary(),
        top_content=build_top_content(),
        recent_activity=build_recent_activity(),
        token_holders=build_token_holders(),
        recent_queries=build_recent_queries(),
    )


@main_bp.route("/admin/revoke-key/<int:user_id>", methods=["POST"])
@login_required
def admin_revoke_key(user_id):
    if current_user.email not in ADMIN_EMAILS:
        abort(404)
    target = db.session.get(User, user_id)
    if target is None:
        abort(404)
    target.api_token = None
    target.api_token_expires_at = None
    db.session.commit()
    flash(f"Revoked API key for {target.name} ({target.email}).")
    return redirect(url_for("main.activity"))


@main_bp.route("/llms.txt")
def llms_txt():
    # Deliberately public (see EXEMPT_ENDPOINTS in create_app) -- this is
    # the llms.txt convention: a plaintext file AI agents check for
    # machine-readable site context, same trust level as robots.txt.
    return Response(build_llms_txt(), mimetype="text/plain")


@main_bp.route("/connect")
@login_required
def connect():
    return render_template("connect.html", mcp_server_url=MCP_SERVER_URL)


# The User.api_token machinery (app/models.py) sat dormant for a while --
# built for a plain URL-fetch AI tool that never shipped (a safety-conscious
# AI correctly refuses to auto-fetch a credentialed URL from an untrusted
# downloaded file) -- but is now the auth mechanism for the public econ-data
# MCP server: generate a key here, use it as a bearer token when connecting
# an MCP client. Same token, same 90-day expiry/use-count tracking; just a
# second consumer now.
#
# Admin-only for now (2026-10-07) -- the MCP server itself isn't deployed
# yet, so the UI is gated to Kayla's own account for her to test against,
# rather than shipping a "generate a key" button to every client with
# nowhere real to use it. Both the UI (connect.html) and these two routes
# are gated, not just the template, so a non-admin can't hit them directly
# either.
@main_bp.route("/connect/regenerate", methods=["POST"])
@login_required
def connect_regenerate():
    if current_user.email not in ADMIN_EMAILS:
        abort(404)
    current_user.generate_api_token()
    db.session.commit()
    flash("Generated a new API key.")
    return redirect(url_for("main.connect"))


@main_bp.route("/connect/revoke", methods=["POST"])
@login_required
def connect_revoke():
    if current_user.email not in ADMIN_EMAILS:
        abort(404)
    current_user.api_token = None
    current_user.api_token_expires_at = None
    db.session.commit()
    flash("API key revoked.")
    return redirect(url_for("main.connect"))


@main_bp.route("/connect/download")
@login_required
def connect_download():
    # Framed for pasting into (or attaching to) a client's own Claude/
    # ChatGPT session. Bakes in recent report content directly rather than
    # linking to it -- see build_connect_prompt's docstring/header for why.
    return Response(
        build_connect_prompt(),
        mimetype="text/plain",
        headers={"Content-Disposition": "attachment; filename=mc-econ-intel-ai-prompt.txt"},
    )

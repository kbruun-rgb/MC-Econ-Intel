from flask import Blueprint, Response, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app import db
from app.bible_scan import build_connect_prompt, build_llms_txt
from app.content_health import build_health_rows
from app.topics import build_wizard_data
from config import ADMIN_EMAILS, TEAM, TOPIC_HUBS

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
@login_required
def home():
    return render_template("home.html", topic_hubs=TOPIC_HUBS)


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


@main_bp.route("/llms.txt")
def llms_txt():
    # Deliberately public (see EXEMPT_ENDPOINTS in create_app) -- this is
    # the llms.txt convention: a plaintext file AI agents check for
    # machine-readable site context, same trust level as robots.txt.
    return Response(build_llms_txt(), mimetype="text/plain")


@main_bp.route("/connect")
@login_required
def connect():
    return render_template("connect.html")


# /connect/regenerate and the User.api_token machinery (app/models.py) are
# intentionally not used by the current downloadable prompt anymore -- a
# safety-conscious AI correctly refuses to auto-fetch a credentialed URL
# from an untrusted downloaded file (tested and confirmed), so the prompt
# now bakes in actual content instead of a link to fetch (see
# build_connect_prompt). Left in place, dormant, in case a future, more
# controlled integration (e.g. a deliberate custom tool a client's developer
# wires up, not a generic chat-and-fetch flow) wants token-based access.
@main_bp.route("/connect/regenerate", methods=["POST"])
@login_required
def connect_regenerate():
    current_user.generate_api_token()
    db.session.commit()
    flash("Generated a new access token.")
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

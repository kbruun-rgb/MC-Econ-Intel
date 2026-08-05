from flask import Blueprint, abort, render_template
from flask_login import login_required

from app.library_scan import find_theme, scan_econ_library
from config import DASHBOARD_LIGHT_MODE_OVERRIDES

dashboards_bp = Blueprint("dashboards", __name__, url_prefix="/dashboards")


@dashboards_bp.route("/")
@login_required
def index():
    library = scan_econ_library()
    return render_template("dashboards_index.html", library=library)


@dashboards_bp.route("/<geography>/<theme_slug>")
@login_required
def detail(geography, theme_slug):
    geography_key = geography.capitalize() if geography.lower() != "us" else "US"
    entry = find_theme(geography_key, theme_slug)
    if entry is None:
        abort(404)
    return render_template(
        "dashboard_detail.html",
        geography=geography_key,
        entry=entry,
        light_mode_overrides=DASHBOARD_LIGHT_MODE_OVERRIDES,
    )

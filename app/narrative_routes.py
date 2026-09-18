from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.narrative import (
    approve_snippet,
    create_manual_snippet,
    get_live_snippet,
    get_pending_drafts,
    get_snippet,
    list_dashboards_for_picker,
    reject_snippet,
    update_draft,
)
from config import ADMIN_EMAILS, NARRATIVE_TOPICS

narrative_bp = Blueprint("narrative", __name__)


def _require_admin():
    if current_user.email not in ADMIN_EMAILS:
        # 404, not 403 -- matches /health and /activity: a non-admin should
        # see nothing that confirms this URL is real.
        abort(404)


def _parse_related_dashboard():
    """The picker's <select> posts a single "geography|theme_slug" value (or
    empty for "None") -- split it back into the two column values.
    """
    raw = request.form.get("related_dashboard", "")
    if "|" not in raw:
        return None, None
    geography, theme_slug = raw.split("|", 1)
    return geography, theme_slug


@narrative_bp.route("/admin/narrative")
@login_required
def queue():
    _require_admin()
    live = {slug: get_live_snippet(slug) for slug in NARRATIVE_TOPICS}
    return render_template(
        "narrative_admin.html",
        drafts=get_pending_drafts(),
        live=live,
        topics=NARRATIVE_TOPICS,
    )


@narrative_bp.route("/admin/narrative/new", methods=["GET", "POST"])
@login_required
def new():
    _require_admin()
    if request.method == "POST":
        related_geography, related_theme_slug = _parse_related_dashboard()
        create_manual_snippet(
            topic_slug=request.form["topic_slug"],
            headline=request.form["headline"].strip(),
            body=request.form["body"].strip(),
            source_note=request.form.get("source_note", "").strip() or None,
            admin_email=current_user.email,
            chart_file=request.files.get("chart"),
            related_geography=related_geography,
            related_theme_slug=related_theme_slug,
        )
        flash("Published.")
        return redirect(url_for("narrative.queue"))
    return render_template(
        "narrative_edit.html", topics=NARRATIVE_TOPICS, snippet=None, dashboard_options=list_dashboards_for_picker()
    )


@narrative_bp.route("/admin/narrative/<int:snippet_id>/edit", methods=["GET", "POST"])
@login_required
def edit(snippet_id):
    _require_admin()
    snippet = get_snippet(snippet_id) or abort(404)
    if request.method == "POST":
        related_geography, related_theme_slug = _parse_related_dashboard()
        update_draft(
            snippet,
            request.form["headline"].strip(),
            request.form["body"].strip(),
            related_geography=related_geography,
            related_theme_slug=related_theme_slug,
        )
        flash("Draft updated.")
        return redirect(url_for("narrative.queue"))
    return render_template(
        "narrative_edit.html", topics=NARRATIVE_TOPICS, snippet=snippet, dashboard_options=list_dashboards_for_picker()
    )


@narrative_bp.route("/admin/narrative/<int:snippet_id>/approve", methods=["POST"])
@login_required
def approve(snippet_id):
    _require_admin()
    snippet = get_snippet(snippet_id) or abort(404)
    approve_snippet(snippet, current_user.email)
    flash("Published.")
    return redirect(url_for("narrative.queue"))


@narrative_bp.route("/admin/narrative/<int:snippet_id>/reject", methods=["POST"])
@login_required
def reject(snippet_id):
    _require_admin()
    snippet = get_snippet(snippet_id) or abort(404)
    reject_snippet(snippet)
    flash("Rejected.")
    return redirect(url_for("narrative.queue"))


@narrative_bp.route("/admin/narrative/<int:snippet_id>/chart.png")
@login_required
def admin_chart(snippet_id):
    _require_admin()
    snippet = get_snippet(snippet_id) or abort(404)
    if not snippet.chart_image:
        abort(404)
    return Response(snippet.chart_image, mimetype=snippet.chart_mimetype or "image/png")


@narrative_bp.route("/narrative/<slug>/chart.png")
@login_required
def chart(slug):
    snippet = get_live_snippet(slug) or abort(404)
    if not snippet.chart_image:
        abort(404)
    return Response(snippet.chart_image, mimetype=snippet.chart_mimetype or "image/png")

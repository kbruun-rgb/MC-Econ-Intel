from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.narrative import (
    approve_snippet,
    create_manual_snippet,
    get_all_live_snippets,
    get_archived_snippets,
    get_live_snippet,
    get_pending_drafts,
    get_recent_feedback,
    get_rejected_snippets,
    get_snippet,
    list_dashboards_for_picker,
    reject_snippet,
    related_dashboard_link,
    render_paragraphs,
    request_retry,
    restore_snippet,
    topic_label,
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


@narrative_bp.route("/insights")
@login_required
def gallery():
    # Admin-only for now (same 404-not-403 pattern as /health, /activity) --
    # this is still demo/preview content while the concept gets worked out,
    # not something to show every client yet. Separately, deliberately not
    # gated by config.NARRATIVE_ENABLED -- that flag is specifically about
    # embedding narrative blocks into home/topic pages, which is paused
    # pending a redesign; this page is independent of that.
    _require_admin()
    cards = [
        {
            "snippet": s,
            "topic_label": topic_label(s.topic_slug),
            "paragraphs": render_paragraphs(s.body),
            "link": related_dashboard_link(s),
        }
        for s in get_all_live_snippets()
    ]
    return render_template("narrative_gallery.html", cards=cards)


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
        topic_label=topic_label,
        get_recent_feedback=get_recent_feedback,
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
    # ?from=<archived snippet id> pre-fills the form from an old entry --
    # the "resurface with an updated chart/text" path from /admin/narrative/archive.
    # The chart itself is deliberately NOT carried over -- the whole point is
    # to attach a fresher one, so leaving the old image in place would be too
    # easy to publish by accident without actually updating it.
    prefill = get_snippet(request.args.get("from", type=int)) if request.args.get("from") else None
    return render_template(
        "narrative_edit.html",
        topics=NARRATIVE_TOPICS,
        snippet=None,
        prefill=prefill,
        dashboard_options=list_dashboards_for_picker(),
        topic_label=topic_label,
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
        "narrative_edit.html",
        topics=NARRATIVE_TOPICS,
        snippet=snippet,
        prefill=None,
        dashboard_options=list_dashboards_for_picker(),
        topic_label=topic_label,
    )


@narrative_bp.route("/admin/narrative/<int:snippet_id>/approve", methods=["POST"])
@login_required
def approve(snippet_id):
    _require_admin()
    snippet = get_snippet(snippet_id) or abort(404)
    approve_snippet(snippet, current_user.email, note=request.form.get("note", "").strip() or None)
    flash("Published.")
    return redirect(url_for("narrative.queue"))


@narrative_bp.route("/admin/narrative/<int:snippet_id>/reject", methods=["POST"])
@login_required
def reject(snippet_id):
    _require_admin()
    snippet = get_snippet(snippet_id) or abort(404)
    reject_snippet(snippet, note=request.form.get("note", "").strip() or None)
    flash("Rejected.")
    return redirect(url_for("narrative.queue"))


@narrative_bp.route("/admin/narrative/archive")
@login_required
def archive():
    _require_admin()
    return render_template(
        "narrative_archive.html",
        snippets=[
            {"snippet": s, "topic_label": topic_label(s.topic_slug)}
            for s in get_archived_snippets()
        ],
        rejected=[
            {"snippet": s, "topic_label": topic_label(s.topic_slug)}
            for s in get_rejected_snippets()
        ],
    )


@narrative_bp.route("/admin/narrative/<int:snippet_id>/retry", methods=["POST"])
@login_required
def retry(snippet_id):
    _require_admin()
    snippet = get_snippet(snippet_id) or abort(404)
    request_retry(snippet)
    flash(
        "Regeneration requested -- the narrative-retry-check task picks this up within about "
        "30 minutes and drops a fresh draft in the queue, informed by your rejection note."
    )
    return redirect(url_for("narrative.archive"))


@narrative_bp.route("/admin/narrative/<int:snippet_id>/restore", methods=["POST"])
@login_required
def restore(snippet_id):
    _require_admin()
    snippet = get_snippet(snippet_id) or abort(404)
    restore_snippet(snippet, current_user.email)
    flash("Restored -- live again, exactly as it was.")
    return redirect(url_for("narrative.archive"))


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

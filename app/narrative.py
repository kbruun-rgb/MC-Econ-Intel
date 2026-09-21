"""Query/action helpers for narrative content -- the short chart-plus-insight
blocks shown on topic pages and the home page (see app/models.py's
NarrativeSnippet). Nothing here decides what a topic's narrative *should*
say -- that's either the narrative-draft skill (agent-authored) or an admin
writing one directly -- this just manages the draft/approve/archive lifecycle.
"""
import re
from datetime import datetime, timezone

from flask import url_for
from markupsafe import Markup, escape

from app import db
from app.library_scan import find_theme, scan_econ_library
from app.models import NarrativeSnippet
from config import NARRATIVE_GLOSSARY, TOPIC_HUBS


def topic_label(topic_slug):
    """Human-readable label for a topic_slug, for the /insights gallery's
    per-card badge. "home" isn't a real TOPIC_HUBS entry (see config.py),
    so it needs its own case.
    """
    if topic_slug == "home":
        return "Home"
    topic = next((t for t in TOPIC_HUBS if t["slug"] == topic_slug), None)
    return topic["label"] if topic else topic_slug


def list_dashboards_for_picker():
    """(geography, theme_slug, label) for every real dashboard, for the
    "related dashboard" dropdown on the narrative admin forms.
    """
    options = []
    for geography, entries in scan_econ_library().items():
        for entry in entries:
            if entry["has_content"]:
                options.append((geography, entry["theme_slug"], f"{geography} – {entry['theme']}"))
    return sorted(options, key=lambda o: o[2])


def related_dashboard_link(snippet):
    """(url, label) for a snippet's optional "related dashboard" pointer, or
    None if it doesn't have one or the dashboard it points to no longer
    exists.
    """
    if not snippet.related_geography or not snippet.related_theme_slug:
        return None
    entry = find_theme(snippet.related_geography, snippet.related_theme_slug)
    if entry is None:
        return None
    url = url_for("dashboards.detail", geography=snippet.related_geography.lower(), theme_slug=snippet.related_theme_slug)
    return url, entry["theme"]


def render_paragraphs(body):
    """Splits a snippet's body into paragraphs, auto-linking the first
    mention anywhere in the body of any config.NARRATIVE_GLOSSARY term to its
    dashboard. Dedupes by destination dashboard, not by literal term -- if a
    snippet says both "CHI" and "Consumer Health Index", only the earlier one
    becomes a link, since they'd otherwise send the reader to the same place
    twice. Two overlapping terms in the same paragraph never both claim the
    same text.
    """
    linked_destinations = set()
    paragraphs = []
    for para in body.split("\n\n"):
        escaped = str(escape(para))
        claims = []  # (start, end, geography, theme_slug)
        for term, case_sensitive, geography, theme_slug in NARRATIVE_GLOSSARY:
            if (geography, theme_slug) in linked_destinations:
                continue
            flags = 0 if case_sensitive else re.IGNORECASE
            match = re.search(r"\b" + re.escape(term) + r"\b", escaped, flags)
            if not match:
                continue
            if any(match.start() < end and start < match.end() for start, end, *_ in claims):
                continue  # overlaps a term this paragraph already claimed
            claims.append((match.start(), match.end(), geography, theme_slug))
            linked_destinations.add((geography, theme_slug))
        for start, end, geography, theme_slug in sorted(claims, reverse=True):
            url = url_for("dashboards.detail", geography=geography.lower(), theme_slug=theme_slug)
            escaped = f'{escaped[:start]}<a href="{url}">{escaped[start:end]}</a>{escaped[end:]}'
        paragraphs.append(Markup(escaped))
    return paragraphs


def get_live_snippet(topic_slug):
    """The current published snippet for a topic, or None."""
    return (
        NarrativeSnippet.query.filter_by(topic_slug=topic_slug, status="approved")
        .order_by(NarrativeSnippet.published_at.desc())
        .first()
    )


def get_all_live_snippets():
    """Every currently-approved snippet across every topic, most recent
    first -- feeds the standalone /insights gallery (see narrative_routes.py)
    where all of them are shown together, independent of whether any
    individual landing page also surfaces them (see config.NARRATIVE_ENABLED).
    """
    return NarrativeSnippet.query.filter_by(status="approved").order_by(NarrativeSnippet.published_at.desc()).all()


def get_pending_drafts():
    return NarrativeSnippet.query.filter_by(status="draft").order_by(NarrativeSnippet.created_at.desc()).all()


def get_rejected_snippets():
    """Every snippet a draft was rejected, most recently reviewed first --
    same purpose as get_archived_snippets but for content that never went
    live. Kept (not deleted) specifically so the review_note explaining
    *why* survives for both a human to see and the next generation run to
    read.
    """
    return NarrativeSnippet.query.filter_by(status="rejected").order_by(NarrativeSnippet.reviewed_at.desc()).all()


def get_archived_snippets():
    """Every snippet that was once live and got replaced -- nothing is ever
    deleted when a new one is approved (see approve_snippet/
    create_manual_snippet), just flipped to status="archived", so this is a
    full history to browse or restore from.
    """
    return NarrativeSnippet.query.filter_by(status="archived").order_by(NarrativeSnippet.published_at.desc()).all()


def restore_snippet(snippet, admin_email):
    """Re-publishes a previously-archived snippet exactly as it was
    (same chart, same text) -- the one-click "resurface as-is" path. To
    resurface it with fresher data instead, use the edit form (pre-filled
    from this snippet via /admin/narrative/new?from=<id>) to swap in an
    updated chart/text before publishing, or ask for the topic's finding to
    be regenerated -- rebuilding a chart from current data isn't something
    a database update alone can do.
    """
    previous = get_live_snippet(snippet.topic_slug)
    if previous and previous.id != snippet.id:
        previous.status = "archived"

    snippet.status = "approved"
    snippet.published_at = datetime.now(timezone.utc)
    db.session.commit()


def get_snippet(snippet_id):
    return db.session.get(NarrativeSnippet, snippet_id)


def update_draft(snippet, headline, body, related_geography=None, related_theme_slug=None):
    snippet.headline = headline
    snippet.body = body
    snippet.related_geography = related_geography or None
    snippet.related_theme_slug = related_theme_slug or None
    db.session.commit()


def approve_snippet(snippet, admin_email, note=None):
    """Publishes a draft, archiving whatever was previously live for the same
    topic so exactly one approved row is ever considered current. `note` is
    optional feedback even on approval (e.g. "good, but trim the second
    paragraph next time") -- see get_recent_feedback.
    """
    previous = get_live_snippet(snippet.topic_slug)
    if previous and previous.id != snippet.id:
        previous.status = "archived"

    snippet.status = "approved"
    snippet.published_at = datetime.now(timezone.utc)
    snippet.reviewed_at = datetime.now(timezone.utc)
    snippet.review_note = note or None
    if snippet.author == "agent":
        # Record who signed off, without erasing that the agent drafted it.
        snippet.author = f"agent (approved by {admin_email})"
    db.session.commit()


def reject_snippet(snippet, note=None):
    snippet.status = "rejected"
    snippet.reviewed_at = datetime.now(timezone.utc)
    snippet.review_note = note or None
    db.session.commit()


def request_retry(snippet):
    """Flags a rejected draft for automatic regeneration -- the website
    can't launch a Claude Code session itself, so this just marks the row;
    the narrative-retry-check scheduled task polls for these and does the
    actual regeneration, informed by this snippet's review_note.
    """
    snippet.retry_requested_at = datetime.now(timezone.utc)
    db.session.commit()


def get_pending_retries():
    return (
        NarrativeSnippet.query.filter(NarrativeSnippet.retry_requested_at.isnot(None))
        .order_by(NarrativeSnippet.retry_requested_at.asc())
        .all()
    )


def clear_retry(snippet):
    snippet.retry_requested_at = None
    db.session.commit()


def get_recent_feedback(topic_slug, limit=5):
    """The last few review notes left for a topic (rejected drafts, or
    approvals with a note attached), most recent first. This is how a
    correction left at review time actually reaches the next generation
    run -- the narrative-draft skill reads this before drafting again
    rather than repeating whatever it did last time.
    """
    return (
        NarrativeSnippet.query.filter(
            NarrativeSnippet.topic_slug == topic_slug,
            NarrativeSnippet.review_note.isnot(None),
            NarrativeSnippet.review_note != "",
        )
        .order_by(NarrativeSnippet.reviewed_at.desc())
        .limit(limit)
        .all()
    )


def create_manual_snippet(
    topic_slug, headline, body, source_note, admin_email, chart_file=None, related_geography=None, related_theme_slug=None
):
    """A human-authored snippet publishes immediately -- Kayla writing it
    directly *is* the review step, so there's no separate approval click.
    """
    snippet = NarrativeSnippet(
        topic_slug=topic_slug,
        headline=headline,
        body=body,
        source_note=source_note,
        status="approved",
        author=admin_email,
        published_at=datetime.now(timezone.utc),
        related_geography=related_geography or None,
        related_theme_slug=related_theme_slug or None,
    )
    if chart_file and chart_file.filename:
        snippet.chart_image = chart_file.read()
        snippet.chart_mimetype = chart_file.mimetype

    previous = get_live_snippet(topic_slug)
    if previous:
        previous.status = "archived"

    db.session.add(snippet)
    db.session.commit()
    return snippet

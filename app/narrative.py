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
from app.models import NarrativeSnippet
from config import NARRATIVE_GLOSSARY


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


def get_pending_drafts():
    return NarrativeSnippet.query.filter_by(status="draft").order_by(NarrativeSnippet.created_at.desc()).all()


def get_snippet(snippet_id):
    return db.session.get(NarrativeSnippet, snippet_id)


def update_draft(snippet, headline, body):
    snippet.headline = headline
    snippet.body = body
    db.session.commit()


def approve_snippet(snippet, admin_email):
    """Publishes a draft, archiving whatever was previously live for the same
    topic so exactly one approved row is ever considered current.
    """
    previous = get_live_snippet(snippet.topic_slug)
    if previous and previous.id != snippet.id:
        previous.status = "archived"

    snippet.status = "approved"
    snippet.published_at = datetime.now(timezone.utc)
    if snippet.author == "agent":
        # Record who signed off, without erasing that the agent drafted it.
        snippet.author = f"agent (approved by {admin_email})"
    db.session.commit()


def reject_snippet(snippet):
    snippet.status = "rejected"
    db.session.commit()


def create_manual_snippet(topic_slug, headline, body, source_note, admin_email, chart_file=None):
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

from flask import Blueprint, abort, render_template
from flask_login import login_required

from app.narrative import get_live_snippet, render_paragraphs
from app.topics import get_topic, topic_content
from config import NARRATIVE_ENABLED

topics_bp = Blueprint("topics", __name__, url_prefix="/topics")


@topics_bp.route("/<slug>")
@login_required
def detail(slug):
    topic = get_topic(slug)
    if topic is None:
        abort(404)
    dashboards, reports = topic_content(topic)
    narrative = get_live_snippet(slug) if NARRATIVE_ENABLED else None
    return render_template(
        "topic_detail.html",
        topic=topic,
        dashboards=dashboards,
        reports=reports,
        narrative=narrative,
        narrative_paragraphs=render_paragraphs(narrative.body) if narrative else None,
    )

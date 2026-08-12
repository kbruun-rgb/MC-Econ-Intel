from flask import Blueprint, abort, render_template
from flask_login import login_required

from app.topics import get_topic, topic_content

topics_bp = Blueprint("topics", __name__, url_prefix="/topics")


@topics_bp.route("/<slug>")
@login_required
def detail(slug):
    topic = get_topic(slug)
    if topic is None:
        abort(404)
    dashboards, reports = topic_content(topic)
    return render_template("topic_detail.html", topic=topic, dashboards=dashboards, reports=reports)

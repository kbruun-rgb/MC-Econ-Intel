"""Matches dashboards and reports into the curated cross-content "topic
hubs" defined in config.TOPIC_HUBS. Nothing here decides *what* belongs in
a hub -- that's the hand-curated mapping in config.py -- this just applies
it against the live content on each request.
"""
from flask import url_for

from app.library_scan import scan_econ_library, scan_industry_reports, scan_reports
from config import TOPIC_HUBS


def get_topic(slug):
    return next((t for t in TOPIC_HUBS if t["slug"] == slug), None)


def topic_content(topic):
    """Returns (dashboards, reports) for a topic dict from TOPIC_HUBS."""
    dashboards = []
    for geography, entries in scan_econ_library().items():
        for entry in entries:
            if entry["theme"] in topic["dashboard_themes"] and entry["has_content"]:
                dashboards.append({**entry, "geography": geography})

    reports, _skipped = scan_reports()
    matched = [r for r in reports if any(t in topic["report_themes"] for t in r["themes"])]

    if topic.get("include_all_industry_reports"):
        matched += scan_industry_reports()
    else:
        matched += [r for r in scan_industry_reports() if any(t in topic["report_themes"] for t in r["themes"])]

    matched.sort(key=lambda r: r["date"], reverse=True)
    return dashboards, matched


def _report_url(report):
    if report["kind"] == "article":
        return url_for("reports.article", folder=report["folder"])
    if report["kind"] == "industry":
        return url_for("industry_reports.detail", slug=report["slug"])
    return url_for("reports.deck_read", folder=report["folder"])


def build_wizard_data():
    """One entry per topic hub, each holding the dashboards/reports matched
    to it in a shape the "Guide me" wizard's client-side JS can filter
    directly -- ids for de-duplicating an item that matches more than one
    selected topic, geography for the geography step (now on both
    dashboards and reports), and an is_industry flag for the
    industry-coverage step.
    """
    data = {}
    for topic in TOPIC_HUBS:
        dashboards, reports = topic_content(topic)
        data[topic["slug"]] = {
            "dashboards": [
                {
                    "id": f"dash:{d['geography']}:{d['theme_slug']}",
                    "label": d["theme"],
                    "description": d.get("description", ""),
                    "geography": d["geography"],
                    "url": url_for("dashboards.detail", geography=d["geography"].lower(), theme_slug=d["theme_slug"]),
                }
                for d in dashboards
            ],
            "reports": [
                {
                    "id": f"report:{r.get('folder', r.get('slug'))}",
                    "label": r["title"],
                    "date": r["date"].strftime("%b %d, %Y"),
                    "sort_date": r["date"].isoformat(),
                    "type": r["type"],
                    "geography": r["geography"],
                    "is_industry": r["kind"] == "industry",
                    "url": _report_url(r),
                }
                for r in reports
            ],
        }
    return data

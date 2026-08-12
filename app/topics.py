"""Matches dashboards and reports into the curated cross-content "topic
hubs" defined in config.TOPIC_HUBS. Nothing here decides *what* belongs in
a hub -- that's the hand-curated mapping in config.py -- this just applies
it against the live content on each request.
"""
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

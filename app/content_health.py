"""Freshness overview for content with an ongoing update cadence
(dashboards, industry reports) -- flags anything that's gone quiet for
longer than STALE_THRESHOLD_DAYS. Analysis & Reports memos are excluded:
each is a one-off dated write-up, not something with an expected refresh
cycle, so "stale" doesn't mean anything for them.

Built directly from the same scanners the public pages use -- no separate
tracking, so this can never drift from what's actually being served.
"""
from datetime import datetime

from app.library_scan import scan_econ_library, scan_industry_reports

STALE_THRESHOLD_DAYS = 45


def build_health_rows():
    rows = []

    for geography, entries in scan_econ_library().items():
        for entry in entries:
            if not entry["dashboards"] or not entry["updated_at"]:
                continue
            rows.append(
                {
                    "label": entry["theme"],
                    "geography": geography,
                    "kind": "Dashboard",
                    "updated_at": entry["updated_at"],
                }
            )

    for report in scan_industry_reports():
        rows.append(
            {
                "label": report["title"],
                "geography": report["geography"],
                "kind": "Industry Report",
                "updated_at": report["updated_at"],
            }
        )

    now = datetime.now()
    for row in rows:
        row["days_ago"] = (now - row["updated_at"]).days
        row["is_stale"] = row["days_ago"] > STALE_THRESHOLD_DAYS

    rows.sort(key=lambda r: r["updated_at"])
    return rows

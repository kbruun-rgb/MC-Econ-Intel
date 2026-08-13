"""Mark (or unmark) an analysis folder for the Analysis & Reports section.

Nothing in the Analyses folder shows up on the site until you explicitly
publish it here -- this is deliberate: it's what keeps bespoke,
brand-specific client work (e.g. a one-off brief written for a single
company) from leaking onto the general site just because it happens to have
a memo/brief file, the way filename-based auto-detection would.

Usage:
    python publish_report.py 2026-06-10-memorial-day-spending
    python publish_report.py 2026-06-03-staples-drs-leading-indicator --title "Office Supply Store Sales Leading Indicator" --theme "Consumer Spending"
    python publish_report.py 2026-08-05-macro-grocery-category-update --theme "Macro Outlook" --theme "Consumer Spending" --theme "Groceries"
    python publish_report.py 2026-08-05-us-economic-update-june-2026 --date 2026-06-01
    python publish_report.py 2026-06-30-tapestry-genz --remove

Repeat --theme to tag a piece with more than one, so it's searchable under
any of them (e.g. a grocery-focused macro update tagged both "Macro
Outlook" and "Groceries"). Passing --theme at all replaces the full list,
not just adds to it.

Re-running on an already-published folder updates only the fields you pass
-- title/theme/date not mentioned in this run keep their existing value,
they don't get cleared.

By default the displayed date is parsed from the folder's YYYY-MM-DD prefix,
which is normally when the analysis was first written. When a folder is
processed well after the fact (e.g. backlog cleanup) and that prefix reflects
the processing date rather than the period the analysis is actually about,
use --date to override what's shown on the site.
"""
import argparse
import json
import os
from datetime import date

from app.library_scan import PUBLISH_FILENAME
from config import ANALYSES_ROOT


def _parse_date(value):
    try:
        year, month, day = (int(part) for part in value.split("-"))
        return date(year, month, day).isoformat()
    except (ValueError, TypeError):
        raise argparse.ArgumentTypeError(f"--date must be YYYY-MM-DD, got {value!r}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", help="Analysis folder name, e.g. 2026-06-10-memorial-day-spending")
    parser.add_argument("--title", help="Override the auto-generated title (default: humanized from the folder slug)")
    parser.add_argument(
        "--theme",
        action="append",
        help="Override the auto-guessed theme (default: keyword-matched, else \"Other\"). "
        "Repeat to tag with more than one theme; passing it at all replaces the full list.",
    )
    parser.add_argument("--date", type=_parse_date, help="Override the displayed date, YYYY-MM-DD (default: parsed from the folder's date prefix)")
    parser.add_argument(
        "--geography",
        choices=["US", "Global"],
        help="Override the auto-guessed geography (default: \"Global\" if the slug says so, else \"US\")",
    )
    parser.add_argument("--remove", action="store_true", help="Un-publish this folder")
    args = parser.parse_args()

    folder_path = os.path.join(ANALYSES_ROOT, args.folder)
    if not os.path.isdir(folder_path):
        raise SystemExit(f"No such analysis folder: {folder_path}")

    marker_path = os.path.join(folder_path, PUBLISH_FILENAME)

    if args.remove:
        if os.path.isfile(marker_path):
            os.remove(marker_path)
            print(f"Removed '{args.folder}' from Analysis & Reports.")
        else:
            print(f"'{args.folder}' wasn't published.")
        return

    # Load existing meta first and update only what's passed -- previously
    # this rebuilt from scratch every run, silently wiping out e.g. an
    # existing title if you only meant to change the theme.
    meta = {}
    if os.path.isfile(marker_path):
        try:
            with open(marker_path, "r", encoding="utf-8") as fh:
                existing = json.load(fh)
                if isinstance(existing, dict):
                    meta = existing
        except (OSError, ValueError):
            pass
    meta.pop("theme", None)  # legacy singular key, superseded by "themes" below

    if args.title:
        meta["title"] = args.title
    if args.theme:
        meta["themes"] = args.theme
    if args.date:
        meta["date"] = args.date
    if args.geography:
        meta["geography"] = args.geography
    with open(marker_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)

    label = f' as "{args.title}"' if args.title else ""
    print(f"Published '{args.folder}'{label}. It'll appear on /reports next refresh.")


if __name__ == "__main__":
    main()

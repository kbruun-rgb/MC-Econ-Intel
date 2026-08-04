"""Mark (or unmark) an analysis folder for the Analysis & Reports section.

Nothing in the Analyses folder shows up on the site until you explicitly
publish it here -- this is deliberate: it's what keeps bespoke,
brand-specific client work (e.g. a one-off brief written for a single
company) from leaking onto the general site just because it happens to have
a memo/brief file, the way filename-based auto-detection would.

Usage:
    python publish_report.py 2026-06-10-memorial-day-spending
    python publish_report.py 2026-06-03-staples-drs-leading-indicator --title "Office Supply Store Sales Leading Indicator" --theme "Consumer Spending"
    python publish_report.py 2026-06-30-tapestry-genz --remove

Re-running on an already-published folder updates its title/theme override.
"""
import argparse
import json
import os

from app.library_scan import PUBLISH_FILENAME
from config import ANALYSES_ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", help="Analysis folder name, e.g. 2026-06-10-memorial-day-spending")
    parser.add_argument("--title", help="Override the auto-generated title (default: humanized from the folder slug)")
    parser.add_argument("--theme", help="Override the auto-guessed theme (default: keyword-matched, else \"Other\")")
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

    meta = {}
    if args.title:
        meta["title"] = args.title
    if args.theme:
        meta["theme"] = args.theme
    with open(marker_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)

    label = f' as "{args.title}"' if args.title else ""
    print(f"Published '{args.folder}'{label}. It'll appear on /reports next refresh.")


if __name__ == "__main__":
    main()

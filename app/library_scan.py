"""Live filesystem scanners for the Econ Data Library and the Analyses
folder. Nothing here copies content -- these functions just describe what
already exists on disk so the app can link to it through the authenticated
file routes in app/files.py.
"""
import json
import os
import re
from datetime import date, datetime

import markdown

from app.office_convert import ensure_pptx_pdf
from config import (
    ANALYSES_ROOT,
    DASHBOARD_FILE_TITLES,
    DASHBOARD_THEME_DESCRIPTIONS,
    DASHBOARD_THEME_DISPLAY_NAMES,
    ECON_LIBRARY_ROOT,
    INDUSTRY_REPORTS_ROOT,
    THEME_KEYWORDS,
)

GUIDE_FILENAME = "interpretation_guide.md"
PUBLISH_FILENAME = "publish.json"
ANALYSIS_FOLDER_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})-(.+)$")
DELIVERABLE_RE = re.compile(r"(memo|brief)", re.IGNORECASE)
INDUSTRY_REPORT_RE = re.compile(r"^Industry Report - (.+)\.pdf$", re.IGNORECASE)

# The generator regenerates every category together in one run each month, so
# a fresh batch's files all land within the same window. A file sitting well
# outside that window is a leftover from a retired/renamed category (seen in
# practice -- standalone "Furniture" and "Home Furnishings" files lingering
# after the category merged into "Furniture & Home Furnishings"), not a
# current one just skipped this cycle. Filtering on that instead of a
# hardcoded category list means a genuine taxonomy change upstream doesn't
# need a matching code change here.
INDUSTRY_REPORT_STALE_TOLERANCE_DAYS = 5


def slugify(text):
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def humanize(slug_or_filename):
    name = os.path.splitext(slug_or_filename)[0]
    name = name.replace("_", " ").replace("-", " ")
    return " ".join(word.capitalize() for word in name.split())


def _guess_theme(text):
    text_l = text.lower()
    for theme, keywords in THEME_KEYWORDS.items():
        for kw in keywords:
            if kw in text_l:
                return theme
    return None


def scan_econ_library(root=ECON_LIBRARY_ROOT):
    """Returns {geography: [theme_entry, ...]}, geography in ("US", "Global", "Other")."""
    library = {"US": [], "Global": [], "Other": []}

    if not os.path.isdir(root):
        return library

    for entry in sorted(os.scandir(root), key=lambda e: e.name):
        if not entry.is_dir():
            continue
        folder_name = entry.name
        if folder_name.startswith("US "):
            geography, theme = "US", folder_name[3:]
        elif folder_name.startswith("Global "):
            geography, theme = "Global", folder_name[7:]
        else:
            geography, theme = "Other", folder_name

        # theme_slug is derived from the raw folder-name theme so existing
        # links/bookmarks keep working even when the display name is
        # overridden below.
        theme_slug = slugify(theme)
        theme = DASHBOARD_THEME_DISPLAY_NAMES.get((geography, theme), theme)

        dashboards = []
        guide_html = None
        updated_at = None
        try:
            for f in sorted(os.scandir(entry.path), key=lambda e: e.name):
                if not f.is_file():
                    continue
                if f.name.lower().endswith(".html"):
                    title = DASHBOARD_FILE_TITLES.get(f.name, humanize(f.name))
                    dashboards.append({"filename": f.name, "title": title})
                    mtime = datetime.fromtimestamp(f.stat().st_mtime)
                    if updated_at is None or mtime > updated_at:
                        updated_at = mtime
                elif f.name == GUIDE_FILENAME:
                    with open(f.path, "r", encoding="utf-8", errors="replace") as fh:
                        guide_html = markdown.markdown(
                            fh.read(), extensions=["tables", "fenced_code"]
                        )
        except OSError:
            continue

        library[geography].append(
            {
                "theme": theme,
                "theme_slug": theme_slug,
                "description": DASHBOARD_THEME_DESCRIPTIONS.get(theme, ""),
                "folder": folder_name,
                "dashboards": dashboards,
                "guide_html": guide_html,
                "has_content": bool(dashboards) or bool(guide_html),
                "updated_at": updated_at,
            }
        )

    return library


def find_theme(geography, theme_slug, root=ECON_LIBRARY_ROOT):
    library = scan_econ_library(root)
    for entry in library.get(geography, []):
        if entry["theme_slug"] == theme_slug:
            return entry
    return None


def _load_publish_meta(folder_path):
    """Returns a dict if publish.json is present (possibly empty), else None.

    Presence of this file is what makes an analysis show up in Analysis &
    Reports at all -- see publish_report.py. This is an explicit opt-in
    rather than "anything with a memo/brief file" so bespoke client-specific
    work never appears on the general site just because it matches a
    filename pattern.
    """
    marker = os.path.join(folder_path, PUBLISH_FILENAME)
    if not os.path.isfile(marker):
        return None
    try:
        with open(marker, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def scan_reports(root=ANALYSES_ROOT):
    """Returns (reports, skipped). skipped maps folder name -> reason.
    Reports sorted most-recent-first.
    """
    reports = []
    skipped = {}

    if not os.path.isdir(root):
        return reports, skipped

    for entry in sorted(os.scandir(root), key=lambda e: e.name, reverse=True):
        if not entry.is_dir():
            continue
        match = ANALYSIS_FOLDER_RE.match(entry.name)
        if not match:
            continue
        year, month, day, slug = match.groups()
        try:
            report_date = date(int(year), int(month), int(day))
        except ValueError:
            continue

        publish_meta = _load_publish_meta(entry.path)
        if publish_meta is None:
            skipped[entry.name] = "not marked for publishing (no publish.json)"
            continue

        try:
            candidates = [
                f
                for f in os.scandir(entry.path)
                if f.is_file()
                and DELIVERABLE_RE.search(f.name)
                and f.name.lower().endswith((".pdf", ".docx", ".pptx"))
            ]
        except OSError:
            candidates = []

        # A written memo (.docx) is rendered inline as an article -- that's
        # the best reading experience, so it wins if one exists. Otherwise
        # this is a slide deck or a standalone PDF, which we link out to
        # rather than trying to reflow as prose.
        docx_files = [f for f in candidates if f.name.lower().endswith(".docx")]
        other_files = [f for f in candidates if not f.name.lower().endswith(".docx")]
        other_files.sort(key=lambda f: 0 if f.name.lower().endswith(".pdf") else 1)

        if docx_files:
            kind, deliverable = "article", docx_files[0].name
        elif other_files:
            best = other_files[0]
            if best.name.lower().endswith(".pptx"):
                # Decks are converted to PDF (once, cached alongside the
                # source) so the download is always a PDF, never a .pptx.
                pdf_path = ensure_pptx_pdf(best.path)
                deliverable = os.path.basename(pdf_path) if pdf_path else best.name
            else:
                deliverable = best.name
            kind = "download"
        else:
            skipped[entry.name] = "no memo/brief deliverable file found"
            continue

        title = publish_meta.get("title") or humanize(slug)
        # "themes" (list) is current; "theme" (string) is the legacy key
        # from before multi-theme tagging -- still honored so existing
        # publish.json files don't need to be re-run.
        themes = publish_meta.get("themes")
        if not themes and publish_meta.get("theme"):
            themes = [publish_meta["theme"]]
        if not themes:
            guessed = _guess_theme(slug)
            themes = [guessed] if guessed else ["Other"]
        if publish_meta.get("date"):
            try:
                report_date = date.fromisoformat(publish_meta["date"])
            except ValueError:
                pass
        reports.append(
            {
                "folder": entry.name,
                "slug": slug,
                "title": title,
                "date": report_date,
                "filename": deliverable,
                "kind": kind,
                "type": "Analysis" if kind == "article" else "Report",
                "themes": themes,
            }
        )

    reports.sort(key=lambda r: r["date"], reverse=True)
    return reports, skipped


def find_report(folder, root=ANALYSES_ROOT):
    reports, _skipped = scan_reports(root)
    for r in reports:
        if r["folder"] == folder:
            return r
    return None


def scan_industry_reports(root=INDUSTRY_REPORTS_ROOT):
    """One entry per category (e.g. "Groceries", "Autos"), overwritten in
    place monthly at the source -- there's no dated folder per edition, just
    the current one. Sorted alphabetically by category.
    """
    if not os.path.isdir(root):
        return []

    candidates = []
    try:
        for f in os.scandir(root):
            if not f.is_file():
                continue
            match = INDUSTRY_REPORT_RE.match(f.name)
            if not match:
                continue
            candidates.append((match.group(1).strip(), f.name, f.stat().st_mtime))
    except OSError:
        return []

    if not candidates:
        return []

    latest_mtime = max(c[2] for c in candidates)
    cutoff = latest_mtime - INDUSTRY_REPORT_STALE_TOLERANCE_DAYS * 86400

    reports = [
        {
            "slug": slugify(category),
            "category": category,
            "title": f"Industry Report: {category}",
            "filename": filename,
            "kind": "industry",
            "type": "Report",
            "themes": [category],
            "updated_at": datetime.fromtimestamp(mtime),
            "date": datetime.fromtimestamp(mtime).date(),
        }
        for category, filename, mtime in candidates
        if mtime >= cutoff
    ]
    reports.sort(key=lambda r: r["category"])
    return reports


def find_industry_report(slug, root=INDUSTRY_REPORTS_ROOT):
    for r in scan_industry_reports(root):
        if r["slug"] == slug:
            return r
    return None

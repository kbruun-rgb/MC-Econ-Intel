import os

from flask import Blueprint, abort, render_template
from flask_login import login_required

from app.docx_render import render_docx_article
from app.library_scan import find_report, scan_industry_reports, scan_reports
from config import ANALYSES_ROOT

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


@reports_bp.route("/")
@login_required
def index():
    reports, skipped = scan_reports()
    if skipped:
        # Server-side note only -- not shown to clients. Lets Kayla see which
        # analyses aren't published yet, and why.
        print(f"[reports] {len(skipped)} folder(s) not shown:", flush=True)
        for folder, reason in skipped.items():
            print(f"  - {folder}: {reason}", flush=True)

    # Industry Reports have their own section (see industry_reports.py) but
    # also show up here so someone searching Analysis & Reports for a
    # category (e.g. "Groceries") finds them without knowing to look
    # elsewhere -- same list, same search/filter, tagged by category.
    reports = reports + scan_industry_reports()
    reports.sort(key=lambda r: r["date"], reverse=True)
    themes = sorted({r["theme"] for r in reports})
    return render_template("reports_index.html", reports=reports, themes=themes)


@reports_bp.route("/<folder>")
@login_required
def article(folder):
    report = find_report(folder)
    if report is None or report["kind"] != "article":
        abort(404)
    path = os.path.join(ANALYSES_ROOT, report["folder"], report["filename"])
    title, body_html = render_docx_article(path)
    return render_template(
        "report_article.html", report=report, title=title, body_html=body_html
    )

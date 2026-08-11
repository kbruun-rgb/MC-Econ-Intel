import os

from flask import Blueprint, abort, render_template, send_file
from flask_login import login_required

from app.library_scan import find_industry_report, scan_industry_reports
from app.pdf_render import pdf_page_count, render_pdf_page
from config import INDUSTRY_REPORTS_ROOT

industry_reports_bp = Blueprint("industry_reports", __name__, url_prefix="/industry-reports")


@industry_reports_bp.route("/")
@login_required
def index():
    reports = scan_industry_reports()
    return render_template("industry_reports_index.html", reports=reports)


@industry_reports_bp.route("/<slug>")
@login_required
def detail(slug):
    report = find_industry_report(slug)
    if report is None:
        abort(404)
    path = os.path.join(INDUSTRY_REPORTS_ROOT, report["filename"])
    try:
        page_count = pdf_page_count(path)
    except Exception:
        page_count = 0
    return render_template("industry_report_detail.html", report=report, page_count=page_count)


@industry_reports_bp.route("/<slug>/page/<int:page_num>.jpg")
@login_required
def page_image(slug, page_num):
    report = find_industry_report(slug)
    if report is None:
        abort(404)
    path = os.path.join(INDUSTRY_REPORTS_ROOT, report["filename"])
    try:
        image_path = render_pdf_page(path, page_num)
    except Exception:
        abort(404)
    return send_file(image_path, mimetype="image/jpeg")

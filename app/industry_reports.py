from flask import Blueprint, abort, render_template
from flask_login import login_required

from app.library_scan import find_industry_report, scan_industry_reports

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
    return render_template("industry_report_detail.html", report=report)

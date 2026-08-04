from flask import Blueprint, abort, send_file
from flask_login import login_required

from app.library_scan import DELIVERABLE_RE
from app.safe_files import resolve_within_root
from config import ANALYSES_ROOT, ECON_LIBRARY_ROOT

files_bp = Blueprint("files", __name__, url_prefix="/files")


@files_bp.route("/dashboards/<path:relpath>")
@login_required
def dashboard_file(relpath):
    if not relpath.lower().endswith(".html"):
        abort(404)
    path = resolve_within_root(ECON_LIBRARY_ROOT, relpath)
    if path is None:
        abort(404)
    return send_file(path, mimetype="text/html")


@files_bp.route("/reports/<path:relpath>")
@login_required
def report_file(relpath):
    filename = relpath.rsplit("/", 1)[-1]
    lower = filename.lower()
    if not lower.endswith((".pdf", ".docx", ".pptx")) or not DELIVERABLE_RE.search(filename):
        abort(404)
    path = resolve_within_root(ANALYSES_ROOT, relpath)
    if path is None:
        abort(404)
    as_attachment = not lower.endswith(".pdf")
    return send_file(path, as_attachment=as_attachment, download_name=filename)

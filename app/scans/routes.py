import csv
import io

from flask import Response, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..errors import AppError, ValidationError
from ..ml import FEATURE_COLUMNS, LABELS
from ..services import scans as svc
from . import bp


@bp.before_request
@login_required
def _require_login():
    """Every page in this blueprint needs a signed-in user."""


def _page_arg() -> int:
    return max(request.args.get("page", 1, type=int) or 1, 1)


@bp.get("/")
def index():
    pagination = svc.list_scans(current_user, page=_page_arg(), per_page=10)
    return render_template("scans/index.html", pagination=pagination,
                           totals=svc.user_totals(current_user))


@bp.route("/upload", methods=["GET", "POST"])
def upload():
    form = {}
    if request.method == "POST":
        form = {"name": request.form.get("name", ""), "notes": request.form.get("notes", "")}
        try:
            scan = svc.create_scan(current_user, request.files.get("file"),
                                   name=form["name"], notes=form["notes"])
        except AppError as err:
            flash(err.message, "error")
            return render_template("scans/upload.html", form=form, error=err), err.status_code
        if scan.status == "failed":
            flash(f"Scan saved, but prediction failed: {scan.error_message}", "warning")
        else:
            flash(f"Scanned {scan.total_rows} connections: {scan.malicious_count} flagged as malicious.",
                  "success")
        return redirect(url_for("scans.detail", scan_id=scan.id))
    return render_template("scans/upload.html", form=form, error=None)


@bp.get("/<int:scan_id>")
def detail(scan_id: int):
    scan = svc.get_scan(current_user, scan_id)
    label = request.args.get("label") or None
    if label not in (None, *LABELS):
        label = None
    results = svc.scan_results(scan, page=_page_arg(), per_page=50, label=label)
    return render_template("scans/detail.html", scan=scan, results=results, label=label,
                           columns=FEATURE_COLUMNS)


@bp.route("/<int:scan_id>/edit", methods=["GET", "POST"])
def edit(scan_id: int):
    scan = svc.get_scan(current_user, scan_id)
    form = {"filename": scan.filename, "notes": scan.notes or ""}
    if request.method == "POST":
        form = {"filename": request.form.get("filename", ""), "notes": request.form.get("notes", "")}
        try:
            svc.update_scan(scan, filename=form["filename"], notes=form["notes"])
        except ValidationError as err:
            flash(err.message, "error")
            return render_template("scans/edit.html", scan=scan, form=form), err.status_code
        flash("Scan updated.", "success")
        return redirect(url_for("scans.detail", scan_id=scan.id))
    return render_template("scans/edit.html", scan=scan, form=form)


@bp.post("/<int:scan_id>/delete")
def delete(scan_id: int):
    scan = svc.get_scan(current_user, scan_id)
    name = scan.filename
    svc.delete_scan(scan)
    flash(f"Deleted scan “{name}”.", "info")
    return redirect(url_for("scans.index"))


@bp.get("/<int:scan_id>/export.csv")
def export(scan_id: int):
    scan = svc.get_scan(current_user, scan_id)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["row", *FEATURE_COLUMNS, "predicted_label", "confidence"])
    for r in scan.results:
        writer.writerow([r.row_index, *(r.features.get(c) for c in FEATURE_COLUMNS),
                         r.label, f"{r.confidence:.4f}"])
    return Response(buf.getvalue(), mimetype="text/csv", headers={
        "Content-Disposition": f'attachment; filename="scan-{scan.id}-results.csv"'})

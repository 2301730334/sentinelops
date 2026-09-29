"""Scan lifecycle: upload -> validate -> predict -> persist; plus read/update/delete."""
from __future__ import annotations

import logging
import time

from flask import current_app
from sqlalchemy import func, select
from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import NotFound
from werkzeug.utils import secure_filename

from ..errors import AppError, ValidationError
from ..extensions import db
from ..metrics import record_scan
from ..ml import LABELS, MALICIOUS, get_predictor
from ..models import Scan, ScanResult, ScanStatus, User
from .csv_parser import check_extension, parse_connections

log = logging.getLogger(__name__)

MAX_NAME_LENGTH = 255
MAX_NOTES_LENGTH = 2000


def _clean_name(name: str | None) -> str | None:
    if name is None:
        return None
    name = name.strip()
    if not name:
        raise ValidationError("Name cannot be empty.", details={"fields": {"filename": "required"}})
    if len(name) > MAX_NAME_LENGTH:
        raise ValidationError(f"Name must be at most {MAX_NAME_LENGTH} characters.",
                              details={"fields": {"filename": "too long"}})
    return name


def _clean_notes(notes: str | None) -> str | None:
    if notes is None:
        return None
    notes = notes.strip()
    if len(notes) > MAX_NOTES_LENGTH:
        raise ValidationError(f"Notes must be at most {MAX_NOTES_LENGTH} characters.",
                              details={"fields": {"notes": "too long"}})
    return notes or None


def create_scan(user: User, upload: FileStorage | None, name: str | None = None,
                notes: str | None = None) -> Scan:
    if upload is None or not upload.filename:
        raise AppError("No file was uploaded. Attach a CSV file in the 'file' field.",
                       details={"fields": {"file": "required"}})
    original = secure_filename(upload.filename) or "upload.csv"
    check_extension(original)
    display_name = _clean_name(name) if name and name.strip() else original
    notes = _clean_notes(notes)

    rows = parse_connections(upload.read(), current_app.config["MAX_CSV_ROWS"])

    scan = Scan(user_id=user.id, filename=display_name, original_filename=original,
                notes=notes, status=ScanStatus.PROCESSING, total_rows=len(rows))
    db.session.add(scan)
    db.session.flush()

    started = time.perf_counter()
    try:
        predictor = get_predictor()
        predictions = predictor.predict(rows)
        scan.model_version = predictor.version
        db.session.add_all([
            ScanResult(scan_id=scan.id, row_index=i, label=p.label,
                       confidence=p.confidence, features=row)
            for i, (row, p) in enumerate(zip(rows, predictions), start=1)
        ])
        scan.malicious_count = sum(1 for p in predictions if p.label == MALICIOUS)
        scan.benign_count = len(predictions) - scan.malicious_count
        scan.status = ScanStatus.COMPLETED
    except Exception as exc:  # keep the scan, mark it failed, surface the reason
        log.exception("scan_prediction_failed", extra={"scan_id": scan.id})
        scan.status = ScanStatus.FAILED
        scan.error_message = getattr(exc, "message", None) or "Prediction failed; see server logs."
    db.session.commit()
    elapsed = time.perf_counter() - started
    record_scan(scan.status, scan.malicious_count, scan.benign_count, elapsed)

    log.info("scan_created", extra={
        "scan_id": scan.id, "user_id": user.id, "rows": scan.total_rows,
        "malicious": scan.malicious_count, "status": scan.status,
        "predict_ms": round(elapsed * 1000, 2),
    })
    return scan


def list_scans(user: User, page: int = 1, per_page: int = 10):
    stmt = select(Scan).where(Scan.user_id == user.id).order_by(Scan.created_at.desc(), Scan.id.desc())
    return db.paginate(stmt, page=page, per_page=per_page, error_out=False)


def user_totals(user: User) -> dict:
    count, rows, malicious = db.session.execute(
        select(func.count(Scan.id), func.coalesce(func.sum(Scan.total_rows), 0),
               func.coalesce(func.sum(Scan.malicious_count), 0)).where(Scan.user_id == user.id)
    ).one()
    return {"scans": count, "rows": rows, "malicious": malicious}


def get_scan(user: User, scan_id: int) -> Scan:
    """Return the user's scan, or 404 (also for other users' scans, to avoid leaking ids)."""
    scan = db.session.get(Scan, scan_id)
    if scan is None or scan.user_id != user.id:
        raise NotFound("Scan not found.")
    return scan


def update_scan(scan: Scan, filename: str | None = None, notes: str | None = None) -> Scan:
    if filename is not None:
        scan.filename = _clean_name(filename)
    if notes is not None:
        scan.notes = _clean_notes(notes)
    db.session.commit()
    log.info("scan_updated", extra={"scan_id": scan.id})
    return scan


def delete_scan(scan: Scan) -> None:
    scan_id = scan.id
    db.session.delete(scan)
    db.session.commit()
    log.info("scan_deleted", extra={"scan_id": scan_id})


def scan_results(scan: Scan, page: int = 1, per_page: int = 50, label: str | None = None):
    stmt = select(ScanResult).where(ScanResult.scan_id == scan.id)
    if label:
        if label not in LABELS:
            raise ValidationError(f"label must be one of {list(LABELS)}")
        stmt = stmt.where(ScanResult.label == label)
    stmt = stmt.order_by(ScanResult.row_index)
    return db.paginate(stmt, page=page, per_page=per_page, error_out=False)

"""Validate and parse uploaded IoT-23-style connection records.

Rules:
* UTF-8 text; delimiter auto-detected among , ; | and tab
* header row must contain every column in FEATURE_COLUMNS (case-insensitive);
  extra columns (ts, uid, id.orig_h, label, ...) are ignored
* numeric fields must be non-negative numbers; Zeek's "-" means 0
* at least one and at most MAX_CSV_ROWS data rows
"""
from __future__ import annotations

import csv
import io
import math
import os

from ..errors import AppError, ValidationError
from ..ml.features import FEATURE_COLUMNS, MISSING_TOKENS, NUMERIC_FEATURES

ALLOWED_EXTENSIONS = {".csv"}
MAX_REPORTED_ERRORS = 10


class UnsupportedFileType(AppError):
    status_code = 415
    error_type = "unsupported_media_type"


def check_extension(filename: str) -> None:
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise UnsupportedFileType("Only .csv files are accepted.",
                                  details={"allowed_extensions": sorted(ALLOWED_EXTENSIONS)})


def _decode(raw: bytes) -> str:
    if not raw or not raw.strip():
        raise ValidationError("The uploaded file is empty.")
    if b"\x00" in raw[:4096]:
        raise ValidationError("The file looks binary. Upload a plain-text CSV file.")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValidationError("The file must be UTF-8 encoded text.") from exc


def _dialect(text: str):
    try:
        return csv.Sniffer().sniff(text[:4096], delimiters=",;|\t")
    except csv.Error:
        return csv.excel


def _parse_number(value: str) -> float:
    value = (value or "").strip()
    if value.lower() in MISSING_TOKENS:
        return 0.0
    number = float(value)  # ValueError handled by caller
    if math.isnan(number) or math.isinf(number) or number < 0:
        raise ValueError("must be a finite, non-negative number")
    return number


def _parse_category(column: str, value: str) -> str:
    value = (value or "").strip()
    if value.lower() in MISSING_TOKENS:
        return "-"
    return value.lower() if column == "proto" else value.upper()


def parse_connections(raw: bytes, max_rows: int) -> list[dict]:
    text = _decode(raw)
    reader = csv.reader(io.StringIO(text), _dialect(text))
    try:
        header = next(reader)
    except StopIteration:  # pragma: no cover - _decode already rejects empty input
        raise ValidationError("The uploaded file is empty.")

    index = {name.strip().lower(): i for i, name in enumerate(header)}
    missing = [c for c in FEATURE_COLUMNS if c not in index]
    if missing:
        raise ValidationError(
            "The CSV is missing required columns: " + ", ".join(missing),
            details={"missing_columns": missing, "required_columns": list(FEATURE_COLUMNS)},
        )

    rows: list[dict] = []
    errors: list[dict] = []
    for line_no, record in enumerate(reader, start=2):
        if not record or all(not cell.strip() for cell in record):
            continue
        if len(rows) >= max_rows:
            raise ValidationError(
                f"The file has more than {max_rows} data rows.",
                details={"max_rows": max_rows},
            )
        row: dict = {}
        for column in FEATURE_COLUMNS:
            pos = index[column]
            value = record[pos] if pos < len(record) else ""
            if column in NUMERIC_FEATURES:
                try:
                    row[column] = _parse_number(value)
                except ValueError:
                    if len(errors) < MAX_REPORTED_ERRORS:
                        errors.append({"line": line_no, "column": column, "value": value[:50],
                                       "error": "must be a non-negative number or '-'"})
                    row = None
                    break
            else:
                row[column] = _parse_category(column, value)
        if row is not None:
            rows.append(row)

    if errors:
        raise ValidationError(
            f"Found invalid values in the CSV (showing up to {MAX_REPORTED_ERRORS}).",
            details={"errors": [f"line {e['line']}, {e['column']}={e['value']!r}: {e['error']}"
                                for e in errors],
                     "row_errors": errors},
        )
    if not rows:
        raise ValidationError("The CSV has a header but no data rows.")
    return rows


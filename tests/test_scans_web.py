import pytest

from app.extensions import db
from app.ml import Prediction, Predictor, set_predictor
from app.models import Scan, ScanResult

from .conftest import BENIGN_ROW, SCAN_ROW, login, make_csv, make_user, upload


def _scan_id():
    return db.session.query(Scan.id).scalar()


def test_scans_require_login(client):
    resp = client.get("/scans/")
    assert resp.status_code == 302
    assert "/auth/login?next=/scans/" in resp.headers["Location"]


def test_empty_list(auth_client):
    resp = auth_client.get("/scans/")
    assert resp.status_code == 200
    assert b"No scans yet" in resp.data


def test_upload_page(auth_client):
    resp = auth_client.get("/scans/upload")
    assert resp.status_code == 200
    assert b"sample_iot23.csv" in resp.data


def test_upload_creates_scan_with_predictions(auth_client):
    resp = upload(auth_client, name="Camera capture", notes="lab run 1")
    assert resp.status_code == 302
    scan = db.session.get(Scan, _scan_id())
    assert scan.filename == "Camera capture"
    assert scan.original_filename == "traffic.csv"
    assert scan.notes == "lab run 1"
    assert scan.status == "completed"
    assert scan.total_rows == 2
    assert scan.malicious_count == 1 and scan.benign_count == 1
    assert scan.model_version == "test-stub"
    results = scan.results.all()
    assert [r.row_index for r in results] == [1, 2]
    assert results[1].label == "malicious"


def test_upload_defaults_name_to_sanitised_filename(auth_client):
    upload(auth_client, filename="../../etc/My Capture.csv")
    assert db.session.get(Scan, _scan_id()).filename == "etc_My_Capture.csv"


def test_detail_page_and_label_filter(auth_client):
    upload(auth_client)
    sid = _scan_id()
    resp = auth_client.get(f"/scans/{sid}")
    assert resp.status_code == 200
    assert b"malicious" in resp.data and b"benign" in resp.data
    filtered = auth_client.get(f"/scans/{sid}?label=malicious").data.decode()
    assert filtered.count('text-bg-danger">malicious') == 1
    assert 'text-bg-success">benign' not in filtered
    # invalid filter falls back to all rows
    assert auth_client.get(f"/scans/{sid}?label=weird").status_code == 200


def test_list_shows_scans_and_totals(auth_client):
    upload(auth_client, name="first")
    upload(auth_client, name="second")
    body = auth_client.get("/scans/").data
    assert b"first" in body and b"second" in body


def test_pagination(auth_client):
    for i in range(12):
        upload(auth_client, name=f"scan-{i:02d}")
    page2 = auth_client.get("/scans/?page=2").data
    assert b"scan-00" in page2 and b"scan-11" not in page2


@pytest.mark.parametrize("data, filename, status, message", [
    (make_csv(), "traffic.txt", 415, b"Only .csv"),
    (b"a,b\n1,2\n", "t.csv", 422, b"missing required columns"),
    (make_csv(rows=["x,1,1,1,1,tcp,SF"]), "t.csv", 422, b"line 2"),
    (b"", "t.csv", 422, b"empty"),
])
def test_upload_validation_errors(auth_client, data, filename, status, message):
    resp = upload(auth_client, data=data, filename=filename)
    assert resp.status_code == status
    assert message in resp.data
    assert db.session.query(Scan).count() == 0


def test_upload_without_file(auth_client):
    resp = auth_client.post("/scans/upload", data={}, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert b"No file was uploaded" in resp.data


def test_upload_too_large_shows_friendly_page(auth_client, app):
    app.config["MAX_CONTENT_LENGTH"] = 1024
    resp = upload(auth_client, data=make_csv(rows=[BENIGN_ROW] * 200))
    assert resp.status_code == 413
    assert b"File too large" in resp.data


def test_prediction_failure_marks_scan_failed(auth_client, app):
    class Broken(Predictor):
        version = "broken"

        def predict(self, rows):
            raise RuntimeError("boom")

    set_predictor(app, Broken())
    resp = upload(auth_client)
    assert resp.status_code == 302
    scan = db.session.get(Scan, _scan_id())
    assert scan.status == "failed"
    assert scan.error_message
    assert b"prediction failed" in auth_client.get(resp.headers["Location"], follow_redirects=True).data


def test_edit_scan(auth_client):
    upload(auth_client)
    sid = _scan_id()
    assert auth_client.get(f"/scans/{sid}/edit").status_code == 200
    resp = auth_client.post(f"/scans/{sid}/edit", data={"filename": "Renamed", "notes": "checked"})
    assert resp.status_code == 302
    scan = db.session.get(Scan, sid)
    assert (scan.filename, scan.notes) == ("Renamed", "checked")


def test_edit_scan_validation(auth_client):
    upload(auth_client)
    sid = _scan_id()
    assert auth_client.post(f"/scans/{sid}/edit", data={"filename": "  ", "notes": ""}).status_code == 422
    assert auth_client.post(f"/scans/{sid}/edit", data={"filename": "ok", "notes": "x" * 2001}).status_code == 422


def test_delete_scan_removes_results(auth_client):
    upload(auth_client)
    sid = _scan_id()
    resp = auth_client.post(f"/scans/{sid}/delete")
    assert resp.status_code == 302
    assert db.session.get(Scan, sid) is None
    assert db.session.query(ScanResult).count() == 0


def test_export_csv(auth_client):
    upload(auth_client)
    resp = auth_client.get(f"/scans/{_scan_id()}/export.csv")
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    lines = resp.data.decode().strip().splitlines()
    assert lines[0].endswith("predicted_label,confidence")
    assert len(lines) == 3


def test_users_cannot_see_each_others_scans(client, app):
    make_user("alice")
    make_user("mallory")
    login(client, "alice")
    upload(client)
    sid = _scan_id()
    client.post("/auth/logout")
    login(client, "mallory")
    for method, url in [("get", f"/scans/{sid}"), ("get", f"/scans/{sid}/edit"),
                        ("post", f"/scans/{sid}/delete"), ("get", f"/scans/{sid}/export.csv")]:
        assert getattr(client, method)(url).status_code == 404
    assert db.session.get(Scan, sid) is not None
    assert b"No scans yet" in client.get("/scans/").data


def test_missing_scan_404(auth_client):
    resp = auth_client.get("/scans/999")
    assert resp.status_code == 404
    assert b"Not found" in resp.data

import io

import pytest

from app.extensions import db
from app.models import Scan, User

from .conftest import PASSWORD, make_csv, make_user


def api_upload(client, headers, data=None, filename="traffic.csv", **fields):
    payload = {"file": (io.BytesIO(make_csv() if data is None else data), filename), **fields}
    return client.post("/api/v1/scans", data=payload, headers=headers,
                       content_type="multipart/form-data")


def test_index_lists_endpoints(client):
    body = client.get("/api/v1").get_json()
    assert body["version"] == "v1" and "scans" in body["endpoints"]


# ---- auth -----------------------------------------------------------------

def test_register(client):
    resp = client.post("/api/v1/auth/register",
                       json={"username": "bob", "email": "bob@example.com", "password": PASSWORD})
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["username"] == "bob" and "password_hash" not in body


def test_register_validation_and_conflict(client, user):
    resp = client.post("/api/v1/auth/register", json={"username": "b", "email": "x", "password": "1"})
    assert resp.status_code == 422
    assert set(resp.get_json()["error"]["details"]["fields"]) == {"username", "email", "password"}
    resp = client.post("/api/v1/auth/register",
                       json={"username": "alice", "email": "z@example.com", "password": PASSWORD})
    assert resp.status_code == 409
    assert resp.get_json()["error"]["type"] == "conflict"


def test_non_json_body_rejected(client):
    resp = client.post("/api/v1/auth/token", data="username=alice")
    assert resp.status_code == 400
    assert "JSON" in resp.get_json()["error"]["message"]


def test_token_and_me(client, api_headers):
    resp = client.get("/api/v1/auth/me", headers=api_headers)
    assert resp.status_code == 200
    assert resp.get_json()["username"] == "alice"


def test_token_bad_credentials(client, user):
    resp = client.post("/api/v1/auth/token", json={"username": "alice", "password": "nope-nope"})
    assert resp.status_code == 401
    assert resp.headers["WWW-Authenticate"].startswith("Bearer")


@pytest.mark.parametrize("header", [None, "Basic abc", "Bearer ", "Bearer not-a-token"])
def test_protected_endpoints_reject_bad_auth(client, user, header):
    headers = {"Authorization": header} if header else {}
    resp = client.get("/api/v1/scans", headers=headers)
    assert resp.status_code == 401
    assert resp.get_json()["error"]["type"] == "unauthorized"


def test_session_cookie_is_not_enough_for_api(auth_client):
    assert auth_client.get("/api/v1/scans").status_code == 401


def test_expired_token(client, app, api_headers):
    app.config["API_TOKEN_TTL_SECONDS"] = -1
    resp = client.get("/api/v1/scans", headers=api_headers)
    assert resp.status_code == 401
    assert "expired" in resp.get_json()["error"]["message"]


def test_password_change_invalidates_token(client, api_headers):
    user = db.session.query(User).filter_by(username="alice").one()
    user.set_password("a-brand-new-password")
    db.session.commit()
    assert client.get("/api/v1/scans", headers=api_headers).status_code == 401


# ---- scans CRUD -----------------------------------------------------------

def test_create_scan(client, api_headers):
    resp = api_upload(client, api_headers, name="api scan", notes="from curl")
    assert resp.status_code == 201
    body = resp.get_json()
    assert resp.headers["Location"] == f"/api/v1/scans/{body['id']}"
    assert body["filename"] == "api scan" and body["notes"] == "from curl"
    assert body["status"] == "completed"
    assert (body["total_rows"], body["malicious_count"], body["benign_count"]) == (2, 1, 1)
    assert body["links"]["results"].endswith("/results")


@pytest.mark.parametrize("data, filename, status, err_type", [
    (make_csv(), "t.json", 415, "unsupported_media_type"),
    (b"x,y\n1,2\n", "t.csv", 422, "validation_error"),
])
def test_create_scan_validation(client, api_headers, data, filename, status, err_type):
    resp = api_upload(client, api_headers, data=data, filename=filename)
    assert resp.status_code == status
    assert resp.get_json()["error"]["type"] == err_type


def test_create_scan_missing_columns_details(client, api_headers):
    resp = api_upload(client, api_headers, data=b"duration\n1\n")
    details = resp.get_json()["error"]["details"]
    assert "proto" in details["missing_columns"]


def test_create_scan_without_file(client, api_headers):
    resp = client.post("/api/v1/scans", headers=api_headers, data={},
                       content_type="multipart/form-data")
    assert resp.status_code == 400


def test_create_scan_too_large(client, app, api_headers):
    app.config["MAX_CONTENT_LENGTH"] = 512
    resp = api_upload(client, api_headers, data=make_csv(rows=["1,1,1,1,1,tcp,SF"] * 100))
    assert resp.status_code == 413
    assert "MB" in resp.get_json()["error"]["message"]


def test_list_scans_paginated(client, api_headers):
    for i in range(3):
        api_upload(client, api_headers, name=f"s{i}")
    body = client.get("/api/v1/scans?per_page=2", headers=api_headers).get_json()
    assert body["total"] == 3 and body["pages"] == 2 and len(body["items"]) == 2
    assert body["items"][0]["filename"] == "s2"  # newest first
    page2 = client.get("/api/v1/scans?per_page=2&page=2", headers=api_headers).get_json()
    assert len(page2["items"]) == 1


@pytest.mark.parametrize("query", ["page=0", "per_page=1000", "page=abc"])
def test_list_scans_bad_paging(client, api_headers, query):
    assert client.get(f"/api/v1/scans?{query}", headers=api_headers).status_code == 400


def test_get_scan_and_results(client, api_headers):
    sid = api_upload(client, api_headers).get_json()["id"]
    assert client.get(f"/api/v1/scans/{sid}", headers=api_headers).get_json()["id"] == sid
    results = client.get(f"/api/v1/scans/{sid}/results", headers=api_headers).get_json()
    assert results["total"] == 2
    assert results["items"][0].keys() == {"row", "label", "confidence", "features"}
    malicious = client.get(f"/api/v1/scans/{sid}/results?label=malicious", headers=api_headers).get_json()
    assert [r["label"] for r in malicious["items"]] == ["malicious"]
    bad = client.get(f"/api/v1/scans/{sid}/results?label=evil", headers=api_headers)
    assert bad.status_code == 422


def test_patch_scan(client, api_headers):
    sid = api_upload(client, api_headers, notes="old").get_json()["id"]
    resp = client.patch(f"/api/v1/scans/{sid}", json={"filename": "renamed"}, headers=api_headers)
    assert resp.status_code == 200
    assert resp.get_json()["filename"] == "renamed" and resp.get_json()["notes"] == "old"
    resp = client.patch(f"/api/v1/scans/{sid}", json={"notes": None}, headers=api_headers)
    assert resp.get_json()["notes"] is None


@pytest.mark.parametrize("body, status", [
    ({}, 400), ({"owner": 2}, 400), ({"filename": 5}, 400), ({"filename": ""}, 422),
    ({"notes": "x" * 2001}, 422),
])
def test_patch_scan_validation(client, api_headers, body, status):
    sid = api_upload(client, api_headers).get_json()["id"]
    assert client.patch(f"/api/v1/scans/{sid}", json=body, headers=api_headers).status_code == status


def test_delete_scan(client, api_headers):
    sid = api_upload(client, api_headers).get_json()["id"]
    resp = client.delete(f"/api/v1/scans/{sid}", headers=api_headers)
    assert resp.status_code == 204 and resp.data == b""
    assert client.get(f"/api/v1/scans/{sid}", headers=api_headers).status_code == 404


def test_other_users_scans_are_404(client, api_headers):
    sid = api_upload(client, api_headers).get_json()["id"]
    make_user("mallory")
    token = client.post("/api/v1/auth/token",
                        json={"username": "mallory", "password": PASSWORD}).get_json()["access_token"]
    other = {"Authorization": f"Bearer {token}"}
    assert client.get(f"/api/v1/scans/{sid}", headers=other).status_code == 404
    assert client.patch(f"/api/v1/scans/{sid}", json={"notes": "x"}, headers=other).status_code == 404
    assert client.delete(f"/api/v1/scans/{sid}", headers=other).status_code == 404
    assert client.get("/api/v1/scans", headers=other).get_json()["total"] == 0
    assert db.session.get(Scan, sid) is not None


def test_method_not_allowed_is_json(client, api_headers):
    resp = client.put("/api/v1/scans", headers=api_headers)
    assert resp.status_code == 405
    assert resp.get_json()["error"]["status"] == 405


def test_unexpected_error_returns_json_500(client, app, api_headers, monkeypatch):
    from app.services import scans

    def explode(*a, **k):
        raise RuntimeError("database on fire")

    monkeypatch.setattr(scans, "list_scans", explode)
    app.config["PROPAGATE_EXCEPTIONS"] = False
    resp = client.get("/api/v1/scans", headers=api_headers)
    assert resp.status_code == 500
    body = resp.get_json()
    assert body["error"]["type"] == "internal_server_error"
    assert "fire" not in body["error"]["message"]  # no internals leaked

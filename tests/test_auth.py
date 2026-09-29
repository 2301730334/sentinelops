import pytest

from app import create_app
from app.extensions import db
from app.models import User
from app.security import is_safe_redirect

from .conftest import PASSWORD, login, make_user


def test_register_page_renders(client):
    resp = client.get("/auth/register")
    assert resp.status_code == 200
    assert b"Create an account" in resp.data


def test_register_creates_user_and_logs_in(client, app):
    resp = client.post("/auth/register", data={
        "username": "bob", "email": "Bob@Example.com",
        "password": PASSWORD, "confirm": PASSWORD,
    })
    assert resp.status_code == 302
    user = db.session.query(User).filter_by(username="bob").one()
    assert user.email == "bob@example.com"
    assert user.password_hash != PASSWORD
    # already signed in, so visiting login redirects away
    assert client.get("/auth/login").status_code == 302


@pytest.mark.parametrize("data, field", [
    ({"username": "x", "email": "a@b.co", "password": PASSWORD, "confirm": PASSWORD}, b"Username must be"),
    ({"username": "bobby", "email": "nope", "password": PASSWORD, "confirm": PASSWORD}, b"valid email"),
    ({"username": "bobby", "email": "a@b.co", "password": "short", "confirm": "short"}, b"at least 8"),
    ({"username": "bobby", "email": "a@b.co", "password": PASSWORD, "confirm": "other-pass"}, b"do not match"),
])
def test_register_validation_errors(client, data, field):
    resp = client.post("/auth/register", data=data)
    assert resp.status_code == 422
    assert field in resp.data
    assert db.session.query(User).count() == 0


def test_register_duplicate_rejected(client, user):
    resp = client.post("/auth/register", data={
        "username": "ALICE", "email": "new@example.com", "password": PASSWORD, "confirm": PASSWORD,
    })
    assert resp.status_code == 409
    assert b"already registered" in resp.data


def test_login_success_with_username_or_email(client, user):
    assert login(client).status_code == 302
    client.post("/auth/logout")
    assert login(client, username="alice@example.com").status_code == 302


def test_login_failure(client, user):
    resp = login(client, password="wrong-password")
    assert resp.status_code == 401
    assert b"Invalid username or password" in resp.data


def test_login_respects_safe_next(client, user):
    resp = client.post("/auth/login?next=/auth/register",
                       data={"username": "alice", "password": PASSWORD})
    assert resp.headers["Location"].endswith("/auth/register")


def test_login_ignores_external_next(client, user):
    resp = client.post("/auth/login?next=https://evil.example/",
                       data={"username": "alice", "password": PASSWORD})
    assert "evil.example" not in resp.headers["Location"]


def test_logout(auth_client):
    resp = auth_client.post("/auth/logout")
    assert resp.status_code == 302
    # logout requires login, so a second call bounces to the login page
    assert "/auth/login" in auth_client.post("/auth/logout").headers["Location"]


def test_navbar_shows_username_when_signed_in(auth_client):
    assert b"Signed in as" in auth_client.get("/").data


@pytest.mark.parametrize("target, ok", [
    ("/scans/1", True), ("", False), (None, False),
    ("https://evil.example", False), ("//evil.example", False), ("scans", False),
])
def test_is_safe_redirect(target, ok):
    assert is_safe_redirect(target) is ok


def test_csrf_blocks_forms_without_token():
    app = create_app("testing", overrides={"CSRF_ENABLED": True})
    with app.app_context():
        db.create_all()
        make_user()
        client = app.test_client()
        resp = client.post("/auth/login", data={"username": "alice", "password": PASSWORD})
        assert resp.status_code == 400

        client.get("/auth/login")  # issues a token into the session
        with client.session_transaction() as sess:
            token = sess["_csrf_token"]
        resp = client.post("/auth/login", data={
            "username": "alice", "password": PASSWORD, "csrf_token": token,
        })
        assert resp.status_code == 302
        db.drop_all()

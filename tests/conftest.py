import pytest

from app import create_app
from app.extensions import db as _db


@pytest.fixture()
def app():
    app = create_app("testing")
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


PASSWORD = "correct-horse-1"


def make_user(username="alice", email=None, password=PASSWORD):
    from app.models import User

    user = User(username=username, email=email or f"{username}@example.com")
    user.set_password(password)
    _db.session.add(user)
    _db.session.commit()
    return user


@pytest.fixture()
def user(app):
    return make_user()


def login(client, username="alice", password=PASSWORD):
    return client.post("/auth/login", data={"username": username, "password": password})


@pytest.fixture()
def auth_client(client, user):
    login(client)
    return client

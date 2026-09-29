import pytest

from app import create_app
from app.extensions import db as _db


@pytest.fixture(scope="session")
def stub_predictor():
    """Train the synthetic stub model once for the whole test session."""
    from app.ml import SklearnPredictor
    from app.ml.stub import train_stub_model

    return SklearnPredictor(train_stub_model(n=300, seed=1), version="test-stub")


@pytest.fixture()
def app(stub_predictor):
    from app.ml import set_predictor

    app = create_app("testing")
    set_predictor(app, stub_predictor)
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

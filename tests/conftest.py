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


HEADER = "duration,orig_bytes,resp_bytes,orig_pkts,resp_pkts,proto,conn_state"
BENIGN_ROW = "4.2,820,15400,9,18,tcp,SF"
SCAN_ROW = "-,-,-,1,0,tcp,S0"


def make_csv(rows=(BENIGN_ROW, SCAN_ROW), header=HEADER) -> bytes:
    return ("\n".join([header, *rows]) + "\n").encode()


def upload(client, data=None, filename="traffic.csv", url="/scans/upload", **fields):
    import io

    payload = {"file": (io.BytesIO(make_csv() if data is None else data), filename), **fields}
    return client.post(url, data=payload, content_type="multipart/form-data")


@pytest.fixture()
def api_headers(client, user):
    resp = client.post("/api/v1/auth/token", json={"username": "alice", "password": PASSWORD})
    return {"Authorization": f"Bearer {resp.get_json()['access_token']}"}

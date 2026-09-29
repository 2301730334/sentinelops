import joblib
import numpy as np
import pytest
from sklearn.dummy import DummyClassifier

from app import create_app
from app.ml import (BENIGN, FEATURE_COLUMNS, MALICIOUS, ModelUnavailableError, Prediction,
                    Predictor, SklearnPredictor, get_predictor, normalize_label, set_predictor)
from app.ml.features import rows_to_matrix
from app.ml.sklearn_predictor import file_sha256
from app.ml.stub import generate_synthetic, stub_bundle

PORT_SCAN = {"duration": 0.0, "orig_bytes": 0.0, "resp_bytes": 0.0, "orig_pkts": 1.0,
             "resp_pkts": 0.0, "proto": "tcp", "conn_state": "S0"}
WEB_SESSION = {"duration": 4.2, "orig_bytes": 820.0, "resp_bytes": 15400.0, "orig_pkts": 9.0,
               "resp_pkts": 18.0, "proto": "tcp", "conn_state": "SF"}


def test_predictor_is_abstract():
    with pytest.raises(TypeError):
        Predictor()


@pytest.mark.parametrize("raw, expected", [
    ("Benign", BENIGN), ("benign ", BENIGN), (0, BENIGN), (np.int64(0), BENIGN), (False, BENIGN),
    ("Malicious", MALICIOUS), (1, MALICIOUS), (True, MALICIOUS), ("PartOfAHorizontalPortScan", MALICIOUS),
])
def test_normalize_label(raw, expected):
    assert normalize_label(raw) == expected


def test_synthetic_data_is_deterministic_and_balanced():
    rows_a, labels_a = generate_synthetic(n=200, seed=3)
    rows_b, labels_b = generate_synthetic(n=200, seed=3)
    assert rows_a == rows_b and list(labels_a) == list(labels_b)
    assert set(rows_a[0]) == set(FEATURE_COLUMNS)
    assert 0.3 < (labels_a == "Benign").mean() < 0.7


def test_rows_to_matrix_orders_columns():
    m = rows_to_matrix([WEB_SESSION])
    assert m.shape == (1, len(FEATURE_COLUMNS))
    assert list(m[0]) == [WEB_SESSION[c] for c in FEATURE_COLUMNS]


def test_stub_model_separates_obvious_cases(stub_predictor):
    preds = stub_predictor.predict([PORT_SCAN, WEB_SESSION])
    assert [p.label for p in preds] == [MALICIOUS, BENIGN]
    assert all(0.5 <= p.confidence <= 1.0 for p in preds)


def test_stub_model_accuracy_on_holdout(stub_predictor):
    rows, labels = generate_synthetic(n=300, seed=99)
    preds = stub_predictor.predict(rows)
    accuracy = np.mean([p.label == normalize_label(l) for p, l in zip(preds, labels)])
    assert accuracy > 0.9


def test_empty_input_returns_empty_list(stub_predictor):
    assert stub_predictor.predict([]) == []


def test_unknown_category_is_tolerated(stub_predictor):
    row = dict(WEB_SESSION, proto="sctp", conn_state="-")
    assert stub_predictor.predict([row])[0].label in (BENIGN, MALICIOUS)


def test_load_bundle_from_file(tmp_path):
    path = tmp_path / "model.joblib"
    joblib.dump(stub_bundle(n=200, seed=2), path)
    predictor = SklearnPredictor.from_file(str(path))
    assert predictor.version == "stub-rf-v1"
    assert predictor.predict([PORT_SCAN])[0].label == MALICIOUS


def test_load_bare_estimator_without_proba(tmp_path):
    class NoProba:
        def predict(self, X):
            return np.array([1] * len(X))

    path = tmp_path / "bare.joblib"
    joblib.dump(DummyClassifier(strategy="constant", constant="Benign").fit(
        rows_to_matrix([WEB_SESSION, PORT_SCAN]), ["Benign", "Malicious"]), path)
    predictor = SklearnPredictor.from_file(str(path))
    assert predictor.version.startswith("DummyClassifier-")
    assert predictor.predict([PORT_SCAN]) == [Prediction(BENIGN, 1.0)]

    assert SklearnPredictor(NoProba(), version="x").predict([WEB_SESSION]) == [Prediction(MALICIOUS, 1.0)]


def test_checksum_pinning(tmp_path):
    path = tmp_path / "model.joblib"
    joblib.dump(stub_bundle(n=100), path)
    assert SklearnPredictor.from_file(str(path), expected_sha256=file_sha256(str(path)))
    with pytest.raises(ModelUnavailableError, match="checksum"):
        SklearnPredictor.from_file(str(path), expected_sha256="0" * 64)


def test_rejects_invalid_model_objects():
    with pytest.raises(ModelUnavailableError):
        SklearnPredictor(object(), version="x")
    with pytest.raises(ModelUnavailableError, match="unsupported"):
        SklearnPredictor(DummyClassifier(), version="x", features=["src_ip"])


def test_registry_loads_file_and_caches(tmp_path):
    path = tmp_path / "model.joblib"
    joblib.dump(stub_bundle(n=100), path)
    app = create_app("testing", overrides={"MODEL_PATH": str(path)})
    first = get_predictor(app)
    assert first.version == "stub-rf-v1"
    assert get_predictor(app) is first
    set_predictor(app, None)
    assert get_predictor(app) is not first


def test_registry_falls_back_to_stub(tmp_path):
    app = create_app("testing", overrides={"MODEL_PATH": str(tmp_path / "missing.joblib"),
                                           "MODEL_FALLBACK_STUB": True})
    assert get_predictor(app).version.endswith("-inmemory")


def test_registry_raises_without_model_or_fallback(tmp_path):
    app = create_app("testing", overrides={"MODEL_PATH": str(tmp_path / "missing.joblib"),
                                           "MODEL_FALLBACK_STUB": False})
    with pytest.raises(ModelUnavailableError):
        get_predictor(app)


def test_shipped_model_file_loads():
    """models/model.joblib in the repo must load and follow the contract."""
    app = create_app("testing")
    predictor = SklearnPredictor.from_file(app.config["MODEL_PATH"])
    assert predictor.predict([PORT_SCAN, WEB_SESSION])[0].label == MALICIOUS

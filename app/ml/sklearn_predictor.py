"""Predictor backed by a scikit-learn estimator stored with joblib."""
from __future__ import annotations

import hashlib
import logging
from typing import Mapping, Sequence

import joblib

from ..errors import AppError
from .base import Prediction, Predictor, normalize_label
from .features import FEATURE_COLUMNS, rows_to_matrix

log = logging.getLogger(__name__)


class ModelUnavailableError(AppError):
    status_code = 503
    error_type = "model_unavailable"


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class SklearnPredictor(Predictor):
    def __init__(self, estimator, version: str, features: Sequence[str] = FEATURE_COLUMNS):
        if not hasattr(estimator, "predict"):
            raise ModelUnavailableError("Loaded model object has no predict() method.")
        missing = [f for f in features if f not in FEATURE_COLUMNS]
        if missing:
            raise ModelUnavailableError(f"Model expects unsupported features: {missing}")
        self.estimator = estimator
        self.features = tuple(features)
        self._version = version

    @property
    def version(self) -> str:
        return self._version

    @classmethod
    def from_file(cls, path: str, expected_sha256: str | None = None) -> "SklearnPredictor":
        """Load either a bare estimator or a bundle dict {"model", "features", "version"}.

        joblib files are pickles and can execute code on load: only load trusted
        models. Set MODEL_SHA256 to pin the exact file that may be loaded.
        """
        digest = file_sha256(path)
        if expected_sha256 and digest.lower() != expected_sha256.strip().lower():
            raise ModelUnavailableError("Model file checksum does not match MODEL_SHA256.")
        obj = joblib.load(path)
        if isinstance(obj, dict):
            estimator = obj.get("model")
            features = obj.get("features", FEATURE_COLUMNS)
            version = obj.get("version") or f"{type(estimator).__name__}-{digest[:12]}"
        else:
            estimator, features = obj, FEATURE_COLUMNS
            version = f"{type(estimator).__name__}-{digest[:12]}"
        log.info("model_loaded", extra={"model_path": path, "model_version": version,
                                        "sha256": digest})
        return cls(estimator, version=version, features=features)

    def predict(self, rows: Sequence[Mapping]) -> list[Prediction]:
        if not rows:
            return []
        X = rows_to_matrix(rows, self.features)
        labels = self.estimator.predict(X)
        if hasattr(self.estimator, "predict_proba"):
            confidences = self.estimator.predict_proba(X).max(axis=1)
        else:
            confidences = [1.0] * len(labels)
        return [
            Prediction(label=normalize_label(lbl), confidence=float(conf))
            for lbl, conf in zip(labels, confidences)
        ]

"""Loads the configured predictor once per app and caches it."""
from __future__ import annotations

import logging
import os
import threading

from flask import Flask, current_app

from ..metrics import record_model_loaded
from .base import Predictor
from .sklearn_predictor import ModelUnavailableError, SklearnPredictor

log = logging.getLogger(__name__)
_lock = threading.Lock()
_KEY = "sentinelops.predictor"


def load_predictor(app: Flask) -> Predictor:
    path = app.config["MODEL_PATH"]
    if os.path.exists(path):
        return SklearnPredictor.from_file(path, expected_sha256=os.environ.get("MODEL_SHA256"))
    if app.config.get("MODEL_FALLBACK_STUB"):
        from .stub import STUB_VERSION, train_stub_model

        log.warning("model_missing_using_stub", extra={"model_path": path})
        return SklearnPredictor(train_stub_model(), version=f"{STUB_VERSION}-inmemory")
    raise ModelUnavailableError(f"Model file not found at {path}.")


def get_predictor(app: Flask | None = None) -> Predictor:
    app = app or current_app._get_current_object()
    predictor = app.extensions.get(_KEY)
    if predictor is None:
        with _lock:
            predictor = app.extensions.get(_KEY)
            if predictor is None:
                predictor = load_predictor(app)
                app.extensions[_KEY] = predictor
                with app.app_context():
                    record_model_loaded(predictor.version)
    return predictor


def set_predictor(app: Flask, predictor: Predictor | None) -> None:
    """Override (or clear) the cached predictor, e.g. in tests."""
    if predictor is None:
        app.extensions.pop(_KEY, None)
    else:
        app.extensions[_KEY] = predictor
        with app.app_context():
            record_model_loaded(predictor.version)

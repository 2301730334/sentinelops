"""Stub model trained on a tiny synthetic IoT-23-style dataset.

It exists so the whole pipeline works before the real model is ready. The
synthetic traffic mimics three well-known IoT-23 behaviours:

* benign: completed TCP/UDP sessions (mostly SF) with real payloads
* horizontal port scans: TCP SYNs with no reply (S0/REJ), zero bytes, 1-2 packets
* C&C / flooding: short, tiny, repetitive connections (UDP/ICMP floods, keep-alives)

The pipeline uses only scikit-learn classes, so the saved file has no
dependency on this module.
"""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from .features import FEATURE_COLUMNS, NUMERIC_FEATURES

STUB_VERSION = "stub-rf-v1"


def _benign(rng: np.random.Generator, n: int) -> list[dict]:
    rows = []
    for _ in range(n):
        proto = rng.choice(["tcp", "udp", "icmp"], p=[0.6, 0.35, 0.05])
        orig_bytes = float(rng.lognormal(6.0, 1.2))
        resp_bytes = float(rng.lognormal(7.5, 1.5))
        rows.append({
            "duration": float(rng.exponential(3.0)),
            "orig_bytes": orig_bytes,
            "resp_bytes": resp_bytes,
            "orig_pkts": float(max(1, int(orig_bytes / 400) + rng.integers(1, 6))),
            "resp_pkts": float(max(1, int(resp_bytes / 900) + rng.integers(1, 6))),
            "proto": str(proto),
            "conn_state": str(rng.choice(["SF", "S1", "RSTO", "OTH"], p=[0.8, 0.08, 0.07, 0.05])),
        })
    return rows


def _port_scan(rng: np.random.Generator, n: int) -> list[dict]:
    return [{
        "duration": float(rng.choice([0.0, rng.exponential(0.5)])),
        "orig_bytes": 0.0,
        "resp_bytes": 0.0,
        "orig_pkts": float(rng.integers(1, 3)),
        "resp_pkts": float(rng.integers(0, 2)),
        "proto": "tcp",
        "conn_state": str(rng.choice(["S0", "REJ", "RSTOS0", "SH"], p=[0.7, 0.2, 0.05, 0.05])),
    } for _ in range(n)]


def _c2_and_flood(rng: np.random.Generator, n: int) -> list[dict]:
    return [{
        "duration": float(rng.exponential(0.05)),
        "orig_bytes": float(rng.integers(0, 120)),
        "resp_bytes": float(rng.integers(0, 60)),
        "orig_pkts": float(rng.integers(1, 4)),
        "resp_pkts": float(rng.integers(0, 2)),
        "proto": str(rng.choice(["udp", "icmp", "tcp"], p=[0.5, 0.3, 0.2])),
        "conn_state": str(rng.choice(["S0", "OTH", "SF"], p=[0.5, 0.35, 0.15])),
    } for _ in range(n)]


def generate_synthetic(n: int = 600, seed: int = 42, noise: float = 0.03):
    """Return (rows, labels) with roughly 55% benign traffic and some label noise."""
    rng = np.random.default_rng(seed)
    n_benign = int(n * 0.55)
    n_scan = int(n * 0.30)
    n_c2 = n - n_benign - n_scan
    rows = _benign(rng, n_benign) + _port_scan(rng, n_scan) + _c2_and_flood(rng, n_c2)
    labels = np.array(["Benign"] * n_benign + ["Malicious"] * (n_scan + n_c2), dtype=object)
    flip = rng.random(n) < noise
    labels[flip] = np.where(labels[flip] == "Benign", "Malicious", "Benign")
    order = rng.permutation(n)
    return [rows[i] for i in order], labels[order]


def build_pipeline(seed: int = 42) -> Pipeline:
    n_num = len(NUMERIC_FEATURES)
    pre = ColumnTransformer([
        ("num", "passthrough", list(range(n_num))),
        ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False),
         list(range(n_num, len(FEATURE_COLUMNS)))),
    ])
    clf = RandomForestClassifier(n_estimators=40, max_depth=8, random_state=seed, n_jobs=1)
    return Pipeline([("pre", pre), ("clf", clf)])


def train_stub_model(n: int = 600, seed: int = 42) -> Pipeline:
    from .features import rows_to_matrix

    rows, labels = generate_synthetic(n=n, seed=seed)
    model = build_pipeline(seed)
    model.fit(rows_to_matrix(rows), labels)
    return model


def stub_bundle(n: int = 600, seed: int = 42) -> dict:
    """The dict saved to models/model.joblib (see models/README.md)."""
    return {
        "model": train_stub_model(n=n, seed=seed),
        "features": list(FEATURE_COLUMNS),
        "version": STUB_VERSION,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "sklearn_version": sklearn.__version__,
        "notes": "Synthetic stub model. Replace with the real IoT-23 model.",
    }

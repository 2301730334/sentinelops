"""Feature schema shared by the CSV validator, the predictor and the stub trainer.

Column names follow the Zeek conn.log fields used by the IoT-23 dataset.
A model receives a 2-D numpy array (dtype=object) with columns in exactly the
order of FEATURE_COLUMNS: numeric values as float, categorical values as str.
"""
from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np

NUMERIC_FEATURES = ("duration", "orig_bytes", "resp_bytes", "orig_pkts", "resp_pkts")
CATEGORICAL_FEATURES = ("proto", "conn_state")
FEATURE_COLUMNS = NUMERIC_FEATURES + CATEGORICAL_FEATURES

KNOWN_PROTOS = ("tcp", "udp", "icmp")
KNOWN_CONN_STATES = (
    "S0", "S1", "S2", "S3", "SF", "REJ", "RSTO", "RSTR", "RSTOS0", "RSTRH", "SH", "SHR", "OTH",
)

# Zeek writes "-" (unset) or "(empty)" for missing values.
MISSING_TOKENS = {"", "-", "(empty)", "nan", "none", "null"}


def rows_to_matrix(rows: Sequence[Mapping], columns: Sequence[str] = FEATURE_COLUMNS) -> np.ndarray:
    matrix = np.empty((len(rows), len(columns)), dtype=object)
    for i, row in enumerate(rows):
        for j, col in enumerate(columns):
            matrix[i, j] = row[col]
    return matrix

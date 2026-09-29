"""Predictor interface.

Anything that can turn parsed connection records into Predictions can be
plugged in: the scikit-learn predictor below, a remote model server, or a fake
in tests.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Mapping, Sequence

MALICIOUS = "malicious"
BENIGN = "benign"
LABELS = (BENIGN, MALICIOUS)

_BENIGN_ALIASES = {"benign", "0", "false", "normal", "0.0"}


@dataclass(frozen=True)
class Prediction:
    label: str          # "malicious" | "benign"
    confidence: float   # probability of the predicted label, 0..1


def normalize_label(raw) -> str:
    """Map model class labels (0/1, 'Benign'/'Malicious', bools...) to our two labels."""
    return BENIGN if str(raw).strip().lower() in _BENIGN_ALIASES else MALICIOUS


class Predictor(ABC):
    @property
    @abstractmethod
    def version(self) -> str:
        """Identifier stored with every scan for traceability."""

    @abstractmethod
    def predict(self, rows: Sequence[Mapping]) -> list[Prediction]:
        """Predict one label per row. Rows contain every name in FEATURE_COLUMNS."""

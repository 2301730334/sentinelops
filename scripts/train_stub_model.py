#!/usr/bin/env python
"""Train the synthetic stub model and write a sample IoT-23-style CSV.

Usage:
    python scripts/train_stub_model.py                  # -> models/model.joblib
    python scripts/train_stub_model.py --sample-rows 200 # also refresh the sample CSV
"""
from __future__ import annotations

import argparse
import csv
import os
import sys

import joblib
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from app.ml.stub import generate_synthetic, stub_bundle  # noqa: E402

SAMPLE_PATH = os.path.join(ROOT, "app", "static", "samples", "sample_iot23.csv")
# Subset of the Zeek conn.log columns found in IoT-23 "conn.log.labeled" files.
SAMPLE_COLUMNS = [
    "ts", "uid", "id.orig_h", "id.orig_p", "id.resp_h", "id.resp_p", "proto", "service",
    "duration", "orig_bytes", "resp_bytes", "conn_state", "orig_pkts", "resp_pkts", "label",
]


def write_sample(path: str, n: int, seed: int) -> None:
    rng = np.random.default_rng(seed)
    rows, labels = generate_synthetic(n=n, seed=seed, noise=0.0)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ts = 1_545_403_816.0
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=SAMPLE_COLUMNS)
        writer.writeheader()
        for row, label in zip(rows, labels):
            ts += float(rng.exponential(2.0))
            zero = row["orig_bytes"] == 0 and row["resp_bytes"] == 0
            writer.writerow({
                "ts": f"{ts:.6f}",
                "uid": "C" + rng.bytes(9).hex()[:17],
                "id.orig_h": f"192.168.1.{rng.integers(2, 254)}",
                "id.orig_p": int(rng.integers(1024, 65535)),
                "id.resp_h": f"{rng.integers(1, 223)}.{rng.integers(0, 255)}.{rng.integers(0, 255)}.{rng.integers(1, 254)}",
                "id.resp_p": int(rng.choice([22, 23, 53, 80, 443, 8080, 2323, 37215])),
                "proto": row["proto"],
                "service": "-",
                # Zeek writes "-" when a value is unset; the app treats it as 0.
                "duration": "-" if zero and row["duration"] == 0 else f"{row['duration']:.6f}",
                "orig_bytes": "-" if zero else int(row["orig_bytes"]),
                "resp_bytes": "-" if zero else int(row["resp_bytes"]),
                "conn_state": row["conn_state"],
                "orig_pkts": int(row["orig_pkts"]),
                "resp_pkts": int(row["resp_pkts"]),
                "label": label,
            })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=os.path.join(ROOT, "models", "model.joblib"))
    parser.add_argument("--rows", type=int, default=600, help="synthetic training rows")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--sample-rows", type=int, default=0, help="also write a sample CSV")
    args = parser.parse_args()

    bundle = stub_bundle(n=args.rows, seed=args.seed)
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    joblib.dump(bundle, args.output, compress=3)
    print(f"wrote {args.output} ({os.path.getsize(args.output) / 1024:.0f} KiB, version {bundle['version']})")

    if args.sample_rows:
        write_sample(SAMPLE_PATH, args.sample_rows, seed=args.seed + 1)
        print(f"wrote {SAMPLE_PATH} ({args.sample_rows} rows)")


if __name__ == "__main__":
    main()

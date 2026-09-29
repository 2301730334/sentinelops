# Model contract

The app loads `models/model.joblib` (override with `MODEL_PATH`). The file in
the repo is a **stub** trained on synthetic data by
`scripts/train_stub_model.py`. To ship the real IoT-23 model, overwrite this file.
No code changes are needed as long as the model follows this contract.

## Accepted file formats (joblib)

1. **Bundle dict** (recommended)
   ```python
   joblib.dump({
       "model": pipeline,               # any object with .predict (and ideally .predict_proba)
       "features": ["duration", "orig_bytes", "resp_bytes",
                    "orig_pkts", "resp_pkts", "proto", "conn_state"],
       "version": "iot23-rf-v1",        # stored with every scan
   }, "models/model.joblib")
   ```
2. **Bare estimator**: the features default to the order above, and the version is
   derived from the class name + SHA-256 of the file.

## Input the model receives

`predict(X)`, where `X` is a 2-D `numpy` array (`dtype=object`), one row per
connection, columns in the order of `features`:

| column | type | notes |
|---|---|---|
| duration, orig_bytes, resp_bytes, orig_pkts, resp_pkts | float | Zeek `-` → `0.0` |
| proto | str | lowercase: `tcp`, `udp`, `icmp` |
| conn_state | str | uppercase Zeek state: `S0`, `SF`, `REJ` … |

The app does **not** use pandas, so pipelines should select columns by integer
index (e.g. a `ColumnTransformer` using `[0, 1, 2, 3, 4]` and `[5, 6]`), not
by column name.

## Output

`predict` may return `0/1`, `"Benign"/"Malicious"`, or booleans. Anything
other than `benign`/`0`/`false`/`normal` counts as **malicious**. If
`predict_proba` exists, the confidence is the maximum class probability;
otherwise it is 1.0.

## Security

joblib files are pickles, so loading one can run code. Only load models you
trust. Set `MODEL_SHA256=<hex digest>` to refuse any file whose checksum
differs (`sha256sum models/model.joblib`).
Train the model with the same scikit-learn version as `requirements.txt`.

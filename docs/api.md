# REST API reference (v1)

Base path: `/api/v1`. Request and response bodies are JSON, except scan upload,
which is `multipart/form-data`.

## Authentication

1. `POST /auth/token` with username (or email) and password returns a signed bearer token.
2. Send `Authorization: Bearer <token>` on every other request.

Tokens expire after `API_TOKEN_TTL_SECONDS` (default 1 h). Changing the password
invalidates them. Browser session cookies are **not** accepted by the API, so
the API needs no CSRF protection.

## Endpoints

| Method | Path | Auth | Success | Description |
|---|---|---|---|---|
| GET | `/api/v1` | – | 200 | API index |
| POST | `/auth/register` | – | 201 | Body `{username, email, password}` → user |
| POST | `/auth/token` | – | 200 | Body `{username, password}` → `{access_token, token_type, expires_in}` |
| GET | `/auth/me` | ✔ | 200 | Current user |
| GET | `/scans?page=&per_page=` | ✔ | 200 | Paginated list, newest first (`per_page` ≤ 100) |
| POST | `/scans` | ✔ | 201 | Multipart: `file` (required), `name`, `notes`. Returns the scan plus a `Location` header |
| GET | `/scans/{id}` | ✔ | 200 | One scan |
| GET | `/scans/{id}/results?label=&page=&per_page=` | ✔ | 200 | Per-row predictions; `label` = `malicious` or `benign` |
| PATCH | `/scans/{id}` | ✔ | 200 | Body with `filename` and/or `notes` (`null` clears notes) |
| DELETE | `/scans/{id}` | ✔ | 204 | Deletes the scan and its results |

A scan owned by another user returns **404** (not 403), so scan ids can't be probed.

### Scan object

```json
{
  "id": 1, "filename": "Lab capture", "original_filename": "sample_iot23.csv",
  "notes": null, "status": "completed", "error_message": null,
  "total_rows": 200, "malicious_count": 89, "benign_count": 111, "malicious_ratio": 0.445,
  "model_version": "stub-rf-v1",
  "created_at": "2026-09-29T09:24:18.278967", "updated_at": "2026-09-29T09:24:18.297381",
  "links": {"self": "/api/v1/scans/1", "results": "/api/v1/scans/1/results"}
}
```

`status` is `completed` or `failed`. If the model fails, the scan is kept with
`status: "failed"` and an `error_message`.

### List envelope

```json
{"items": [...], "page": 1, "per_page": 20, "total": 3, "pages": 1}
```

## Errors

```json
{"error": {"status": 404, "type": "not_found", "message": "Scan not found."}, "request_id": "..."}
```

| Status | When |
|---|---|
| 400 | Malformed request: no JSON body, missing file, bad paging parameter, unknown PATCH field |
| 401 | Missing, invalid or expired token; bad credentials (`WWW-Authenticate: Bearer`) |
| 404 | Unknown route, or scan not found / not yours |
| 405 | Method not allowed |
| 409 | Username or email already registered |
| 413 | Upload larger than `MAX_UPLOAD_MB` |
| 415 | File is not a `.csv` |
| 422 | Validation failed: missing columns, invalid values (with line numbers), too many rows, bad field values |
| 500 | Unexpected error (logged with the request id; no internals in the response) |
| 503 | Model unavailable (readiness) |

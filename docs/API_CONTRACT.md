# API contract — NFC + Face Verification

## Authentication

- `POST /api/v1/auth/login`: JSON `{ "username": "admin", "password": "..." }`; returns an admin bearer token valid for 12 hours.
- Admin endpoints use `Authorization: Bearer <access_token>`.
- Device endpoints use `X-Device-Token: <DEVICE_TOKEN>`.
- `GET /api/v1/health`: health check; no token required.

## Admin / dashboard endpoints

- `GET /api/v1/students`: student profiles, active card UID, last successful scan time, and whether an active face template exists.
- `POST /api/v1/students`, `PUT /api/v1/students/{id}`, `DELETE /api/v1/students/{id}`: create, update, or deactivate students/cards.
- `GET /api/v1/scans?limit=100`: completed NFC attempts, newest first. A face mismatch is retained in `scan_events` with `face_verified=0`, but never creates an `attendance_records` row.
- `GET /api/v1/stats`: daily successful scan statistics using Vietnam local date.
- `GET /api/v1/config`: server and database configuration.
- `GET /api/v1/faces`, `POST /api/v1/faces`, `DELETE /api/v1/faces/{id}`: admin face-template management.
- `GET /api/v1/sessions`, `POST /api/v1/sessions`: attendance sessions.
- `GET /api/v1/attendance?session_id=...`: attendance records.
- `WS /ws/events`: authenticate with `{"type":"auth","token":"<admin-token>"}`; receives `scan.created`, `students.changed`, and `faces.changed`.

## Device protocol — two stages

The same `event_id` must be used for both requests in one physical card tap. Generate a new unique `event_id` for every new tap.

### 1. ESP32 reads NFC and requests the student's embedding

`POST /api/v1/verification/start`

```json
{
  "event_id": "GATE-BOOT7-000001",
  "card_uid": "A1B200000001",
  "session_id": 1
}
```

`session_id` is optional. If omitted, the server selects the session only when exactly one active session exists.

The server validates the active NFC card and student, finds the active face template, stores a pending verification attempt (60-second expiry), and returns:

```json
{
  "event_id": "GATE-BOOT7-000001",
  "student_id": 12,
  "face_embedding": "BASE64_DATA",
  "embedding_dim": 512,
  "model_name": "...",
  "model_version": "...",
  "expires_at": "...Z",
  "created": true
}
```

ESP32 forwards `event_id` and the embedding metadata/data to ESP32-S3-CAM. S3-CAM performs the face comparison locally.

### 2. ESP32 sends the S3-CAM result

`POST /api/v1/verification/complete`

```json
{
  "event_id": "GATE-BOOT7-000001",
  "face_result": 1
}
```

Use `face_result: 1` for a match and `face_result: 0` for no match. The server records the scan event after receiving the face result. A successful result also creates/updates attendance; a failed result is logged with `face_verified=0` but never marks attendance.

### Important behavior

- `event_id` links the NFC request and final face result. Do not generate a second ID for the face result.
- A pending attempt expires after 60 seconds.
- Repeating `start` with the same event ID and UID while pending returns the same pending attempt; a different UID or already closed attempt returns `409`.
- Repeating `complete` after successful completion returns `created: false`; it does not create another scan or attendance record.
- `POST /api/v1/scans` is disabled (`410 Gone`) because it bypasses face verification.
- A card without an active face template cannot start verification.
- Device token authenticates the ESP32 request. It does not cryptographically prove that the reported face result came from the S3-CAM; protect the device network/token accordingly.

## Simulator

```bash
python simulator/send_scan.py --uid A1B200000001 --face-result 1
```

`--face-result` simulates the S3-CAM result; it does not run an actual face-recognition model.

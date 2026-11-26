# API contract — Attenda v3

All URLs below are relative to the FastAPI host, for example `http://127.0.0.1:8000`.

## Authentication

- Admin login: `POST /api/v1/auth/login` with `{ "username": "admin", "password": "..." }`.
- Dashboard requests use `Authorization: Bearer <access_token>`.
- Device requests use `X-Device-Token: <DEVICE_TOKEN from .env>`.
- `GET /api/v1/health` reports API and database schema status without authentication.

## New student registration — admin → backend

### 1. Load blank NFC cards into inventory

- `POST /api/v1/cards/inventory` — admin request:

```json
{ "card_uid": "AABBCCDD" }
```

- `GET /api/v1/cards/inventory` — lists cards with `available`, `reserved`, `assigned`, or `disabled` state.
- `DELETE /api/v1/cards/inventory/{card_uid}` — removes an `available` card; if registration history references it, the server marks it `disabled` instead of deleting historical data.

The UID must be read from the actual physical card before it is entered. The backend must not invent a UID. When creating a registration, the backend reserves the oldest `available` UID and returns it to the dashboard so staff can hand out the matching physical card.

### 2. Create a pending registration

- `POST /api/v1/registrations` — admin request:

```json
{
  "student_code": "23110001",
  "full_name": "Nguyen Van A",
  "class_name": "CE01"
}
```

The response contains `registration_id`, the pre-reserved `card_uid`, and status `waiting_for_scan`. No row is inserted into `students` at this stage.

- `GET /api/v1/registrations` — returns registrations that are waiting for scan or captured and waiting for review.
- `GET /api/v1/registrations/{registration_id}/image` — admin-authenticated binary image response.
- `POST /api/v1/registrations/{registration_id}/retry` — clears the previous capture and returns a captured registration to `waiting_for_scan`.
- `POST /api/v1/registrations/{registration_id}/approve` — only a complete captured registration can be approved. This transaction creates the official `students`, `nfc_cards`, and `face_templates` rows and marks the inventory card `assigned`.
- `POST /api/v1/registrations/{registration_id}/reject` — rejects the pending registration, clears its biometric capture, and returns the reserved card to `available`.

### 3. Device uploads NFC + face capture

- `POST /api/v1/registrations/capture` — device-authenticated request:

```json
{
  "card_uid": "AABBCCDD",
  "face_embedding": "BASE64_EMBEDDING_BYTES",
  "embedding_dim": 512,
  "face_image_base64": "BASE64_JPEG_BYTES",
  "image_mime": "image/jpeg"
}
```

The server finds the pending registration by its reserved UID and stores the embedding plus decoded image bytes in `registration_queue`. `event_id` is optional for enrollment; if omitted, the server generates one. `model_name` and `model_version` are optional metadata; if omitted, the server stores `unspecified`. `embedding_dim` defaults to 512 and `image_mime` defaults to `image/jpeg`. Supported image MIME types are JPEG, PNG, and WebP; maximum decoded image size is 5 MB. Repeated upload with the same `event_id` and UID is idempotent. If no event ID is sent, a repeat upload for a card whose registration is already captured returns the existing captured registration without overwriting it. The browser loads the stored image from the authenticated image endpoint.

## Daily attendance — device → backend

Attendance is a separate process from new student registration. NFC alone never writes an attendance record.

### 1. Start verification after NFC read

- `POST /api/v1/verification/start` — device request:

```json
{ "event_id": "SCAN-0001", "card_uid": "AABBCCDD", "session_id": 1 }
```

`session_id` is optional. If omitted, the server associates the only active session when exactly one exists. For a valid active card with an active face template, the server returns `status: "pending"`, the student's ID, and the stored face embedding. Other statuses include `unregistered`, `inactive_card`, and `no_face_template`.

### 2. Complete verification after the camera comparison

- `POST /api/v1/verification/complete` — device request:

```json
{ "event_id": "SCAN-0001", "face_result": true }
```

The same `event_id` from the first request must be reused. The server records attendance only when the attempt is pending, has not expired, the card/student/template are still active, and `face_result` is true. A false result is stored as `face_mismatch`. Attempts expire after 90 seconds. Repeated completion requests do not create duplicate attendance.

The old direct `POST /api/v1/scans` endpoint is disabled with HTTP 410 so NFC-only requests cannot bypass face verification.

## Other admin endpoints

- `GET /api/v1/students`, `PUT /api/v1/students/{id}`, `DELETE /api/v1/students/{id}` — official student directory and deactivation. Direct `POST /api/v1/students` is disabled; new students must use the registration queue.
- `GET /api/v1/scans?limit=100` — daily verification attempts and legacy scan records, newest first.
- `GET /api/v1/stats` — counts in Vietnam local time.
- `GET /api/v1/faces`, `POST /api/v1/faces`, `DELETE /api/v1/faces/{id}` — face-template administration.
- `GET /api/v1/sessions`, `POST /api/v1/sessions` — attendance sessions.
- `GET /api/v1/attendance?session_id=1` — attendance records.
- `GET /api/v1/config` — server and database configuration.
- `WS /ws/events` — after connection, send `{"type":"auth","token":"<admin-token>"}`. Events include `scan.created`, `students.changed`, `registrations.changed`, `cards.changed`, and `attendance.changed`.

## Common errors

- `401`: missing or invalid admin/device token.
- `404`: unknown registration, image, event, or student.
- `409`: duplicate UID/student code, card not available, invalid registration state, or conflicting event ID.
- `410`: an obsolete direct NFC-only write route is disabled.
- `422`: invalid payload, UID, Base64, image type, or image signature.

OpenAPI documentation: `http://127.0.0.1:8000/docs`.

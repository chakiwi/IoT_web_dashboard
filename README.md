# Attenda v4 — AIoT Attendance Dashboard

Attenda manages student registration, NFC card inventory, face-template registration, and attendance verification using React + TypeScript, FastAPI, and SQLite.

## Components

- Frontend: React, TypeScript, Vite
- Backend: FastAPI
- Database: SQLite schema v3 (application release v4)
- Device connection: ESP32 / PN532 and ESP32-S3-CAM through the documented HTTP API

## Install and run on Windows

1. Install Python 3.11+ and Node.js LTS.
2. Extract the project ZIP.
3. Run `setup.bat` and wait for Python packages, npm packages, database setup, and frontend build to finish.
4. Run `start.bat`.
5. Open `http://127.0.0.1:8000`.

Default demo login after `.env` is created from `.env.example`:

- Username: `admin`
- Password: `attenda123`

The setup script does not overwrite an existing `.env`. It creates/upgrades the database schema without automatically seeding demo users. Review `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `APP_SECRET`, `DEVICE_TOKEN`, and `DEMO_MODE` when using an older project copy. The provided `.env.example` uses `DEMO_MODE=false`, so startup does not add fictional students. Setup creates/upgrades the schema only. To explicitly seed a fresh empty database with fictional students/cards, run `python -m database.setup --seed-demo`; seeding is skipped when the database already contains at least one student.

## New student registration

1. Read the real UIDs from unused physical NFC cards and add them under **Settings → Unused NFC card inventory**.
2. Under **Students**, click **Add student** and enter `student_code`, `full_name`, and `class_name`.
3. Confirming creates a pending registration and reserves one `available` card UID. The student is not inserted into the official directory yet.
4. Give the student the physical card matching the reserved UID shown in **New registrations**.
5. The device sends that UID, face embedding, and face image to `/api/v1/registrations/capture`.
6. Review the face image in the queue and approve or reject the registration.
7. Only approval creates official `students`, `nfc_cards`, and `face_templates` records.

A registration is matched by the actual preloaded card UID, not arrival order. Staff must hand out the physical card corresponding to the UID reserved for that student.

## Daily attendance

1. Device reads a registered NFC UID and creates a unique `event_id`.
2. `POST /api/v1/verification/start` checks the card and returns that student's face embedding.
3. The face-processing device compares the captured face with the returned embedding.
4. `POST /api/v1/verification/complete` sends the same `event_id` and `face_result`.
5. Attendance is recorded only when both NFC and face checks succeed.

NFC-only `POST /api/v1/scans` is disabled to prevent bypassing face verification. See `docs/API_CONTRACT.md` for payloads and responses.

## Database schema v3 (application release v4)

- `students`: approved student profiles.
- `nfc_cards`: active/inactive cards linked to approved students.
- `face_templates`: face embeddings for approved students.
- `card_inventory`: physical blank-card UIDs and their availability/reservation state.
- `registration_queue`: pending/captured/approved/rejected registration data, including face embedding and binary face image.
- `verification_attempts`: pending and completed two-stage attendance verification attempts.
- `attendance_sessions`, `scan_events`, `attendance_records`: attendance sessions, verified scans, and attendance outcomes.

On startup, an existing schema v2 database is upgraded by creating the new v3 tables. Existing students, cards, face templates, scan events, and attendance records are retained. Historical schema-v2 NFC-only scan rows are displayed as legacy/unverified history and are not counted as face-verified check-ins. A legacy database with the old `stations` table is backed up before the legacy migration.

## v4 attendance behavior

- Sessions must be explicitly active and within `starts_at <= now < ends_at` when a scan starts and completes. If there is no active session or more than one active session, the device must send a valid `session_id` or the request is rejected.
- A 10-minute grace period after the session start is counted as `present`; later successful scans are `late`. A later scan cannot downgrade an existing `present` record to `late`.
- Naive session timestamps are interpreted as Asia/Ho_Chi_Minh; timezone-aware ISO-8601 values are normalized to UTC.
- `event_id` must be new across both `verification_attempts` and legacy `scan_events`.
- Re-enabling a disabled student restores only the latest registered card and latest face template.

## Included test database

The included `database/attendance.db` is a clean test starting point: it contains one sample student (`23110001`), that student's original demo card, five unused test UIDs (`AABB0001`–`AABB0005`) in the inventory, and no registration queue rows, attendance sessions, face templates, scan history, verification attempts, or attendance records. The five UIDs are placeholders for software testing only; they are not claims about any physical card.

## Tests

- Backend: `python -m unittest discover -s tests -v`
- Frontend: `cd frontend` then `npm.cmd install` and `npm.cmd run build`
- API docs: `http://127.0.0.1:8000/docs`

Physical device firmware is maintained separately and is not modified by this project package. The backend API contract is documented, but the physical-device integration must be tested after the separately maintained firmware calls these endpoints.

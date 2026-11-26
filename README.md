# Attenda — AIoT Attendance Dashboard

Attenda manages student registration, NFC card inventory, face-template registration, and attendance verification using React + TypeScript, FastAPI, and SQLite.

## Components

- Frontend: React, TypeScript, Vite
- Backend: FastAPI
- Database: SQLite schema v3
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

The setup script does not overwrite an existing `.env`. Review `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `APP_SECRET`, `DEVICE_TOKEN`, and `DEMO_MODE` when using an older project copy. With `DEMO_MODE=true`, the server seeds fictional students and already-assigned demo cards only; it does not seed NFC-only scans that could be mistaken for face-verified check-ins.

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

## Database schema v3

- `students`: approved student profiles.
- `nfc_cards`: active/inactive cards linked to approved students.
- `face_templates`: face embeddings for approved students.
- `card_inventory`: physical blank-card UIDs and their availability/reservation state.
- `registration_queue`: pending/captured/approved/rejected registration data, including face embedding and binary face image.
- `verification_attempts`: pending and completed two-stage attendance verification attempts.
- `attendance_sessions`, `scan_events`, `attendance_records`: attendance sessions, verified scans, and attendance outcomes.

On startup, an existing schema v2 database is upgraded by creating the new v3 tables. Existing students, cards, face templates, scan events, and attendance records are retained. Historical schema-v2 NFC-only scan rows are displayed as legacy/unverified history and are not counted as face-verified check-ins. A legacy database with the old `stations` table is backed up before the legacy migration.

## Tests

- Backend: `python -m unittest discover -s tests -v`
- Frontend: `cd frontend` then `npm.cmd install` and `npm.cmd run build`
- API docs: `http://127.0.0.1:8000/docs`

Physical device firmware is maintained separately and is not modified by this project package. The backend API contract is documented, but the physical-device integration must be tested after the separately maintained firmware calls these endpoints.

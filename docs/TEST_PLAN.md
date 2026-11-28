# Test plan — Attenda v4 (schema v3)

## Automated backend tests

Run from the project root:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The test suite verifies:

- SQLite schema v3 creates inventory, registration queue, and verification-attempt tables without a `stations` table.
- An unused card UID can be loaded into inventory.
- Creating a registration reserves a real available UID but does not create a student immediately.
- A device capture links embedding and binary image data to the matching reserved UID.
- Approval creates the official student, NFC card, and face-template rows and marks the inventory card assigned.
- A new attendance attempt first returns the face embedding but does not write attendance.
- A face mismatch does not create attendance; a successful face result does.
- Repeating completion does not create duplicate attendance.
- Legacy NFC-only scan records remain visible as legacy/unverified history, not as face-verified check-ins.

## Frontend checks

```powershell
cd frontend
npm.cmd install
npm.cmd run build
```

The TypeScript project build should complete without type errors. The Vite production bundle is generated in `frontend/dist`.

## Manual end-to-end checks on Windows

1. Run `setup.bat`, then `start.bat`, and open `http://127.0.0.1:8000`.
2. Sign in with credentials from `.env`.
3. Open **Settings → Unused NFC card inventory** and add the actual UIDs from several blank cards.
4. Open **Students → Add student**, enter the three requested fields, and confirm. Verify that the registration is visible in **New registrations**, not in the official Students list, and has a reserved UID.
5. Send a matching registration-capture payload to `POST /api/v1/registrations/capture`. Verify the queued record displays the captured image.
6. Approve it and verify the student appears in Students with the reserved UID and a face template.
7. Run attendance start with the approved UID. Verify that no attendance row is created yet.
8. Complete once with `face_result=false`; verify no attendance row is created.
9. Start a new event and complete with `face_result=true`; verify exactly one attendance row is created.
10. Restart the server and verify the data remains in SQLite.

## Not verified by this package

- Physical ESP32 / ESP32-S3-CAM capture and face-comparison firmware integration. The device-side firmware is maintained separately; this package defines the backend API contract but does not modify device firmware.
- Face-recognition accuracy, camera exposure/lighting, liveness detection, concurrent multi-reader operation, and long-duration hardware reliability.


## Attendance session and edge-case checks (v4)
- A verification start is rejected unless exactly one currently open session is resolved, or a valid `session_id` is provided.
- Naive session timestamps are interpreted as Asia/Ho_Chi_Minh; timezone-aware ISO-8601 timestamps are normalized to UTC.
- A verification completion is rejected as expired if its session becomes inactive or passes `ends_at` before the face result arrives.
- The first 10 minutes from `starts_at` are considered present; later successful scans are late. A later scan cannot downgrade an existing present record to late.
- An `event_id` already present in legacy `scan_events` cannot start a new verification attempt.
- Re-enabling a student re-enables only that student's latest registered NFC card and latest face template.
- Setup does not seed demo users by default; `--seed-demo` is an explicit opt-in and seeds only an empty student directory.
- LAN security script rejects the stock `demo-device-token-change-me` as well as short or placeholder device tokens.

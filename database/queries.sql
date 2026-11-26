-- Open database/attendance.db in a SQLite GUI or sqlite3 CLI and run these.
SELECT * FROM students ORDER BY student_code;
SELECT * FROM attendance_sessions;
SELECT s.student_code, s.full_name, c.uid FROM students s JOIN nfc_cards c ON c.student_id=s.id;
SELECT event_id, occurred_at, student_code, full_name, card_uid, result, face_verified, verification_status
  FROM v_recent_scans ORDER BY occurred_at DESC LIMIT 20;
SELECT result, COUNT(*) AS total FROM scan_events GROUP BY result;
-- Only fully verified NFC + face events are inserted into scan_events and attendance_records.
SELECT state, COUNT(*) AS total FROM verification_attempts GROUP BY state;

-- Open database/attendance.db in a SQLite GUI or sqlite3 CLI and run these.
SELECT * FROM students ORDER BY student_code;
SELECT * FROM attendance_sessions;
SELECT s.student_code, s.full_name, c.uid FROM students s JOIN nfc_cards c ON c.student_id=s.id;
SELECT event_id, occurred_at, station_name, student_code, full_name, result
  FROM v_recent_scans ORDER BY occurred_at DESC LIMIT 20;
SELECT * FROM v_scan_counts_by_station;
SELECT result, COUNT(*) AS total FROM scan_events GROUP BY result;
-- IMPORTANT: recognized means an NFC UID matched a registered card; not final attendance.

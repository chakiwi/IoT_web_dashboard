-- Open database/attendance.db in a SQLite GUI or sqlite3 CLI and run these.
SELECT * FROM students ORDER BY student_code;
SELECT * FROM card_inventory ORDER BY id;
SELECT * FROM registration_queue ORDER BY created_at DESC;
SELECT * FROM attendance_sessions;
SELECT s.student_code,s.full_name,c.uid FROM students s JOIN nfc_cards c ON c.student_id=s.id;
SELECT event_id,card_uid,status,started_at,completed_at
  FROM verification_attempts ORDER BY started_at DESC LIMIT 20;
SELECT event_id,occurred_at,card_uid,student_code,full_name,result
  FROM v_recent_scans ORDER BY occurred_at DESC LIMIT 20;
SELECT status,COUNT(*) AS total FROM verification_attempts GROUP BY status;
-- Attendance is written only after NFC and face verification both succeed.

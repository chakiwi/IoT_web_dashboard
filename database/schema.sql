PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS students (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 full_name TEXT NOT NULL,
 student_code TEXT NOT NULL UNIQUE,
 class_name TEXT NOT NULL,
 is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS nfc_cards (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 uid TEXT NOT NULL UNIQUE,
 student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE RESTRICT,
 card_type TEXT NOT NULL DEFAULT 'ISO14443-A',
 is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
 registered_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_one_active_card_per_student
 ON nfc_cards(student_id) WHERE is_active = 1;

CREATE TABLE IF NOT EXISTS face_templates (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 face_id TEXT NOT NULL UNIQUE,
 student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
 face_embedding TEXT NOT NULL,
 embedding_dim INTEGER NOT NULL DEFAULT 512,
 model_name TEXT NOT NULL,
 model_version TEXT NOT NULL,
 is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS ix_face_templates_student ON face_templates(student_id);
CREATE INDEX IF NOT EXISTS ix_face_templates_active ON face_templates(is_active);

CREATE TABLE IF NOT EXISTS card_inventory (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 uid TEXT NOT NULL UNIQUE,
 status TEXT NOT NULL DEFAULT 'available' CHECK(status IN ('available','reserved','assigned','disabled')),
 reservation_registration_id TEXT,
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 reserved_at TEXT,
 assigned_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_card_inventory_status ON card_inventory(status,id);

CREATE TABLE IF NOT EXISTS registration_queue (
 registration_id TEXT PRIMARY KEY,
 student_code TEXT NOT NULL,
 full_name TEXT NOT NULL,
 class_name TEXT NOT NULL,
 card_uid TEXT NOT NULL REFERENCES card_inventory(uid) ON DELETE RESTRICT,
 status TEXT NOT NULL DEFAULT 'waiting_for_scan'
   CHECK(status IN ('waiting_for_scan','captured','approved','rejected')),
 face_embedding TEXT,
 embedding_dim INTEGER,
 model_name TEXT,
 model_version TEXT,
 face_image BLOB,
 face_image_mime TEXT,
 capture_event_id TEXT UNIQUE,
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 captured_at TEXT,
 reviewed_at TEXT,
 rejection_reason TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_pending_registration_student_code
 ON registration_queue(student_code) WHERE status IN ('waiting_for_scan','captured');
CREATE UNIQUE INDEX IF NOT EXISTS uq_pending_registration_card
 ON registration_queue(card_uid) WHERE status IN ('waiting_for_scan','captured');
CREATE INDEX IF NOT EXISTS ix_registration_queue_status ON registration_queue(status,created_at);

CREATE TABLE IF NOT EXISTS attendance_sessions (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 title TEXT NOT NULL,
 starts_at TEXT NOT NULL,
 ends_at TEXT NOT NULL,
 is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
 CHECK (ends_at > starts_at)
);

CREATE TABLE IF NOT EXISTS scan_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 event_id TEXT NOT NULL UNIQUE,
 session_id INTEGER REFERENCES attendance_sessions(id) ON DELETE SET NULL,
 card_uid TEXT NOT NULL,
 card_id INTEGER REFERENCES nfc_cards(id) ON DELETE SET NULL,
 student_id INTEGER REFERENCES students(id) ON DELETE SET NULL,
 result TEXT NOT NULL CHECK(result IN ('recognized','unregistered','inactive_card')),
 occurred_at TEXT NOT NULL,
 received_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS ix_scans_time ON scan_events(occurred_at DESC);
CREATE INDEX IF NOT EXISTS ix_scans_student_time ON scan_events(student_id,occurred_at DESC);

CREATE TABLE IF NOT EXISTS verification_attempts (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 event_id TEXT NOT NULL UNIQUE,
 card_uid TEXT NOT NULL,
 card_id INTEGER REFERENCES nfc_cards(id) ON DELETE SET NULL,
 student_id INTEGER REFERENCES students(id) ON DELETE SET NULL,
 face_template_id INTEGER REFERENCES face_templates(id) ON DELETE SET NULL,
 session_id INTEGER REFERENCES attendance_sessions(id) ON DELETE SET NULL,
 status TEXT NOT NULL CHECK(status IN ('pending','verified','face_mismatch','unregistered','inactive_card','no_face_template','expired')),
 face_result INTEGER CHECK(face_result IN (0,1)),
 scan_event_id INTEGER REFERENCES scan_events(id) ON DELETE SET NULL,
 started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 expires_at TEXT NOT NULL,
 completed_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_verification_attempts_time ON verification_attempts(started_at DESC);
CREATE INDEX IF NOT EXISTS ix_verification_attempts_status ON verification_attempts(status);

CREATE TABLE IF NOT EXISTS attendance_records (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 session_id INTEGER NOT NULL REFERENCES attendance_sessions(id) ON DELETE CASCADE,
 student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE RESTRICT,
 status TEXT NOT NULL CHECK(status IN ('present','late','absent','pending')),
 scan_event_id INTEGER REFERENCES scan_events(id) ON DELETE SET NULL,
 marked_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 UNIQUE(session_id,student_id)
);

CREATE VIEW IF NOT EXISTS v_recent_scans AS
 SELECT e.event_id,e.occurred_at,e.received_at,e.session_id,e.card_uid,e.result,
        s.student_code,s.full_name,s.class_name
 FROM scan_events e LEFT JOIN students s ON e.student_id=s.id;

PRAGMA user_version = 3;

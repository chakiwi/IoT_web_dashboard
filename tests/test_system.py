from __future__ import annotations

import base64
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DEMO_MODE"] = "false"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "test-password"
os.environ["APP_SECRET"] = "test-secret-long-enough-for-local-test-only"
os.environ["DEVICE_TOKEN"] = "test-device-token-long-enough"

from backend.app.main import app  # noqa: E402
from database.db import connect, initialize  # noqa: E402
from database.seed import seed  # noqa: E402


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        os.environ["ATTENDA_DB_PATH"] = str(Path(self.temp.name) / "test.db")
        self.context = TestClient(app)
        self.client = self.context.__enter__()
        token = self.client.post("/api/v1/auth/login", json={
            "username": "admin", "password": "test-password"
        }).json()["access_token"]
        self.admin_headers = {"Authorization": "Bearer " + token}
        self.device_headers = {"X-Device-Token": "test-device-token-long-enough"}

        with connect() as db:
            with db:
                self.student_id = db.execute(
                    "INSERT INTO students(full_name,student_code,class_name,is_active) VALUES(?,?,?,1)",
                    ("Nguyễn Minh Anh", "TEST0001", "CE-TEST"),
                ).lastrowid
                db.execute(
                    "INSERT INTO nfc_cards(uid,student_id,card_type,is_active) VALUES(?,?,?,1)",
                    ("A1B2C3D4", self.student_id, "TEST_ISO14443-A"),
                )
        self._add_face(self.student_id, "FACE-BASE")

    def tearDown(self):
        self.context.__exit__(None, None, None)
        self.temp.cleanup()

    def _add_face(self, student_id: int, face_id: str):
        response = self.client.post("/api/v1/faces", headers=self.admin_headers, json={
            "face_id": face_id,
            "student_id": student_id,
            "face_embedding": base64.b64encode(b"1234").decode(),
            "embedding_dim": 1,
            "model_name": "test-model",
            "model_version": "1",
            "is_active": True,
        })
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["id"]

    def _add_session(self, title="Test session", starts_delta=-5, ends_delta=60, is_active=True):
        now = datetime.now(timezone.utc)
        response = self.client.post("/api/v1/sessions", headers=self.admin_headers, json={
            "title": title,
            "starts_at": (now + timedelta(minutes=starts_delta)).isoformat(),
            "ends_at": (now + timedelta(minutes=ends_delta)).isoformat(),
            "is_active": is_active,
        })
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["id"]

    def _start(self, event_id: str, session_id: int | None = None, uid="A1B2C3D4"):
        payload = {"event_id": event_id, "card_uid": uid}
        if session_id is not None:
            payload["session_id"] = session_id
        return self.client.post("/api/v1/verification/start", headers=self.device_headers, json=payload)

    def _complete(self, event_id: str, face_result=True):
        return self.client.post("/api/v1/verification/complete", headers=self.device_headers, json={
            "event_id": event_id, "face_result": face_result
        })

    def test_schema_and_station_endpoint_removed(self):
        health = self.client.get("/api/v1/health").json()
        self.assertEqual(health["schema_version"], 3)
        with connect() as db:
            names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"students", "nfc_cards", "face_templates", "attendance_sessions", "scan_events",
                         "attendance_records", "card_inventory", "registration_queue", "verification_attempts"} <= names)
        self.assertNotIn("stations", names)
        self.assertEqual(self.client.get("/api/v1/stations", headers=self.admin_headers).status_code, 404)

    def test_registration_auto_reserves_inventory_uid_then_approves(self):
        for uid in ("C0FFEE01", "C0FFEE02"):
            response = self.client.post("/api/v1/cards/inventory", json={"card_uid": uid}, headers=self.admin_headers)
            self.assertEqual(response.status_code, 201, response.text)
        registration = self.client.post("/api/v1/registrations", json={
            "student_code": "99900001", "full_name": "Test Registration", "class_name": "TEST01"
        }, headers=self.admin_headers)
        self.assertEqual(registration.status_code, 201, registration.text)
        data = registration.json()
        self.assertEqual(data["card_uid"], "C0FFEE01")
        approve_too_early = self.client.post(
            f"/api/v1/registrations/{data['registration_id']}/approve", headers=self.admin_headers
        )
        self.assertEqual(approve_too_early.status_code, 409)

        embedding = base64.b64encode(b"1234").decode()
        image = base64.b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 20 + b"\xff\xd9").decode()
        capture = self.client.post("/api/v1/registrations/capture", headers=self.device_headers, json={
            "card_uid": data["card_uid"], "face_embedding": embedding, "embedding_dim": 1,
            "face_image_base64": image,
        })
        self.assertEqual(capture.status_code, 201, capture.text)
        self.assertEqual(capture.json()["status"], "captured")
        repeated = self.client.post("/api/v1/registrations/capture", headers=self.device_headers, json={
            "card_uid": data["card_uid"], "face_embedding": embedding, "embedding_dim": 1,
            "face_image_base64": image,
        })
        self.assertFalse(repeated.json()["created"])

        approved = self.client.post(
            f"/api/v1/registrations/{data['registration_id']}/approve", headers=self.admin_headers
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        students = self.client.get("/api/v1/students", headers=self.admin_headers).json()
        new_student = next(student for student in students if student["student_code"] == "99900001")
        self.assertEqual(new_student["card_uid"], "C0FFEE01")
        self.assertEqual(new_student["has_face"], 1)
        inventory = self.client.get("/api/v1/cards/inventory", headers=self.admin_headers).json()
        self.assertEqual(next(card for card in inventory if card["uid"] == "C0FFEE01")["status"], "assigned")

    def test_rejected_registration_releases_reserved_uid(self):
        self.client.post("/api/v1/cards/inventory", json={"card_uid": "C0FFEE02"}, headers=self.admin_headers)
        first = self.client.post("/api/v1/registrations", json={
            "student_code": "99900002", "full_name": "First Candidate", "class_name": "TEST01"
        }, headers=self.admin_headers)
        self.assertEqual(first.status_code, 201, first.text)
        rejected = self.client.post(
            f"/api/v1/registrations/{first.json()['registration_id']}/reject", headers=self.admin_headers
        )
        self.assertEqual(rejected.status_code, 200, rejected.text)
        cards = self.client.get("/api/v1/cards/inventory", headers=self.admin_headers).json()
        self.assertEqual(next(card for card in cards if card["uid"] == "C0FFEE02")["status"], "available")
        second = self.client.post("/api/v1/registrations", json={
            "student_code": "99900003", "full_name": "Second Candidate", "class_name": "TEST01"
        }, headers=self.admin_headers)
        self.assertEqual(second.status_code, 201, second.text)
        self.assertEqual(second.json()["card_uid"], "C0FFEE02")

    def test_no_active_or_out_of_window_session_is_rejected(self):
        no_session = self._start("NO-SESSION")
        self.assertEqual(no_session.status_code, 409, no_session.text)
        ended_session = self._add_session("Ended", starts_delta=-60, ends_delta=-1)
        ended = self._start("ENDED-SESSION", session_id=ended_session)
        self.assertEqual(ended.status_code, 409, ended.text)
        future_session = self._add_session("Future", starts_delta=10, ends_delta=60)
        future = self._start("FUTURE-SESSION", session_id=future_session)
        self.assertEqual(future.status_code, 409, future.text)

    def test_attendance_requires_nfc_and_face_and_uses_grace_period(self):
        session_id = self._add_session(starts_delta=-5, ends_delta=60)
        failed_start = self._start("FACE-FAIL", session_id)
        self.assertEqual(failed_start.status_code, 200, failed_start.text)
        self.assertEqual(failed_start.json()["status"], "pending")
        self.assertEqual(self.client.get("/api/v1/attendance", headers=self.admin_headers).json(), [])
        failed = self._complete("FACE-FAIL", False)
        self.assertEqual(failed.json()["status"], "face_mismatch")
        replay_failed = self._complete("FACE-FAIL", True)
        self.assertEqual(replay_failed.json()["status"], "face_mismatch")
        self.assertEqual(self.client.get("/api/v1/attendance", headers=self.admin_headers).json(), [])

        good_start = self._start("FACE-GOOD", session_id)
        self.assertEqual(good_start.status_code, 200, good_start.text)
        self.assertIn("face_embedding", good_start.json())
        good = self._complete("FACE-GOOD", True)
        self.assertEqual(good.json()["status"], "verified")
        attendance = self.client.get("/api/v1/attendance", headers=self.admin_headers).json()
        self.assertEqual(len(attendance), 1)
        self.assertEqual(attendance[0]["status"], "present")

        # Repeated successful scans cannot downgrade an existing present record to late.
        with connect() as db:
            with db:
                db.execute(
                    "UPDATE attendance_sessions SET starts_at=? WHERE id=?",
                    ((datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(), session_id),
                )
        second_start = self._start("FACE-GOOD-SECOND", session_id)
        self.assertEqual(second_start.status_code, 200, second_start.text)
        self.assertEqual(self._complete("FACE-GOOD-SECOND", True).json()["status"], "verified")
        attendance = self.client.get("/api/v1/attendance", headers=self.admin_headers).json()
        self.assertEqual(attendance[0]["status"], "present")

    def test_late_after_grace_period(self):
        session_id = self._add_session("Late test", starts_delta=-20, ends_delta=60)
        started = self._start("LATE-EVENT", session_id)
        self.assertEqual(started.status_code, 200, started.text)
        completed = self._complete("LATE-EVENT", True)
        self.assertEqual(completed.json()["status"], "verified")
        attendance = self.client.get("/api/v1/attendance", headers=self.admin_headers).json()
        self.assertEqual(attendance[0]["status"], "late")

    def test_session_closed_between_start_and_complete_expires_attempt(self):
        session_id = self._add_session("Close during verify", starts_delta=-5, ends_delta=60)
        started = self._start("CLOSE-WHILE-PENDING", session_id)
        self.assertEqual(started.status_code, 200, started.text)
        with connect() as db:
            with db:
                db.execute("UPDATE attendance_sessions SET is_active=0 WHERE id=?", (session_id,))
        completed = self._complete("CLOSE-WHILE-PENDING", True)
        self.assertEqual(completed.json()["status"], "expired")
        self.assertEqual(self.client.get("/api/v1/attendance", headers=self.admin_headers).json(), [])
        with connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM scan_events").fetchone()[0], 0)

    def test_event_id_already_in_legacy_scan_history_is_rejected(self):
        session_id = self._add_session("Legacy collision", starts_delta=-5, ends_delta=60)
        with connect() as db:
            with db:
                card = db.execute("SELECT id FROM nfc_cards WHERE uid='A1B2C3D4'").fetchone()
                db.execute(
                    """INSERT INTO scan_events(event_id,session_id,card_uid,card_id,student_id,result,occurred_at)
                       VALUES(?,?,?,?,?,'recognized',?)""",
                    ("LEGACY-COLLISION", session_id, "A1B2C3D4", card["id"], self.student_id, datetime.now(timezone.utc).isoformat()),
                )
        response = self._start("LEGACY-COLLISION", session_id)
        self.assertEqual(response.status_code, 409, response.text)
        with connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM verification_attempts WHERE event_id='LEGACY-COLLISION'").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM scan_events WHERE event_id='LEGACY-COLLISION'").fetchone()[0], 1)

    def test_reenable_student_restores_latest_card_and_face(self):
        disabled = self.client.delete(f"/api/v1/students/{self.student_id}", headers=self.admin_headers)
        self.assertEqual(disabled.status_code, 200, disabled.text)
        with connect() as db:
            self.assertEqual(db.execute("SELECT is_active FROM nfc_cards WHERE student_id=?", (self.student_id,)).fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT is_active FROM face_templates WHERE student_id=?", (self.student_id,)).fetchone()[0], 0)
        updated = self.client.put(f"/api/v1/students/{self.student_id}", headers=self.admin_headers, json={
            "full_name": "Nguyễn Minh Anh", "student_code": "TEST0001", "class_name": "CE-TEST", "is_active": True
        })
        self.assertEqual(updated.status_code, 200, updated.text)
        with connect() as db:
            self.assertEqual(db.execute("SELECT is_active FROM nfc_cards WHERE student_id=?", (self.student_id,)).fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT is_active FROM face_templates WHERE student_id=?", (self.student_id,)).fetchone()[0], 1)


    def test_multiple_open_sessions_require_explicit_session_id(self):
        self._add_session("Open A", starts_delta=-5, ends_delta=60)
        self._add_session("Open B", starts_delta=-5, ends_delta=60)
        response = self._start("MULTI-SESSION")
        self.assertEqual(response.status_code, 409, response.text)

    def test_seed_does_not_repopulate_a_partially_cleaned_database(self):
        with connect() as db:
            before = db.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        self.assertEqual(before, 1)
        seed(include_scans=False)
        with connect() as db:
            after = db.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        self.assertEqual(after, 1)


    def test_v2_database_migration_preserves_students_and_rebuilds_view(self):
        legacy_path = Path(self.temp.name) / "legacy-v2.db"
        legacy = sqlite3.connect(legacy_path)
        legacy.executescript("""
            CREATE TABLE students (
                id INTEGER PRIMARY KEY AUTOINCREMENT, full_name TEXT NOT NULL,
                student_code TEXT NOT NULL UNIQUE, class_name TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
            );
            CREATE TABLE nfc_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT NOT NULL UNIQUE,
                student_id INTEGER NOT NULL REFERENCES students(id), card_type TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1, registered_at TEXT NOT NULL
            );
            CREATE TABLE scan_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
                session_id INTEGER, card_uid TEXT NOT NULL, card_id INTEGER, student_id INTEGER,
                result TEXT NOT NULL, occurred_at TEXT NOT NULL,
                received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE VIEW v_recent_scans AS SELECT event_id,card_uid,'OLD_STATION' AS station_name FROM scan_events;
            INSERT INTO students(id,full_name,student_code,class_name,is_active,created_at)
              VALUES(1,'Legacy Student','LEGACY01','CE-OLD',1,'2026-01-01T00:00:00Z');
            INSERT INTO nfc_cards(id,uid,student_id,card_type,is_active,registered_at)
              VALUES(1,'DEADBEEF',1,'ISO14443-A',1,'2026-01-01T00:00:00Z');
            PRAGMA user_version=2;
        """)
        legacy.close()
        initialize(legacy_path)
        with connect(legacy_path) as migrated:
            self.assertEqual(migrated.execute("PRAGMA user_version").fetchone()[0], 3)
            self.assertEqual(migrated.execute("SELECT student_code FROM students WHERE id=1").fetchone()[0], "LEGACY01")
            self.assertEqual(migrated.execute("SELECT uid FROM nfc_cards WHERE id=1").fetchone()[0], "DEADBEEF")
            view_sql = migrated.execute("SELECT sql FROM sqlite_master WHERE type='view' AND name='v_recent_scans'").fetchone()[0]
            self.assertNotIn("station_name", view_sql)
            self.assertIsNotNone(migrated.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='registration_queue'").fetchone())
            self.assertEqual(migrated.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_naive_session_timestamps_are_interpreted_as_vietnam_time(self):
        response = self.client.post("/api/v1/sessions", headers=self.admin_headers, json={
            "title": "Local-time session",
            "starts_at": "2026-11-28T20:00:00",
            "ends_at": "2026-11-28T21:00:00",
            "is_active": True,
        })
        self.assertEqual(response.status_code, 201, response.text)
        with connect() as db:
            row = db.execute("SELECT starts_at,ends_at FROM attendance_sessions WHERE id=?", (response.json()["id"],)).fetchone()
        self.assertTrue(row["starts_at"].endswith("Z"))
        self.assertTrue(row["ends_at"].endswith("Z"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

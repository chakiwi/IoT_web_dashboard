"""SQLite repository for Attenda. NFC UID identifies a card, not a person."""
from __future__ import annotations

import os
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
SCHEMA = BASE / "schema.sql"
DEFAULT_DB_PATH = BASE / "attendance.db"
VN_TZ = timezone(timedelta(hours=7), name="Asia/Ho_Chi_Minh")
LATE_GRACE_MINUTES = 10


def db_path() -> Path:
    return Path(os.environ.get("ATTENDA_DB_PATH", str(DEFAULT_DB_PATH))).resolve()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_datetime_utc(value: str) -> datetime:
    """Parse ISO-8601; naive values are interpreted as Vietnam local time."""
    raw = str(value).strip()
    if not raw:
        raise ValueError("Thời gian không được để trống")
    if raw.endswith(("Z", "z")):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("Thời gian phải theo định dạng ISO 8601") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=VN_TZ)
    return parsed.astimezone(timezone.utc)


def datetime_to_utc_iso(value: str) -> str:
    return parse_datetime_utc(value).isoformat(timespec="seconds").replace("+00:00", "Z")


def session_is_open(session: sqlite3.Row | dict, at: datetime | None = None) -> bool:
    if not session or not bool(session["is_active"]):
        return False
    now = at or datetime.now(timezone.utc)
    starts = parse_datetime_utc(session["starts_at"])
    ends = parse_datetime_utc(session["ends_at"])
    return starts <= now < ends


def attendance_status_for(session: sqlite3.Row | dict, at: datetime | None = None) -> str:
    """A 10-minute grace period after session start is considered present."""
    now = at or datetime.now(timezone.utc)
    starts = parse_datetime_utc(session["starts_at"])
    return "present" if now <= starts + timedelta(minutes=LATE_GRACE_MINUTES) else "late"


@contextmanager
def connect(path: str | Path | None = None):
    location = Path(path) if path else db_path()
    location.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(location, timeout=8)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=8000")
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
    finally:
        conn.close()


def initialize(path: str | Path | None = None) -> Path:
    """Create or upgrade the schema while preserving existing records."""
    location = Path(path) if path else db_path()
    location.parent.mkdir(parents=True, exist_ok=True)
    probe = sqlite3.connect(location)
    try:
        version = probe.execute("PRAGMA user_version").fetchone()[0]
        tables = {row[0] for row in probe.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        probe.close()

    if version < 2 and "stations" in tables:
        backup = location.with_name(location.stem + "_legacy_backup" + location.suffix)
        if not backup.exists():
            shutil.copy2(location, backup)
        temp = location.with_name(location.stem + "_migration" + location.suffix)
        if temp.exists():
            temp.unlink()
        _migrate_legacy(backup, temp)
        temp.replace(location)
    else:
        with connect(location) as db:
            if version < 3:
                # The legacy v2 view may contain station columns; rebuild it for schema v3.
                db.execute("DROP VIEW IF EXISTS v_recent_scans")
            db.executescript(SCHEMA.read_text(encoding="utf-8"))
    return location


def _migrate_legacy(old_path: Path, new_path: Path) -> None:
    with connect(old_path) as old, connect(new_path) as new:
        new.executescript(SCHEMA.read_text(encoding="utf-8"))
        for student in old.execute("SELECT * FROM students ORDER BY id"):
            new.execute(
                "INSERT INTO students(id,full_name,student_code,class_name,is_active,created_at) VALUES(?,?,?,?,?,?)",
                (student["id"], student["full_name"], student["student_code"], student["class_name"], student["is_active"], student["created_at"]),
            )
        for card in old.execute("SELECT * FROM nfc_cards"):
            new.execute(
                "INSERT INTO nfc_cards(id,uid,student_id,card_type,is_active,registered_at) VALUES(?,?,?,?,?,?)",
                (card["id"], card["uid"], card["student_id"], card["card_type"], card["is_active"], card["registered_at"]),
            )
        for event in old.execute("SELECT * FROM scan_events"):
            new.execute(
                "INSERT INTO scan_events(id,event_id,card_uid,card_id,student_id,result,occurred_at,received_at) VALUES(?,?,?,?,?,?,?,?)",
                (event["id"], event["event_id"], event["card_uid"], event["card_id"], event["student_id"], event["result"], event["occurred_at"], event["received_at"]),
            )
        new.commit()


def normalize_uid(uid: str) -> str:
    value = uid.strip().upper().replace(":", "").replace(" ", "").replace("-", "")
    if not (2 <= len(value) <= 32 and len(value) % 2 == 0) or any(char not in "0123456789ABCDEF" for char in value):
        raise ValueError("UID phải là chuỗi hex chẵn, 2-32 ký tự")
    return value


def record_scan(db: sqlite3.Connection, event_id: str, card_uid: str, session_id: int | None = None):
    event_id = event_id.strip()
    uid = normalize_uid(card_uid)
    if not event_id or len(event_id) > 100:
        raise ValueError("event_id phải dài 1-100 ký tự")
    if session_id is None:
        raise ValueError("Không có buổi điểm danh hợp lệ cho lượt quét")
    if not db.in_transaction:
        db.execute("BEGIN IMMEDIATE")

    existing = db.execute("SELECT * FROM scan_events WHERE event_id=?", (event_id,)).fetchone()
    if existing:
        if existing["card_uid"] != uid:
            raise ValueError("event_id đã được dùng với dữ liệu khác")
        row = db.execute("SELECT * FROM v_recent_scans WHERE event_id=?", (event_id,)).fetchone()
        return dict(row), False

    session = db.execute("SELECT * FROM attendance_sessions WHERE id=?", (session_id,)).fetchone()
    if not session or not session_is_open(session):
        raise ValueError("Buổi điểm danh chưa bắt đầu, đã kết thúc hoặc đã bị đóng")

    card = db.execute("SELECT id,student_id,is_active FROM nfc_cards WHERE uid=?", (uid,)).fetchone()
    if card is None:
        card_id, student_id, result = None, None, "unregistered"
    elif not card["is_active"]:
        card_id, student_id, result = card["id"], card["student_id"], "inactive_card"
    else:
        card_id, student_id, result = card["id"], card["student_id"], "recognized"

    now = utc_now()
    cursor = db.execute(
        """INSERT INTO scan_events(event_id,session_id,card_uid,card_id,student_id,result,occurred_at)
           VALUES(?,?,?,?,?,?,?)""",
        (event_id, session_id, uid, card_id, student_id, result, now),
    )
    scan_event_pk = cursor.lastrowid

    if result == "recognized" and student_id:
        attendance_status = attendance_status_for(session)
        db.execute(
            """INSERT INTO attendance_records(session_id,student_id,status,scan_event_id)
               VALUES(?,?,?,?)
               ON CONFLICT(session_id,student_id) DO UPDATE SET
                 status=CASE
                   WHEN attendance_records.status='present' OR excluded.status='present' THEN 'present'
                   ELSE excluded.status END,
                 scan_event_id=CASE
                   WHEN attendance_records.status='present' THEN attendance_records.scan_event_id
                   WHEN excluded.status='present' THEN excluded.scan_event_id
                   ELSE attendance_records.scan_event_id END,
                 marked_at=CASE
                   WHEN attendance_records.status IN ('absent','pending') OR excluded.status='present' THEN excluded.marked_at
                   ELSE attendance_records.marked_at END""",
            (session_id, student_id, attendance_status, scan_event_pk),
        )

    row = db.execute("SELECT * FROM v_recent_scans WHERE event_id=?", (event_id,)).fetchone()
    return dict(row), True

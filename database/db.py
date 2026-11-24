"""SQLite repository for Attenda. NFC UID identifies a card, not a person."""
from __future__ import annotations
import os, sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

BASE=Path(__file__).resolve().parent
SCHEMA=BASE/"schema.sql"
DEFAULT_DB_PATH=BASE/"attendance.db"

def db_path():
    return Path(os.environ.get("ATTENDA_DB_PATH",str(DEFAULT_DB_PATH))).resolve()

def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")

@contextmanager
def connect(path=None):
    location=Path(path) if path else db_path()
    location.parent.mkdir(parents=True,exist_ok=True)
    conn=sqlite3.connect(location,timeout=8)
    conn.row_factory=sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=8000")
    conn.execute("PRAGMA journal_mode=WAL")
    try: yield conn
    finally: conn.close()

def initialize(path=None):
    """Create v2 schema; preserve a legacy database backup before replacing it."""
    import shutil
    location=Path(path) if path else db_path()
    location.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(location) as probe:
        version=probe.execute("PRAGMA user_version").fetchone()[0]
        tables={r[0] for r in probe.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if version < 2 and "stations" in tables:
        backup=location.with_name(location.stem+"_legacy_backup"+location.suffix)
        if not backup.exists(): shutil.copy2(location,backup)
        temp=location.with_name(location.stem+"_migration"+location.suffix)
        if temp.exists(): temp.unlink()
        _migrate_legacy(backup,temp)
        temp.replace(location)
    else:
        with connect(location) as db:
            if version < 2:
                # Rebuild the legacy view so its columns match the v2 contract.
                db.execute("DROP VIEW IF EXISTS v_recent_scans")
            db.executescript(SCHEMA.read_text(encoding="utf-8"))
    return location

def _migrate_legacy(old_path,new_path):
    with connect(old_path) as old, connect(new_path) as new:
        new.executescript(SCHEMA.read_text(encoding="utf-8"))
        for s in old.execute("SELECT * FROM students ORDER BY id"):
            new.execute("INSERT INTO students(id,full_name,student_code,class_name,is_active,created_at) VALUES(?,?,?,?,?,?)",
                (s["id"],s["full_name"],s["student_code"],s["class_name"],s["is_active"],s["created_at"]))
        for c in old.execute("SELECT * FROM nfc_cards"):
            new.execute("INSERT INTO nfc_cards(id,uid,student_id,card_type,is_active,registered_at) VALUES(?,?,?,?,?,?)",
                (c["id"],c["uid"],c["student_id"],c["card_type"],c["is_active"],c["registered_at"]))
        for e in old.execute("SELECT * FROM scan_events"):
            new.execute("INSERT INTO scan_events(id,event_id,card_uid,card_id,student_id,result,occurred_at,received_at) VALUES(?,?,?,?,?,?,?,?)",
                (e["id"],e["event_id"],e["card_uid"],e["card_id"],e["student_id"],e["result"],e["occurred_at"],e["received_at"]))
        new.commit()

def normalize_uid(uid:str)->str:
    value=uid.strip().upper().replace(":","").replace(" ","").replace("-","")
    if not (2<=len(value)<=32 and len(value)%2==0) or any(c not in "0123456789ABCDEF" for c in value):
        raise ValueError("UID phải là chuỗi hex chẵn, 2-32 ký tự")
    return value

def record_scan(db,event_id:str,card_uid:str,session_id:int|None=None):
    event_id=event_id.strip()
    uid=normalize_uid(card_uid)
    if not event_id or len(event_id)>100: raise ValueError("event_id phải dài 1-100 ký tự")
    if not db.in_transaction: db.execute("BEGIN IMMEDIATE")
    existing=db.execute("SELECT * FROM scan_events WHERE event_id=?",(event_id,)).fetchone()
    if existing:
        if existing["card_uid"]!=uid: raise ValueError("event_id đã được dùng với dữ liệu khác")
        row=db.execute("SELECT * FROM v_recent_scans WHERE event_id=?",(event_id,)).fetchone()
        return dict(row),False
    card=db.execute("SELECT id,student_id,is_active FROM nfc_cards WHERE uid=?",(uid,)).fetchone()
    if card is None: card_id,student_id,result=None,None,"unregistered"
    elif not card["is_active"]: card_id,student_id,result=card["id"],card["student_id"],"inactive_card"
    else: card_id,student_id,result=card["id"],card["student_id"],"recognized"
    now=utc_now()
    db.execute("""INSERT INTO scan_events(event_id,session_id,card_uid,card_id,student_id,result,occurred_at)
      VALUES(?,?,?,?,?,?,?)""",(event_id,session_id,uid,card_id,student_id,result,now))
    if result=="recognized" and session_id is not None:
        session=db.execute("SELECT * FROM attendance_sessions WHERE id=? AND is_active=1",(session_id,)).fetchone()
        if session and student_id:
            status="late" if now > session["starts_at"] else "present"
            db.execute("""INSERT INTO attendance_records(session_id,student_id,status,scan_event_id)
              VALUES(?,?,?,?) ON CONFLICT(session_id,student_id) DO UPDATE SET
              status=excluded.status,scan_event_id=excluded.scan_event_id,marked_at=excluded.marked_at""",
              (session_id,student_id,status,db.execute("SELECT last_insert_rowid()").fetchone()[0]))
    db.commit()
    row=db.execute("SELECT * FROM v_recent_scans WHERE event_id=?",(event_id,)).fetchone()
    return dict(row),True

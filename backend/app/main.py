from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from database.db import (
    connect,
    datetime_to_utc_iso,
    initialize,
    normalize_uid,
    parse_datetime_utc,
    record_scan,
    session_is_open,
    utc_now,
)
from database.seed import seed

VN_TZ = timezone(timedelta(hours=7), name="Asia/Ho_Chi_Minh")
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env", override=False)
WEB_DIST = ROOT / "frontend" / "dist"
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() in ("1", "true", "yes")
USERNAME = os.getenv("ADMIN_USERNAME", "admin")
PASSWORD = os.getenv("ADMIN_PASSWORD", "attenda123")
SECRET = os.getenv("APP_SECRET", "dev-only-change-before-LAN").encode()
DEVICE_TOKEN = os.getenv("DEVICE_TOKEN", "demo-device-token-change-me")
TOKEN_TTL = 43200
VERIFICATION_TTL_SECONDS = 90
BEARER = HTTPBearer(auto_error=False)


def make_token() -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"sub": USERNAME, "exp": int(time.time()) + TOKEN_TTL}).encode()
    ).rstrip(b"=").decode()
    signature = hmac.new(SECRET, payload.encode(), hashlib.sha256).hexdigest()
    return payload + "." + signature


def valid_token(token: str) -> bool:
    try:
        payload, signature = token.split(".", 1)
        expected = hmac.new(SECRET, payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return False
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return data["sub"] == USERNAME and data["exp"] > int(time.time())
    except Exception:
        return False


def admin(credentials: HTTPAuthorizationCredentials | None = Depends(BEARER)) -> str:
    if not credentials or credentials.scheme.lower() != "bearer" or not valid_token(credentials.credentials):
        raise HTTPException(401, "Vui lòng đăng nhập lại")
    return credentials.credentials


def device(token: str | None) -> None:
    if not token or not hmac.compare_digest(DEVICE_TOKEN, token):
        raise HTTPException(401, "Khóa thiết bị không hợp lệ")


def rows(sql: str, args: tuple = ()) -> list[dict]:
    with connect() as db:
        return [dict(row) for row in db.execute(sql, args).fetchall()]


def safe_base64(value: str, field_name: str, max_bytes: int) -> bytes:
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(422, f"{field_name} phải là Base64 hợp lệ") from exc
    if not raw or len(raw) > max_bytes:
        raise HTTPException(422, f"{field_name} không được rỗng hoặc vượt quá giới hạn")
    return raw


class Login(BaseModel):
    username: str
    password: str


class StudentUpdate(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    student_code: str = Field(min_length=3, max_length=30)
    class_name: str = Field(min_length=1, max_length=60)
    is_active: bool = True

    @field_validator("full_name", "student_code", "class_name")
    @classmethod
    def trim_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Trường này không được để trống")
        return value


class RegistrationCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    student_code: str = Field(min_length=3, max_length=30)
    class_name: str = Field(min_length=1, max_length=60)

    @field_validator("full_name", "student_code", "class_name")
    @classmethod
    def trim_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Trường này không được để trống")
        return value


class InventoryCardCreate(BaseModel):
    card_uid: str = Field(min_length=2, max_length=40)

    @field_validator("card_uid")
    @classmethod
    def validate_uid(cls, value: str) -> str:
        return normalize_uid(value)


class RegistrationCapture(BaseModel):
    event_id: str | None = Field(default=None, max_length=100)
    card_uid: str = Field(min_length=2, max_length=40)
    face_embedding: str = Field(min_length=4, max_length=1_000_000)
    embedding_dim: int = Field(default=512, ge=1, le=8192)
    model_name: str = Field(default="unspecified", max_length=100)
    model_version: str = Field(default="unspecified", max_length=100)
    face_image_base64: str = Field(min_length=4, max_length=8_000_000)
    image_mime: str = Field(default="image/jpeg", max_length=40)

    @field_validator("event_id")
    @classmethod
    def normalize_event_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("card_uid")
    @classmethod
    def validate_uid(cls, value: str) -> str:
        return normalize_uid(value)


class Face(BaseModel):
    face_id: str
    student_id: int
    face_embedding: str = Field(min_length=4, max_length=1_000_000)
    embedding_dim: int = 512
    model_name: str
    model_version: str
    is_active: bool = True

    @field_validator("face_embedding")
    @classmethod
    def validate_embedding(cls, value: str) -> str:
        safe_base64(value, "face_embedding", 750_000)
        return value


class Session(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    starts_at: str
    ends_at: str
    is_active: bool = True

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Tên buổi điểm danh không được để trống")
        return value

    @field_validator("starts_at", "ends_at")
    @classmethod
    def normalize_session_time(cls, value: str) -> str:
        try:
            return datetime_to_utc_iso(value)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


class VerificationStart(BaseModel):
    event_id: str = Field(min_length=1, max_length=100)
    card_uid: str = Field(min_length=2, max_length=40)
    session_id: int | None = None

    @field_validator("event_id")
    @classmethod
    def normalize_event_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("event_id không được để trống")
        return value

    @field_validator("card_uid")
    @classmethod
    def validate_uid(cls, value: str) -> str:
        return normalize_uid(value)


class VerificationComplete(BaseModel):
    event_id: str = Field(min_length=1, max_length=100)
    face_result: bool

    @field_validator("event_id")
    @classmethod
    def normalize_event_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("event_id không được để trống")
        return value


class Hub:
    def __init__(self):
        self.clients: set[WebSocket] = set()

    async def send(self, event: str, payload: dict | None = None) -> None:
        for websocket in list(self.clients):
            try:
                await websocket.send_json({"type": event, "data": payload or {}})
            except Exception:
                self.clients.discard(websocket)


hub = Hub()


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize()
    if DEMO_MODE:
        seed(include_scans=False)
    yield


app = FastAPI(title="Attenda Attendance API", version="4.0.0", lifespan=lifespan)


@app.get("/api/v1/health")
def health():
    with connect() as db:
        db.execute("SELECT 1")
        schema_version = db.execute("PRAGMA user_version").fetchone()[0]
    return {"status": "ok", "database": "SQLite", "schema_version": schema_version, "demo_mode": DEMO_MODE}


@app.post("/api/v1/auth/login")
def login(payload: Login):
    if not (hmac.compare_digest(payload.username, USERNAME) and hmac.compare_digest(payload.password, PASSWORD)):
        raise HTTPException(401, "Sai tài khoản hoặc mật khẩu")
    return {"access_token": make_token(), "token_type": "bearer", "expires_in": TOKEN_TTL, "username": USERNAME}


@app.get("/api/v1/config")
def config(_: str = Depends(admin)):
    return {
        "demo_mode": DEMO_MODE,
        "database": "SQLite",
        "api": "FastAPI",
        "transport": ["Wi-Fi"],
        "timezone": "Asia/Ho_Chi_Minh",
        "server_time": utc_now(),
    }


@app.get("/api/v1/students")
def get_students(_: str = Depends(admin)):
    return rows(
        """SELECT s.id,s.full_name,s.student_code,s.class_name,s.is_active,
                  c.uid AS card_uid,c.is_active AS card_active,
                  (SELECT MAX(e.received_at) FROM scan_events e WHERE e.student_id=s.id) AS last_scan_at,
                  EXISTS(SELECT 1 FROM face_templates f WHERE f.student_id=s.id AND f.is_active=1) AS has_face
           FROM students s
           LEFT JOIN nfc_cards c ON c.student_id=s.id AND c.is_active=1
           ORDER BY s.full_name"""
    )


@app.post("/api/v1/students", status_code=410)
def direct_student_creation_is_disabled(_: str = Depends(admin)):
    raise HTTPException(410, "Sinh viên mới phải được tạo qua hàng đợi đăng ký /api/v1/registrations")


@app.put("/api/v1/students/{student_id}")
async def edit_student(student_id: int, payload: StudentUpdate, _: str = Depends(admin)):
    try:
        with connect() as db:
            with db:
                previous = db.execute("SELECT is_active FROM students WHERE id=?", (student_id,)).fetchone()
                if not previous:
                    raise HTTPException(404, "Không tìm thấy sinh viên")
                db.execute(
                    "UPDATE students SET full_name=?,student_code=?,class_name=?,is_active=? WHERE id=?",
                    (payload.full_name.strip(), payload.student_code.strip(), payload.class_name.strip(), int(payload.is_active), student_id),
                )
                if not payload.is_active:
                    db.execute("UPDATE nfc_cards SET is_active=0 WHERE student_id=?", (student_id,))
                    db.execute("UPDATE face_templates SET is_active=0 WHERE student_id=?", (student_id,))
                elif not previous["is_active"]:
                    # Reactivate only the most recently registered card and latest face template.
                    latest_card = db.execute(
                        "SELECT id FROM nfc_cards WHERE student_id=? ORDER BY registered_at DESC,id DESC LIMIT 1",
                        (student_id,),
                    ).fetchone()
                    if latest_card:
                        db.execute("UPDATE nfc_cards SET is_active=0 WHERE student_id=?", (student_id,))
                        db.execute("UPDATE nfc_cards SET is_active=1 WHERE id=?", (latest_card["id"],))
                    latest_face = db.execute(
                        "SELECT id FROM face_templates WHERE student_id=? ORDER BY created_at DESC,id DESC LIMIT 1",
                        (student_id,),
                    ).fetchone()
                    if latest_face:
                        db.execute("UPDATE face_templates SET is_active=0 WHERE student_id=?", (student_id,))
                        db.execute("UPDATE face_templates SET is_active=1,updated_at=? WHERE id=?", (utc_now(), latest_face["id"]))
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "Mã sinh viên đã tồn tại") from exc
    await hub.send("students.changed")
    return {"id": student_id}


@app.delete("/api/v1/students/{student_id}")
async def disable_student(student_id: int, _: str = Depends(admin)):
    with connect() as db:
        with db:
            cursor = db.execute("UPDATE students SET is_active=0 WHERE id=?", (student_id,))
            if not cursor.rowcount:
                raise HTTPException(404, "Không tìm thấy sinh viên")
            db.execute("UPDATE nfc_cards SET is_active=0 WHERE student_id=?", (student_id,))
            db.execute("UPDATE face_templates SET is_active=0 WHERE student_id=?", (student_id,))
    await hub.send("students.changed")
    return {"message": "Đã vô hiệu hóa sinh viên"}


# ---------------------------------------------------------------------------
# NFC card inventory and new-student registration queue
# ---------------------------------------------------------------------------


@app.get("/api/v1/cards/inventory")
def get_card_inventory(_: str = Depends(admin)):
    return rows("SELECT id,uid,status,created_at,reserved_at,assigned_at FROM card_inventory ORDER BY id DESC")


@app.post("/api/v1/cards/inventory", status_code=201)
async def add_inventory_card(payload: InventoryCardCreate, _: str = Depends(admin)):
    uid = payload.card_uid
    try:
        with connect() as db:
            with db:
                if db.execute("SELECT 1 FROM nfc_cards WHERE uid=?", (uid,)).fetchone():
                    raise HTTPException(409, "UID này đã được cấp cho sinh viên")
                db.execute("INSERT INTO card_inventory(uid,status) VALUES(?,'available')", (uid,))
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "UID đã có trong kho thẻ") from exc
    await hub.send("cards.changed")
    return {"card_uid": uid, "status": "available"}


@app.delete("/api/v1/cards/inventory/{card_uid}")
async def delete_inventory_card(card_uid: str, _: str = Depends(admin)):
    try:
        uid = normalize_uid(card_uid)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    with connect() as db:
        with db:
            card = db.execute("SELECT status FROM card_inventory WHERE uid=?", (uid,)).fetchone()
            if not card or card["status"] != "available":
                raise HTTPException(409, "Chỉ có thể gỡ thẻ đang ở trạng thái Available")
            has_history = db.execute("SELECT 1 FROM registration_queue WHERE card_uid=? LIMIT 1", (uid,)).fetchone()
            if has_history:
                db.execute("UPDATE card_inventory SET status='disabled' WHERE uid=?", (uid,))
                result_status = "disabled"
            else:
                db.execute("DELETE FROM card_inventory WHERE uid=?", (uid,))
                result_status = "removed"
    await hub.send("cards.changed")
    return {"card_uid": uid, "status": result_status}


@app.post("/api/v1/registrations", status_code=201)
async def create_registration(payload: RegistrationCreate, _: str = Depends(admin)):
    student_code = payload.student_code.strip()
    registration_id = "REG-" + secrets.token_hex(4).upper()
    try:
        with connect() as db:
            with db:
                db.execute("BEGIN IMMEDIATE")
                if db.execute("SELECT 1 FROM students WHERE student_code=?", (student_code,)).fetchone():
                    raise HTTPException(409, "Mã sinh viên đã tồn tại trong danh sách chính thức")
                if db.execute(
                    "SELECT 1 FROM registration_queue WHERE student_code=? AND status IN ('waiting_for_scan','captured')",
                    (student_code,),
                ).fetchone():
                    raise HTTPException(409, "Mã sinh viên đang có hồ sơ đăng ký chờ xử lý")
                available = db.execute(
                    "SELECT uid FROM card_inventory WHERE status='available' ORDER BY id LIMIT 1"
                ).fetchone()
                if not available:
                    raise HTTPException(409, "Kho không còn thẻ Available. Hãy nhập UID thẻ trống trước.")
                card_uid = available["uid"]
                updated = db.execute(
                    "UPDATE card_inventory SET status='reserved',reservation_registration_id=?,reserved_at=? WHERE uid=? AND status='available'",
                    (registration_id, utc_now(), card_uid),
                )
                if not updated.rowcount:
                    raise HTTPException(409, "Thẻ vừa được cấp cho một hồ sơ khác; hãy thử lại")
                db.execute(
                    """INSERT INTO registration_queue(registration_id,student_code,full_name,class_name,card_uid,status)
                       VALUES(?,?,?,?,?,'waiting_for_scan')""",
                    (registration_id, student_code, payload.full_name.strip(), payload.class_name.strip(), card_uid),
                )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "Mã sinh viên hoặc thẻ đã được sử dụng trong một hồ sơ khác") from exc
    await hub.send("registrations.changed")
    await hub.send("cards.changed")
    return {"registration_id": registration_id, "card_uid": card_uid, "status": "waiting_for_scan"}


@app.get("/api/v1/registrations")
def get_registrations(include_closed: bool = False, _: str = Depends(admin)):
    condition = "" if include_closed else "WHERE q.status IN ('waiting_for_scan','captured')"
    return rows(
        f"""SELECT q.registration_id,q.student_code,q.full_name,q.class_name,q.card_uid,q.status,
                   q.created_at,q.captured_at,q.reviewed_at,q.rejection_reason,
                   CASE WHEN q.face_image IS NULL THEN 0 ELSE 1 END AS has_face_image
            FROM registration_queue q {condition}
            ORDER BY CASE q.status WHEN 'captured' THEN 0 ELSE 1 END,q.created_at"""
    )


@app.get("/api/v1/registrations/{registration_id}/image")
def get_registration_image(registration_id: str, _: str = Depends(admin)):
    with connect() as db:
        item = db.execute(
            "SELECT face_image,face_image_mime FROM registration_queue WHERE registration_id=?",
            (registration_id,),
        ).fetchone()
    if not item or not item["face_image"]:
        raise HTTPException(404, "Hồ sơ chưa có ảnh khuôn mặt")
    return Response(content=bytes(item["face_image"]), media_type=item["face_image_mime"] or "image/jpeg", headers={"Cache-Control": "no-store"})


@app.post("/api/v1/registrations/capture", status_code=201)
async def capture_registration(payload: RegistrationCapture, x_device_token: str | None = Header(default=None)):
    device(x_device_token)
    event_id = payload.event_id or ("ENROLL-" + secrets.token_hex(8).upper())
    embedding_bytes = safe_base64(payload.face_embedding, "face_embedding", 750_000)
    if len(embedding_bytes) % 4:
        raise HTTPException(422, "Embedding byte length phải chia hết cho 4")
    image_bytes = safe_base64(payload.face_image_base64, "face_image_base64", 5_000_000)
    allowed_mimes = {"image/jpeg", "image/png", "image/webp"}
    if payload.image_mime not in allowed_mimes:
        raise HTTPException(422, "Chỉ chấp nhận ảnh JPEG, PNG hoặc WebP")
    image_signatures = {
        "image/jpeg": image_bytes.startswith(b"\xff\xd8\xff"),
        "image/png": image_bytes.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": len(image_bytes) >= 12 and image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP",
    }
    if not image_signatures[payload.image_mime]:
        raise HTTPException(422, "Định dạng ảnh không khớp với image_mime")

    try:
        with connect() as db:
            with db:
                db.execute("BEGIN IMMEDIATE")
                existing = db.execute(
                    "SELECT registration_id,card_uid,status,capture_event_id FROM registration_queue WHERE capture_event_id=?",
                    (event_id,),
                ).fetchone()
                if existing:
                    if existing["card_uid"] != payload.card_uid:
                        raise HTTPException(409, "event_id đã được dùng với UID khác")
                    return {"created": False, "registration_id": existing["registration_id"], "status": existing["status"]}
                target = db.execute(
                    """SELECT q.registration_id,q.status FROM registration_queue q
                       JOIN card_inventory c ON c.uid=q.card_uid
                       WHERE q.card_uid=? AND c.status='reserved' AND c.reservation_registration_id=q.registration_id AND q.status='waiting_for_scan'""",
                    (payload.card_uid,),
                ).fetchone()
                if not target:
                    captured = db.execute(
                        """SELECT q.registration_id FROM registration_queue q
                           JOIN card_inventory c ON c.uid=q.card_uid
                           WHERE q.card_uid=? AND q.status='captured' AND c.status='reserved'
                             AND c.reservation_registration_id=q.registration_id""",
                        (payload.card_uid,),
                    ).fetchone()
                    if captured:
                        return {"created": False, "registration_id": captured["registration_id"], "status": "captured"}
                    raise HTTPException(404, "UID không có hồ sơ đăng ký đang chờ quét")
                db.execute(
                    """UPDATE registration_queue SET status='captured',face_embedding=?,embedding_dim=?,
                       model_name=?,model_version=?,face_image=?,face_image_mime=?,capture_event_id=?,captured_at=?
                       WHERE registration_id=?""",
                    (
                        payload.face_embedding,
                        payload.embedding_dim,
                        payload.model_name,
                        payload.model_version,
                        sqlite3.Binary(image_bytes),
                        payload.image_mime,
                        event_id,
                        utc_now(),
                        target["registration_id"],
                    ),
                )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "Dữ liệu thu thập bị trùng hoặc xung đột") from exc
    await hub.send("registrations.changed")
    return {"created": True, "registration_id": target["registration_id"], "status": "captured"}


@app.post("/api/v1/registrations/{registration_id}/approve")
async def approve_registration(registration_id: str, _: str = Depends(admin)):
    try:
        with connect() as db:
            with db:
                db.execute("BEGIN IMMEDIATE")
                item = db.execute("SELECT * FROM registration_queue WHERE registration_id=?", (registration_id,)).fetchone()
                if not item:
                    raise HTTPException(404, "Không tìm thấy hồ sơ đăng ký")
                if item["status"] != "captured" or not item["face_embedding"] or not item["face_image"]:
                    raise HTTPException(409, "Hồ sơ chưa có đủ UID, embedding và ảnh khuôn mặt")
                if db.execute("SELECT 1 FROM students WHERE student_code=?", (item["student_code"],)).fetchone():
                    raise HTTPException(409, "Mã sinh viên đã tồn tại trong danh sách chính thức")
                reserved_card = db.execute(
                    "SELECT 1 FROM card_inventory WHERE uid=? AND status='reserved' AND reservation_registration_id=?",
                    (item["card_uid"], registration_id),
                ).fetchone()
                if not reserved_card:
                    raise HTTPException(409, "Thẻ không còn được giữ chỗ cho hồ sơ này")
                student_id = db.execute(
                    "INSERT INTO students(full_name,student_code,class_name,is_active) VALUES(?,?,?,1)",
                    (item["full_name"], item["student_code"], item["class_name"]),
                ).lastrowid
                db.execute("INSERT INTO nfc_cards(uid,student_id,card_type,is_active) VALUES(?,?,?,1)", (item["card_uid"], student_id, "ISO14443-A"))
                db.execute(
                    """INSERT INTO face_templates(face_id,student_id,face_embedding,embedding_dim,model_name,model_version,is_active)
                       VALUES(?,?,?,?,?,?,1)""",
                    ("FACE-" + registration_id, student_id, item["face_embedding"], item["embedding_dim"], item["model_name"], item["model_version"]),
                )
                db.execute(
                    "UPDATE card_inventory SET status='assigned',assigned_at=?,reservation_registration_id=NULL WHERE uid=? AND status='reserved' AND reservation_registration_id=?",
                    (utc_now(), item["card_uid"], registration_id),
                )
                db.execute("UPDATE registration_queue SET status='approved',reviewed_at=? WHERE registration_id=?", (utc_now(), registration_id))
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "Không thể duyệt hồ sơ do trùng mã sinh viên, UID hoặc face_id") from exc
    await hub.send("registrations.changed")
    await hub.send("students.changed")
    await hub.send("cards.changed")
    return {"registration_id": registration_id, "student_id": student_id, "status": "approved"}


@app.post("/api/v1/registrations/{registration_id}/reject")
async def reject_registration(registration_id: str, _: str = Depends(admin)):
    with connect() as db:
        with db:
            item = db.execute("SELECT card_uid,status FROM registration_queue WHERE registration_id=?", (registration_id,)).fetchone()
            if not item:
                raise HTTPException(404, "Không tìm thấy hồ sơ đăng ký")
            if item["status"] == "approved":
                raise HTTPException(409, "Hồ sơ đã duyệt không thể từ chối")
            db.execute(
                "UPDATE registration_queue SET status='rejected',reviewed_at=?,face_embedding=NULL,face_image=NULL,face_image_mime=NULL WHERE registration_id=?",
                (utc_now(), registration_id),
            )
            db.execute(
                "UPDATE card_inventory SET status='available',reservation_registration_id=NULL,reserved_at=NULL WHERE uid=? AND status='reserved' AND reservation_registration_id=?",
                (item["card_uid"], registration_id),
            )
    await hub.send("registrations.changed")
    await hub.send("cards.changed")
    return {"registration_id": registration_id, "status": "rejected"}


@app.post("/api/v1/registrations/{registration_id}/retry")
async def retry_registration_capture(registration_id: str, _: str = Depends(admin)):
    with connect() as db:
        with db:
            item = db.execute("SELECT card_uid,status FROM registration_queue WHERE registration_id=?", (registration_id,)).fetchone()
            if not item:
                raise HTTPException(404, "Không tìm thấy hồ sơ đăng ký")
            if item["status"] != "captured":
                raise HTTPException(409, "Chỉ hồ sơ đã thu thập mới có thể yêu cầu quét lại")
            db.execute(
                """UPDATE registration_queue SET status='waiting_for_scan',face_embedding=NULL,embedding_dim=NULL,
                   model_name=NULL,model_version=NULL,face_image=NULL,face_image_mime=NULL,capture_event_id=NULL,captured_at=NULL
                   WHERE registration_id=?""",
                (registration_id,),
            )
    await hub.send("registrations.changed")
    return {"registration_id": registration_id, "status": "waiting_for_scan"}


# ---------------------------------------------------------------------------
# Attendance verification: NFC check first, face result second
# ---------------------------------------------------------------------------


def expire_stale_verifications() -> None:
    now_text = utc_now()
    now_dt = datetime.now(timezone.utc)
    with connect() as db:
        with db:
            pending = db.execute(
                "SELECT event_id,session_id,expires_at FROM verification_attempts WHERE status='pending'"
            ).fetchall()
            for attempt in pending:
                session = db.execute(
                    "SELECT * FROM attendance_sessions WHERE id=?", (attempt["session_id"],)
                ).fetchone() if attempt["session_id"] is not None else None
                expired = attempt["expires_at"] < now_text or not session or not session_is_open(session, now_dt)
                if expired:
                    db.execute(
                        "UPDATE verification_attempts SET status='expired',completed_at=? WHERE event_id=? AND status='pending'",
                        (now_text, attempt["event_id"]),
                    )


def resolve_session(db: sqlite3.Connection, session_id: int | None) -> int:
    """Resolve exactly one session that is explicitly active and inside its time window."""
    now = datetime.now(timezone.utc)
    if session_id is not None:
        session = db.execute("SELECT * FROM attendance_sessions WHERE id=?", (session_id,)).fetchone()
        if not session or not session_is_open(session, now):
            raise HTTPException(409, "Buổi điểm danh chưa bắt đầu, đã kết thúc hoặc đã bị đóng")
        return session_id

    candidates = db.execute("SELECT * FROM attendance_sessions WHERE is_active=1 ORDER BY id DESC").fetchall()
    active = [session for session in candidates if session_is_open(session, now)]
    if not active:
        raise HTTPException(409, "Hiện không có buổi điểm danh nào đang diễn ra")
    if len(active) > 1:
        raise HTTPException(409, "Có nhiều buổi điểm danh đang diễn ra; thiết bị cần gửi session_id")
    return active[0]["id"]


def start_failure(db: sqlite3.Connection, payload: VerificationStart, status: str, card_id=None, student_id=None, session_id=None):
    now = utc_now()
    db.execute(
        """INSERT INTO verification_attempts(event_id,card_uid,card_id,student_id,session_id,status,expires_at,completed_at)
           VALUES(?,?,?,?,?,?,?,?)""",
        (payload.event_id, payload.card_uid, card_id, student_id, session_id, status, now, now),
    )


@app.post("/api/v1/verification/start")
async def start_verification(payload: VerificationStart, x_device_token: str | None = Header(default=None)):
    device(x_device_token)
    with connect() as db:
        with db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE verification_attempts SET status='expired',completed_at=? WHERE status='pending' AND expires_at<?", (utc_now(), utc_now()))
            previous = db.execute("SELECT * FROM verification_attempts WHERE event_id=?", (payload.event_id,)).fetchone()
            if previous:
                if previous["card_uid"] != payload.card_uid:
                    raise HTTPException(409, "event_id đã được sử dụng với UID khác")
                if previous["status"] == "pending" and previous["expires_at"] >= utc_now():
                    previous_session = db.execute(
                        "SELECT * FROM attendance_sessions WHERE id=?", (previous["session_id"],)
                    ).fetchone() if previous["session_id"] is not None else None
                    if not previous_session or not session_is_open(previous_session):
                        db.execute(
                            "UPDATE verification_attempts SET status='expired',completed_at=? WHERE event_id=?",
                            (utc_now(), payload.event_id),
                        )
                        return {"event_id": payload.event_id, "status": "expired", "created": False}
                    template = db.execute("SELECT face_embedding,embedding_dim,model_name,model_version FROM face_templates WHERE id=? AND is_active=1", (previous["face_template_id"],)).fetchone()
                    if template:
                        return {"event_id": payload.event_id, "status": "pending", "student_id": previous["student_id"], "face_embedding": template["face_embedding"], "embedding_dim": template["embedding_dim"], "model_name": template["model_name"], "model_version": template["model_version"], "expires_at": previous["expires_at"]}
                return {"event_id": payload.event_id, "status": previous["status"], "created": False}

            # event_id must be globally fresh across verification attempts and legacy scan history.
            previous_scan = db.execute("SELECT card_uid FROM scan_events WHERE event_id=?", (payload.event_id,)).fetchone()
            if previous_scan:
                raise HTTPException(409, "event_id đã tồn tại trong lịch sử quét; thiết bị phải tạo mã mới")

            session_id = resolve_session(db, payload.session_id)
            card = db.execute(
                """SELECT c.id AS card_id,c.student_id,c.is_active AS card_active,s.is_active AS student_active
                   FROM nfc_cards c JOIN students s ON s.id=c.student_id WHERE c.uid=?""",
                (payload.card_uid,),
            ).fetchone()
            if not card:
                start_failure(db, payload, "unregistered", session_id=session_id)
                status = "unregistered"
            elif not card["card_active"] or not card["student_active"]:
                start_failure(db, payload, "inactive_card", card["card_id"], card["student_id"], session_id)
                status = "inactive_card"
            else:
                template = db.execute(
                    "SELECT id,face_embedding,embedding_dim,model_name,model_version FROM face_templates WHERE student_id=? AND is_active=1 ORDER BY created_at DESC LIMIT 1",
                    (card["student_id"],),
                ).fetchone()
                if not template:
                    start_failure(db, payload, "no_face_template", card["card_id"], card["student_id"], session_id)
                    status = "no_face_template"
                else:
                    expires = (datetime.now(timezone.utc) + timedelta(seconds=VERIFICATION_TTL_SECONDS)).isoformat(timespec="seconds").replace("+00:00", "Z")
                    db.execute(
                        """INSERT INTO verification_attempts(event_id,card_uid,card_id,student_id,face_template_id,session_id,status,expires_at)
                           VALUES(?,?,?,?,?,?, 'pending', ?)""",
                        (payload.event_id, payload.card_uid, card["card_id"], card["student_id"], template["id"], session_id, expires),
                    )
                    return {
                        "event_id": payload.event_id,
                        "status": "pending",
                        "student_id": card["student_id"],
                        "face_embedding": template["face_embedding"],
                        "embedding_dim": template["embedding_dim"],
                        "model_name": template["model_name"],
                        "model_version": template["model_version"],
                        "expires_at": expires,
                    }
    await hub.send("scan.created", {"event_id": payload.event_id, "status": status})
    return {"event_id": payload.event_id, "status": status, "created": True}


@app.post("/api/v1/verification/complete")
async def complete_verification(payload: VerificationComplete, x_device_token: str | None = Header(default=None)):
    device(x_device_token)
    with connect() as db:
        with db:
            db.execute("BEGIN IMMEDIATE")
            attempt = db.execute("SELECT * FROM verification_attempts WHERE event_id=?", (payload.event_id,)).fetchone()
            if not attempt:
                raise HTTPException(404, "Không tìm thấy lượt xác minh NFC tương ứng")
            if attempt["status"] != "pending":
                return {"event_id": payload.event_id, "status": attempt["status"], "created": False}
            now = utc_now()
            session = db.execute("SELECT * FROM attendance_sessions WHERE id=?", (attempt["session_id"],)).fetchone() if attempt["session_id"] is not None else None
            if attempt["expires_at"] < now or not session or not session_is_open(session):
                db.execute("UPDATE verification_attempts SET status='expired',completed_at=? WHERE event_id=?", (now, payload.event_id))
                status = "expired"
                created = False
            elif not payload.face_result:
                db.execute("UPDATE verification_attempts SET status='face_mismatch',face_result=0,completed_at=? WHERE event_id=?", (now, payload.event_id))
                status = "face_mismatch"
                created = False
            else:
                valid = db.execute(
                    """SELECT 1 FROM nfc_cards c JOIN students s ON s.id=c.student_id
                       JOIN face_templates f ON f.id=? AND f.student_id=s.id
                       WHERE c.id=? AND c.uid=? AND c.is_active=1 AND s.is_active=1 AND f.is_active=1""",
                    (attempt["face_template_id"], attempt["card_id"], attempt["card_uid"]),
                ).fetchone()
                if not valid:
                    db.execute("UPDATE verification_attempts SET status='inactive_card',face_result=1,completed_at=? WHERE event_id=?", (now, payload.event_id))
                    status = "inactive_card"
                    created = False
                else:
                    scan, created = record_scan(db, payload.event_id, attempt["card_uid"], attempt["session_id"])
                    if not created:
                        raise HTTPException(409, "event_id đã được sử dụng trong lịch sử quét; không thể ghi nhận lần xác minh mới")
                    if scan["result"] == "recognized":
                        db.execute(
                            "UPDATE verification_attempts SET status='verified',face_result=1,scan_event_id=?,completed_at=? WHERE event_id=?",
                            (db.execute("SELECT id FROM scan_events WHERE event_id=?", (payload.event_id,)).fetchone()["id"], now, payload.event_id),
                        )
                        status = "verified"
                    else:
                        status = scan["result"]
                        db.execute("UPDATE verification_attempts SET status=?,face_result=1,completed_at=? WHERE event_id=?", (status, now, payload.event_id))
    await hub.send("scan.created", {"event_id": payload.event_id, "status": status})
    if status == "verified":
        await hub.send("attendance.changed", {"event_id": payload.event_id})
    return {"event_id": payload.event_id, "status": status, "created": created}


@app.post("/api/v1/scans", status_code=410)
def direct_nfc_attendance_is_disabled(x_device_token: str | None = Header(default=None)):
    device(x_device_token)
    raise HTTPException(410, "Quy trình mới yêu cầu /verification/start và /verification/complete; không ghi điểm danh chỉ bằng UID NFC")


@app.get("/api/v1/scans")
def get_scans(limit: int = Query(100, ge=1, le=500), _: str = Depends(admin)):
    expire_stale_verifications()
    return rows(
        """SELECT * FROM (
             SELECT -a.id AS id,a.event_id,a.card_uid,
                    CASE WHEN a.status='verified' THEN 'recognized' ELSE a.status END AS result,
                    s.student_code,s.full_name,s.class_name,a.started_at AS occurred_at,a.started_at AS received_at
             FROM verification_attempts a LEFT JOIN students s ON s.id=a.student_id
             UNION ALL
             SELECT 1000000+e.id AS id,e.event_id,e.card_uid,
                    CASE WHEN e.result='recognized' THEN 'legacy_nfc_only' ELSE e.result END AS result,
                    s.student_code,s.full_name,s.class_name,e.occurred_at,e.received_at
             FROM scan_events e LEFT JOIN students s ON s.id=e.student_id
             WHERE NOT EXISTS(SELECT 1 FROM verification_attempts a WHERE a.event_id=e.event_id)
           ) ORDER BY received_at DESC LIMIT ?""",
        (limit,),
    )


@app.get("/api/v1/stats")
def get_stats(_: str = Depends(admin)):
    expire_stale_verifications()
    today = datetime.now(VN_TZ).date().isoformat()
    with connect() as db:
        total_students = db.execute("SELECT COUNT(*) FROM students WHERE is_active=1").fetchone()[0]
        attempt_counts = db.execute(
            "SELECT COUNT(*) AS total,SUM(CASE WHEN status='verified' THEN 1 ELSE 0 END) AS verified FROM verification_attempts WHERE date(started_at,'+7 hours')=?",
            (today,),
        ).fetchone()
        legacy_counts = db.execute(
            """SELECT COUNT(*) AS total,0 AS verified
               FROM scan_events e WHERE date(e.received_at,'+7 hours')=?
               AND NOT EXISTS(SELECT 1 FROM verification_attempts a WHERE a.event_id=e.event_id)""",
            (today,),
        ).fetchone()
        face_count = db.execute("SELECT COUNT(*) FROM face_templates WHERE is_active=1").fetchone()[0]
    total_scans = (attempt_counts["total"] or 0) + (legacy_counts["total"] or 0)
    recognized = (attempt_counts["verified"] or 0) + (legacy_counts["verified"] or 0)
    return {
        "students": total_students,
        "scans_today": total_scans,
        "recognized_today": recognized,
        "flagged_today": total_scans - recognized,
        "registered_rate": round(recognized * 100 / total_scans, 1) if total_scans else 0,
        "face_templates": face_count,
        "server_time": utc_now(),
    }


@app.get("/api/v1/faces")
def get_faces(_: str = Depends(admin)):
    return rows(
        """SELECT f.id,f.face_id,f.student_id,s.full_name,s.student_code,f.embedding_dim,
                  f.model_name,f.model_version,f.is_active,f.created_at
           FROM face_templates f JOIN students s ON s.id=f.student_id ORDER BY f.created_at DESC"""
    )


@app.post("/api/v1/faces", status_code=201)
async def add_face(payload: Face, _: str = Depends(admin)):
    embedding = safe_base64(payload.face_embedding, "face_embedding", 750_000)
    if len(embedding) % 4:
        raise HTTPException(422, "Embedding byte length phải chia hết cho 4")
    try:
        with connect() as db:
            with db:
                if not db.execute("SELECT 1 FROM students WHERE id=? AND is_active=1", (payload.student_id,)).fetchone():
                    raise HTTPException(404, "Sinh viên không tồn tại/đã khóa")
                face_id = db.execute(
                    """INSERT INTO face_templates(face_id,student_id,face_embedding,embedding_dim,model_name,model_version,is_active)
                       VALUES(?,?,?,?,?,?,?)""",
                    (payload.face_id, payload.student_id, payload.face_embedding, payload.embedding_dim, payload.model_name, payload.model_version, int(payload.is_active)),
                ).lastrowid
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "face_id đã tồn tại") from exc
    await hub.send("faces.changed")
    return {"id": face_id}


@app.delete("/api/v1/faces/{face_id}")
async def disable_face(face_id: int, _: str = Depends(admin)):
    with connect() as db:
        with db:
            cursor = db.execute("UPDATE face_templates SET is_active=0,updated_at=? WHERE id=?", (utc_now(), face_id))
            if not cursor.rowcount:
                raise HTTPException(404, "Không tìm thấy mẫu khuôn mặt")
    await hub.send("faces.changed")
    return {"message": "Đã vô hiệu hóa mẫu khuôn mặt"}


@app.get("/api/v1/sessions")
def get_sessions(_: str = Depends(admin)):
    return rows("SELECT * FROM attendance_sessions ORDER BY starts_at DESC")


@app.post("/api/v1/sessions", status_code=201)
def add_session(payload: Session, _: str = Depends(admin)):
    if parse_datetime_utc(payload.ends_at) <= parse_datetime_utc(payload.starts_at):
        raise HTTPException(400, "Thời gian kết thúc phải sau thời gian bắt đầu")
    with connect() as db:
        with db:
            session_id = db.execute(
                "INSERT INTO attendance_sessions(title,starts_at,ends_at,is_active) VALUES(?,?,?,?)",
                (payload.title, payload.starts_at, payload.ends_at, int(payload.is_active)),
            ).lastrowid
    return {"id": session_id}


@app.get("/api/v1/attendance")
def get_attendance(session_id: int | None = None, _: str = Depends(admin)):
    sql = "SELECT r.*,s.full_name,s.student_code,s.class_name FROM attendance_records r JOIN students s ON s.id=r.student_id"
    return rows(sql + (" WHERE r.session_id=?" if session_id is not None else "") + " ORDER BY r.marked_at DESC", ((session_id,) if session_id is not None else ()))


@app.websocket("/ws/events")
async def ws_events(websocket: WebSocket):
    await websocket.accept()
    try:
        message = await asyncio.wait_for(websocket.receive_json(), timeout=6)
        if message.get("type") != "auth" or not valid_token(str(message.get("token", ""))):
            await websocket.close(code=1008)
            return
        hub.clients.add(websocket)
        await websocket.send_json({"type": "ready", "data": {}})
        while True:
            await websocket.receive_text()
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    finally:
        hub.clients.discard(websocket)


@app.get("/", include_in_schema=False)
def home():
    index = WEB_DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return HTMLResponse("<h2>Attenda API is running</h2><p>Build frontend with npm.cmd install && npm.cmd run build.</p><a href='/docs'>API docs</a>")


if (WEB_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if path.startswith(("api/", "ws/")):
        raise HTTPException(404, "Not found")
    target = (WEB_DIST / path).resolve()
    if WEB_DIST.exists() and target.is_relative_to(WEB_DIST.resolve()) and target.is_file():
        return FileResponse(target)
    if (WEB_DIST / "index.html").exists():
        return FileResponse(WEB_DIST / "index.html")
    raise HTTPException(404, "Frontend chưa build")

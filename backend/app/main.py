from __future__ import annotations
import asyncio, base64, binascii, hashlib, hmac, json, os, time, sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from database.db import connect, initialize, normalize_uid, record_scan, utc_now
from database.seed import seed

# Vietnam uses UTC+07:00 year-round; fixed offset avoids Windows tzdata dependency.
VN_TZ=timezone(timedelta(hours=7), name='Asia/Ho_Chi_Minh')

ROOT=Path(__file__).resolve().parents[2]
load_dotenv(ROOT/'.env',override=False)
WEB_DIST=ROOT/'frontend'/'dist'
DEMO_MODE=os.getenv('DEMO_MODE','true').lower() in ('1','true','yes')
USERNAME=os.getenv('ADMIN_USERNAME','admin')
PASSWORD=os.getenv('ADMIN_PASSWORD','attenda123')
SECRET=os.getenv('APP_SECRET','dev-only-change-before-LAN').encode()
DEVICE_TOKEN=os.getenv('DEVICE_TOKEN','demo-device-token-change-me')
BEARER=HTTPBearer(auto_error=False)
TOKEN_TTL=43200

def make_token():
    payload=base64.urlsafe_b64encode(json.dumps({'sub':USERNAME,'exp':int(time.time())+TOKEN_TTL}).encode()).rstrip(b'=').decode()
    return payload+'.'+hmac.new(SECRET,payload.encode(),hashlib.sha256).hexdigest()
def valid_token(token):
    try:
        p,s=token.split('.',1)
        if not hmac.compare_digest(s,hmac.new(SECRET,p.encode(),hashlib.sha256).hexdigest()): return False
        d=json.loads(base64.urlsafe_b64decode(p+'='*(-len(p)%4)))
        return d['sub']==USERNAME and d['exp']>int(time.time())
    except Exception: return False
def admin(c:HTTPAuthorizationCredentials|None=Depends(BEARER)):
    if not c or c.scheme.lower()!='bearer' or not valid_token(c.credentials): raise HTTPException(401,'Vui lòng đăng nhập lại')
    return c.credentials
def device(t:str|None):
    if not t or not hmac.compare_digest(DEVICE_TOKEN,t): raise HTTPException(401,'Khóa thiết bị không hợp lệ')
def rows(sql,args=()):
    with connect() as db: return [dict(r) for r in db.execute(sql,args).fetchall()]

class Login(BaseModel):
    username:str
    password:str
class Student(BaseModel):
    full_name:str=Field(min_length=2,max_length=120)
    student_code:str=Field(min_length=3,max_length=30)
    class_name:str=Field(min_length=1,max_length=60)
    card_uid:str|None=None
    is_active:bool=True
    @field_validator('card_uid')
    @classmethod
    def uid(cls,v): return normalize_uid(v) if v and v.strip() else None
class Scan(BaseModel):
    event_id:str=Field(min_length=1,max_length=100)
    card_uid:str=Field(min_length=2,max_length=40)
    session_id:int|None=None
    @field_validator('card_uid')
    @classmethod
    def uid(cls,v): return normalize_uid(v)
class Face(BaseModel):
    face_id:str
    student_id:int
    face_embedding:str=Field(min_length=4,max_length=100000)
    embedding_dim:int=512
    model_name:str
    model_version:str
    is_active:bool=True
    @field_validator('face_embedding')
    @classmethod
    def b64(cls,v):
        try: base64.b64decode(v,validate=True)
        except (binascii.Error,ValueError): raise ValueError('face_embedding phải là Base64 hợp lệ')
        return v
class Session(BaseModel):
    title:str
    starts_at:str
    ends_at:str
    is_active:bool=True

class Hub:
    def __init__(self): self.clients=set()
    async def send(self,event,payload=None):
        for ws in list(self.clients):
            try: await ws.send_json({'type':event,'data':payload or {}})
            except Exception: self.clients.discard(ws)
hub=Hub()
@asynccontextmanager
async def lifespan(app):
    initialize()
    if DEMO_MODE: seed(include_scans=False) ### true
    yield
app=FastAPI(title='Attenda Attendance API',version='2.0.0',lifespan=lifespan)

@app.get('/api/v1/health')
def health():
    with connect() as db: db.execute('SELECT 1')
    return {'status':'ok','database':'SQLite','schema_version':2,'demo_mode':DEMO_MODE}
@app.post('/api/v1/auth/login')
def login(x:Login):
    if not (hmac.compare_digest(x.username,USERNAME) and hmac.compare_digest(x.password,PASSWORD)): raise HTTPException(401,'Sai tài khoản hoặc mật khẩu')
    return {'access_token':make_token(),'token_type':'bearer','expires_in':TOKEN_TTL,'username':USERNAME}
@app.get('/api/v1/config')
def config(_:str=Depends(admin)):
    return {'demo_mode':DEMO_MODE,'database':'SQLite','api':'FastAPI','transport':['Wi-Fi'],'timezone':'Asia/Ho_Chi_Minh','server_time':utc_now()}

def student_write(db,sid,x):
    if sid is None:
        sid=db.execute('INSERT INTO students(full_name,student_code,class_name,is_active) VALUES(?,?,?,?)',(x.full_name.strip(),x.student_code.strip(),x.class_name.strip(),int(x.is_active))).lastrowid
    else:
        if not db.execute('SELECT 1 FROM students WHERE id=?',(sid,)).fetchone(): raise HTTPException(404,'Không tìm thấy sinh viên')
        db.execute('UPDATE students SET full_name=?,student_code=?,class_name=?,is_active=? WHERE id=?',(x.full_name.strip(),x.student_code.strip(),x.class_name.strip(),int(x.is_active),sid))
    current=db.execute('SELECT id,uid FROM nfc_cards WHERE student_id=? AND is_active=1',(sid,)).fetchone()
    if x.card_uid!=(current['uid'] if current else None):
        db.execute('UPDATE nfc_cards SET is_active=0 WHERE student_id=? AND is_active=1',(sid,))
        if x.card_uid:
            found=db.execute('SELECT id,student_id FROM nfc_cards WHERE uid=?',(x.card_uid,)).fetchone()
            if found and found['student_id']!=sid: raise HTTPException(409,'UID đã thuộc sinh viên khác')
            if found: db.execute('UPDATE nfc_cards SET is_active=1 WHERE id=?',(found['id'],))
            else: db.execute('INSERT INTO nfc_cards(uid,student_id) VALUES(?,?)',(x.card_uid,sid))
    if not x.is_active:
        db.execute('UPDATE nfc_cards SET is_active=0 WHERE student_id=?',(sid,))
        db.execute('UPDATE face_templates SET is_active=0 WHERE student_id=?',(sid,))
    return sid

@app.get('/api/v1/students')
def get_students(_:str=Depends(admin)):
    return [dict(r, email=None, last_station_id=None) for r in rows('''SELECT s.id,s.full_name,s.student_code,s.class_name,s.is_active,c.uid AS card_uid,c.is_active AS card_active,
      (SELECT MAX(received_at) FROM scan_events e WHERE e.student_id=s.id) AS last_scan_at,
      EXISTS(SELECT 1 FROM face_templates f WHERE f.student_id=s.id AND f.is_active=1) AS has_face
      FROM students s LEFT JOIN nfc_cards c ON c.student_id=s.id AND c.is_active=1 ORDER BY s.full_name''')]
@app.post('/api/v1/students',status_code=201)
async def add_student(x:Student,_:str=Depends(admin)):
    try:
        with connect() as db:
            with db: sid=student_write(db,None,x)
    except sqlite3.IntegrityError as e: raise HTTPException(409,'MSSV hoặc UID đã tồn tại') from e
    await hub.send('students.changed'); return {'id':sid}
@app.put('/api/v1/students/{sid}')
async def edit_student(sid:int,x:Student,_:str=Depends(admin)):
    try:
        with connect() as db:
            with db: student_write(db,sid,x)
    except sqlite3.IntegrityError as e: raise HTTPException(409,'MSSV hoặc UID đã tồn tại') from e
    await hub.send('students.changed'); return {'id':sid}
@app.delete('/api/v1/students/{sid}')
async def delete_student(sid:int,_:str=Depends(admin)):
    with connect() as db:
        with db:
            cur=db.execute('UPDATE students SET is_active=0 WHERE id=?',(sid,))
            if not cur.rowcount: raise HTTPException(404,'Không tìm thấy sinh viên')
            db.execute('UPDATE nfc_cards SET is_active=0 WHERE student_id=?',(sid,))
            db.execute('UPDATE face_templates SET is_active=0 WHERE student_id=?',(sid,))
    await hub.send('students.changed'); return {'message':'Đã vô hiệu hóa sinh viên'}

async def scan_save(x):
    try:
        with connect() as db:
            with db:
                session_id=x.session_id
                if session_id is None:
                    active=db.execute('SELECT id FROM attendance_sessions WHERE is_active=1 ORDER BY id DESC LIMIT 2').fetchall()
                    if len(active)==1: session_id=active[0]['id']
                result,created=record_scan(db,x.event_id,x.card_uid,session_id)
    except ValueError as e: raise HTTPException(409 if 'event_id' in str(e) else 400,str(e)) from e
    except sqlite3.IntegrityError as e: raise HTTPException(409,'Dữ liệu quét xung đột') from e
    if created: await hub.send('scan.created',{'event_id':x.event_id})
    return {'created':created,'event_id':x.event_id,'result':result['result'],'scan':result}
@app.post('/api/v1/scans',status_code=201)
async def ingest(x:Scan,x_device_token:str|None=Header(default=None)):
    device(x_device_token); return await scan_save(x)

@app.get('/api/v1/stations')
def get_legacy_stations(_:str=Depends(admin)):
    # Compatibility for the original dashboard bundle. Station entities were
    # removed from schema v2; device heartbeat is not persisted as a station.
    return []

@app.get('/api/v1/scans')
def get_scans(limit:int=Query(100,ge=1,le=500),_:str=Depends(admin)):
    return [dict(r, station_id='LOCAL_GATEWAY', station_name='Thiết bị NFC', station_location='Cổng điểm danh') for r in rows('SELECT e.id, v.* FROM v_recent_scans v JOIN scan_events e ON e.event_id=v.event_id ORDER BY v.received_at DESC LIMIT ?',(limit,))]
@app.get('/api/v1/stats')
def get_stats(_:str=Depends(admin)):
    today=datetime.now(VN_TZ).date().isoformat()
    with connect() as db:
        n=db.execute('SELECT COUNT(*) FROM students WHERE is_active=1').fetchone()[0]
        scans=db.execute('SELECT COUNT(*) FROM scan_events WHERE substr(received_at,1,10)=?',(today,)).fetchone()[0]
        ok=db.execute("SELECT COUNT(*) FROM scan_events WHERE result='recognized' AND substr(received_at,1,10)=?",(today,)).fetchone()[0]
        faces=db.execute('SELECT COUNT(*) FROM face_templates WHERE is_active=1').fetchone()[0]
    return {'students':n,'scans_today':scans,'recognized_today':ok,'flagged_today':scans-ok,'registered_rate':round(ok*100/scans,1) if scans else 0,'face_templates':faces,'stations_online':0,'stations_total':0,'server_time':utc_now()}

@app.get('/api/v1/faces')
def get_faces(_:str=Depends(admin)):
    return rows('''SELECT f.id,f.face_id,f.student_id,s.full_name,s.student_code,f.embedding_dim,f.model_name,f.model_version,f.is_active,f.created_at
      FROM face_templates f JOIN students s ON s.id=f.student_id ORDER BY f.created_at DESC''')
@app.post('/api/v1/faces',status_code=201)
async def add_face(x:Face,_:str=Depends(admin)):
    try: raw=base64.b64decode(x.face_embedding,validate=True)
    except Exception: raise HTTPException(422,'Base64 không hợp lệ')
    if len(raw)%4: raise HTTPException(422,'Embedding byte length phải chia hết cho 4')
    try:
        with connect() as db:
            with db:
                if not db.execute('SELECT 1 FROM students WHERE id=? AND is_active=1',(x.student_id,)).fetchone(): raise HTTPException(404,'Sinh viên không tồn tại/đã khóa')
                fid=db.execute('''INSERT INTO face_templates(face_id,student_id,face_embedding,embedding_dim,model_name,model_version,is_active)
                  VALUES(?,?,?,?,?,?,?)''',(x.face_id,x.student_id,x.face_embedding,x.embedding_dim,x.model_name,x.model_version,int(x.is_active))).lastrowid
    except sqlite3.IntegrityError as e: raise HTTPException(409,'face_id đã tồn tại') from e
    await hub.send('faces.changed'); return {'id':fid}
@app.delete('/api/v1/faces/{fid}')
async def disable_face(fid:int,_:str=Depends(admin)):
    with connect() as db:
        with db:
            cur=db.execute('UPDATE face_templates SET is_active=0,updated_at=? WHERE id=?',(utc_now(),fid))
            if not cur.rowcount: raise HTTPException(404,'Không tìm thấy mẫu khuôn mặt')
    return {'message':'Đã vô hiệu hóa mẫu khuôn mặt'}

@app.get('/api/v1/sessions')
def get_sessions(_:str=Depends(admin)): return rows('SELECT * FROM attendance_sessions ORDER BY starts_at DESC')
@app.post('/api/v1/sessions',status_code=201)
def add_session(x:Session,_:str=Depends(admin)):
    if x.ends_at<=x.starts_at: raise HTTPException(400,'Thời gian kết thúc phải sau thời gian bắt đầu')
    with connect() as db:
        with db: sid=db.execute('INSERT INTO attendance_sessions(title,starts_at,ends_at,is_active) VALUES(?,?,?,?)',(x.title,x.starts_at,x.ends_at,int(x.is_active))).lastrowid
    return {'id':sid}
@app.get('/api/v1/attendance')
def get_attendance(session_id:int|None=None,_:str=Depends(admin)):
    sql='SELECT r.*,s.full_name,s.student_code,s.class_name FROM attendance_records r JOIN students s ON s.id=r.student_id'
    return rows(sql+(' WHERE r.session_id=?' if session_id else '')+' ORDER BY r.marked_at DESC',((session_id,) if session_id else ()))

@app.websocket('/ws/events')
async def ws_events(ws:WebSocket):
    await ws.accept()
    try:
        msg=await asyncio.wait_for(ws.receive_json(),timeout=6)
        if msg.get('type')!='auth' or not valid_token(str(msg.get('token',''))): await ws.close(code=1008); return
        hub.clients.add(ws); await ws.send_json({'type':'ready','data':{}})
        while True: await ws.receive_text()
    except (WebSocketDisconnect,asyncio.TimeoutError): pass
    finally: hub.clients.discard(ws)

@app.get('/',include_in_schema=False)
def home():
    p=WEB_DIST/'index.html'
    if p.exists(): return FileResponse(p)
    return HTMLResponse('<h2>Attenda API is running</h2><p>Build frontend with npm.cmd install && npm.cmd run build.</p><a href="/docs">API docs</a>')
if (WEB_DIST/'assets').exists(): app.mount('/assets',StaticFiles(directory=WEB_DIST/'assets'),name='assets')
@app.get('/{path:path}',include_in_schema=False)
def spa(path:str):
    if path.startswith(('api/','ws/')): raise HTTPException(404,'Not found')
    p=(WEB_DIST/path).resolve()
    if WEB_DIST.exists() and p.is_relative_to(WEB_DIST.resolve()) and p.is_file(): return FileResponse(p)
    if (WEB_DIST/'index.html').exists(): return FileResponse(WEB_DIST/'index.html')
    raise HTTPException(404,'Frontend chưa build')

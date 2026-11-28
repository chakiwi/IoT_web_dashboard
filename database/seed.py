"""Idempotent fictional demo students/cards. No NFC-only demo attendance is seeded."""
from datetime import datetime,timedelta,timezone
from .db import connect,initialize,db_path,record_scan

PEOPLE=[
('23110001','Nguyễn Minh Anh','CE01'),('23110002','Trần Quốc Bảo','CE01'),
('23110003','Lê Hoàng Phúc','CE02'),('23110004','Phạm Gia Hân','CE02'),
('23110005','Võ Đức Huy','CE01'),('23110006','Đặng Hà My','CE03'),
('23110007','Bùi Minh Khang','CE03'),('23110008','Đỗ Quỳnh Như','CE01'),
('23110009','Ngô Gia Phát','CE02'),('23110010','Hoàng Ngọc Lan','CE03'),
('23110011','Phan Tuấn Kiệt','CE01'),('23110012','Lý Minh Thư','CE02')]
def seed(include_scans=False):
    """Seed fictional data only when the database has no students yet."""
    initialize()
    with connect() as db:
        # Never repopulate a deliberately cleaned database that already has a sample/real student.
        if db.execute('SELECT COUNT(*) FROM students').fetchone()[0] > 0:
            return
        for code,name,cls in PEOPLE:
            db.execute('INSERT OR IGNORE INTO students(full_name,student_code,class_name) VALUES(?,?,?)',(name,code,cls))
        for i,(code,_,_) in enumerate(PEOPLE,1):
            sid=db.execute('SELECT id FROM students WHERE student_code=?',(code,)).fetchone()['id']
            db.execute('INSERT OR IGNORE INTO nfc_cards(uid,student_id,card_type) VALUES(?,?,?)',(f'A1B2{i:08X}',sid,'DEMO_ISO14443-A'))
        if include_scans and db.execute('SELECT COUNT(*) FROM attendance_sessions WHERE is_active=1').fetchone()[0]==0:
            db.execute("INSERT INTO attendance_sessions(title,starts_at,ends_at,is_active) VALUES(?,?,?,1)",
                ('Buổi điểm danh demo',(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat(),(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat()))
        if include_scans and db.execute('SELECT COUNT(*) FROM scan_events').fetchone()[0]==0:
            session_id=db.execute("SELECT id FROM attendance_sessions WHERE is_active=1 ORDER BY id DESC LIMIT 1").fetchone()['id']
            for i in range(24):
                uid=f'A1B2{(i%12)+1:08X}' if i not in (6,18) else 'DEADBEEF'
                record_scan(db,f'DEMO-{i+1:04d}',uid,session_id)
        db.commit()
if __name__=='__main__':
    seed()
    print('SQLite ready:',db_path())

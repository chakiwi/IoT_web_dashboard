import os,sys,tempfile,unittest
from pathlib import Path
from fastapi.testclient import TestClient
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
TMP=tempfile.TemporaryDirectory()
os.environ['ATTENDA_DB_PATH']=str(Path(TMP.name)/'test.db')
os.environ['DEMO_MODE']='true';os.environ['ADMIN_USERNAME']='admin';os.environ['ADMIN_PASSWORD']='test-password'
os.environ['APP_SECRET']='test-secret-long-enough-for-local-test-only';os.environ['DEVICE_TOKEN']='test-device-token-long-enough'
from backend.app.main import app
class ApiTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.ctx=TestClient(app);cls.c=cls.ctx.__enter__()
  cls.token=cls.c.post('/api/v1/auth/login',json={'username':'admin','password':'test-password'}).json()['access_token']
  cls.h={'Authorization':'Bearer '+cls.token}
 @classmethod
 def tearDownClass(cls): cls.ctx.__exit__(None,None,None);TMP.cleanup()
 def test_health_and_schema(self):
  self.assertEqual(self.c.get('/api/v1/health').status_code,200)
  with __import__('sqlite3').connect(os.environ['ATTENDA_DB_PATH']) as db:
   names={r[0] for r in db.execute("select name from sqlite_master where type='table'")}
  self.assertTrue({'students','nfc_cards','face_templates','attendance_sessions','scan_events','attendance_records'}<=names)
  self.assertNotIn('stations',names)
 def test_student_and_scan(self):
  x={'full_name':'Test Student','student_code':'99900001','class_name':'TEST','card_uid':'AABBCCDD','is_active':True}
  r=self.c.post('/api/v1/students',json=x,headers=self.h);self.assertEqual(r.status_code,201,r.text)
  import base64
  face={'face_id':'FACE-EV-1','student_id':r.json()['id'],'face_embedding':base64.b64encode(b'1234').decode(),'embedding_dim':1,'model_name':'test','model_version':'1'}
  self.assertEqual(self.c.post('/api/v1/faces',json=face,headers=self.h).status_code,201)
  device={'X-Device-Token':'test-device-token-long-enough'}
  start=self.c.post('/api/v1/verification/start',json={'event_id':'EV-1','card_uid':'AABBCCDD'},headers=device)
  self.assertEqual(start.status_code,200,start.text);self.assertEqual(start.json()['event_id'],'EV-1')
  self.assertEqual(len(self.c.get('/api/v1/scans',headers=self.h).json()),0)
  complete=self.c.post('/api/v1/verification/complete',json={'event_id':'EV-1','face_result':True},headers=device)
  self.assertEqual(complete.status_code,200,complete.text);self.assertTrue(complete.json()['verified'])
  self.assertEqual(len(self.c.get('/api/v1/scans',headers=self.h).json()),1)
  duplicate=self.c.post('/api/v1/verification/complete',json={'event_id':'EV-1','face_result':True},headers=device)
  self.assertEqual(duplicate.status_code,200);self.assertFalse(duplicate.json()['created'])
  failed_start=self.c.post('/api/v1/verification/start',json={'event_id':'EV-2','card_uid':'AABBCCDD'},headers=device)
  self.assertEqual(failed_start.status_code,200,failed_start.text)
  failed=self.c.post('/api/v1/verification/complete',json={'event_id':'EV-2','face_result':False},headers=device)
  self.assertEqual(failed.status_code,200);self.assertFalse(failed.json()['verified'])
  events=self.c.get('/api/v1/scans',headers=self.h).json()
  self.assertEqual(len(events),2);self.assertEqual(events[0]['face_verified'],0)
  attendance=self.c.get('/api/v1/attendance',headers=self.h).json()
  self.assertEqual(len(attendance),0)
  old=self.c.post('/api/v1/scans',json={'event_id':'EV-OLD','card_uid':'AABBCCDD'},headers=device)
  self.assertEqual(old.status_code,410)
 def test_faces(self):
  student=self.c.get('/api/v1/students',headers=self.h).json()[0]
  import base64
  x={'face_id':'FACE-TEST','student_id':student['id'],'face_embedding':base64.b64encode(b'1234').decode(),'embedding_dim':1,'model_name':'test','model_version':'1'}
  r=self.c.post('/api/v1/faces',json=x,headers=self.h);self.assertEqual(r.status_code,201,r.text)
if __name__=='__main__':unittest.main()

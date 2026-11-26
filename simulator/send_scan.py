"""Simulate the ESP32 NFC request and the ESP32-S3-CAM face result."""
import argparse,json,os,sys,urllib.request,urllib.error,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
def post(server,path,body):
    req=urllib.request.Request(server.rstrip('/')+path,data=json.dumps(body).encode(),
      headers={'Content-Type':'application/json','X-Device-Token':os.getenv('DEVICE_TOKEN','')},method='POST')
    with urllib.request.urlopen(req,timeout=8) as r:return json.loads(r.read())
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--server',default='http://127.0.0.1:8000')
    ap.add_argument('--uid',default='A1B200000001')
    ap.add_argument('--event-id',default=None)
    ap.add_argument('--session-id',type=int,default=None)
    ap.add_argument('--face-result',type=int,choices=(0,1),default=1,help='Simulated ESP32-S3-CAM result: 1=match, 0=no match')
    args=ap.parse_args()
    event_id=args.event_id or 'SIM-'+uuid.uuid4().hex
    body={'event_id':event_id,'card_uid':args.uid}
    if args.session_id is not None:body['session_id']=args.session_id
    try:
        start=post(args.server,'/api/v1/verification/start',body)
        print('NFC accepted; embedding received for student:',start['student_id'])
        result=post(args.server,'/api/v1/verification/complete',{'event_id':event_id,'face_result':bool(args.face_result)})
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except urllib.error.HTTPError as e:print('HTTP',e.code,e.read().decode());raise SystemExit(1)
    except OSError as e:print('Cannot connect to backend:',e);raise SystemExit(1)
if __name__=='__main__':main()

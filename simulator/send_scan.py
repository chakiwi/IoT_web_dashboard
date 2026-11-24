"""Send a test scan using the same payload contract as the ESP32 firmware."""
import argparse,json,os,sys,urllib.request,urllib.error,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--server',default='http://127.0.0.1:8000')
    ap.add_argument('--uid',default='A1B200000001')
    ap.add_argument('--event-id',default=None)
    ap.add_argument('--session-id',type=int,default=None)
    args=ap.parse_args()
    body={'event_id':args.event_id or 'SIM-'+uuid.uuid4().hex,'card_uid':args.uid}
    if args.session_id is not None: body['session_id']=args.session_id
    req=urllib.request.Request(args.server.rstrip('/')+'/api/v1/scans',data=json.dumps(body).encode(),
      headers={'Content-Type':'application/json','X-Device-Token':os.getenv('DEVICE_TOKEN','')},method='POST')
    try:
        with urllib.request.urlopen(req,timeout=8) as r: print('HTTP',r.status);print(json.dumps(json.loads(r.read()),ensure_ascii=False,indent=2))
    except urllib.error.HTTPError as e: print('HTTP',e.code,e.read().decode());raise SystemExit(1)
    except OSError as e: print('Không kết nối được backend:',e);raise SystemExit(1)
if __name__=='__main__': main()

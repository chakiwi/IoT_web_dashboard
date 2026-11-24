"""USB Serial -> local FastAPI. ACK is sent only after the API persisted the scan."""
import argparse,json,os,sys,time,urllib.request,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
try: import serial
except ImportError: raise SystemExit('Thiếu pyserial: cài requirements.txt')
def send(server,event):
    payload={k:event[k] for k in ('event_id','card_uid')}
    if event.get('session_id') is not None: payload['session_id']=event['session_id']
    req=urllib.request.Request(server.rstrip('/')+'/api/v1/scans',data=json.dumps(payload).encode(),
      method='POST',headers={'Content-Type':'application/json','X-Device-Token':os.getenv('DEVICE_TOKEN','')})
    with urllib.request.urlopen(req,timeout=8) as r:return json.loads(r.read())
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--port',required=True);ap.add_argument('--baud',type=int,default=115200);ap.add_argument('--server',default='http://127.0.0.1:8000');a=ap.parse_args()
    while True:
        try:
            with serial.Serial(a.port,a.baud,timeout=1,write_timeout=2) as conn:
                time.sleep(2);print('USB bridge',a.port,'->',a.server)
                while True:
                    raw=conn.readline()
                    if not raw:continue
                    line=raw.decode(errors='replace').strip()
                    if not line.startswith('{'):
                        if line:print('[ESP32]',line)
                        continue
                    try:
                        event=json.loads(line)
                        if event.get('type')!='scan':continue
                        result=send(a.server,event)
                        conn.write(('ACK '+event['event_id']+'\\n').encode());conn.flush()
                        print('Saved:',result.get('result'),event['event_id'])
                    except Exception as exc: print('Not acknowledged; board may retry:',exc)
        except (serial.SerialException,OSError) as exc:
            print('Waiting for serial:',exc);time.sleep(2)
if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:print('Stopped')

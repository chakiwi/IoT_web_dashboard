"""USB Serial bridge for the two-stage NFC + face verification protocol."""
import argparse,json,os,time,urllib.request,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
try:
    import serial
except ImportError:
    raise SystemExit('Thiếu pyserial: cài backend requirements.txt')
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')

def post(server,path,payload):
    req=urllib.request.Request(server.rstrip('/')+path,data=json.dumps(payload).encode(),
      method='POST',headers={'Content-Type':'application/json','X-Device-Token':os.getenv('DEVICE_TOKEN','')})
    with urllib.request.urlopen(req,timeout=10) as response:return json.loads(response.read())

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',required=True)
    parser.add_argument('--baud',type=int,default=115200)
    parser.add_argument('--server',default='http://127.0.0.1:8000')
    args=parser.parse_args()
    while True:
        try:
            with serial.Serial(args.port,args.baud,timeout=1,write_timeout=3) as conn:
                time.sleep(2);print('USB bridge',args.port,'->',args.server)
                while True:
                    raw=conn.readline()
                    if not raw:continue
                    line=raw.decode(errors='replace').strip()
                    if not line.startswith('{'):
                        if line:print('[ESP32]',line)
                        continue
                    try:
                        message=json.loads(line)
                        kind=message.get('type')
                        if kind=='verification_start':
                            payload={key:message[key] for key in ('event_id','card_uid','session_id') if key in message}
                            result=post(args.server,'/api/v1/verification/start',payload)
                            conn.write((json.dumps({'type':'verification_ready',**result})+'\n').encode());conn.flush()
                            print('Embedding sent to board for event:',result['event_id'])
                        elif kind=='face_result':
                            result=post(args.server,'/api/v1/verification/complete',{
                                'event_id':message['event_id'],'face_result':bool(message['face_result'])})
                            conn.write((json.dumps({'type':'verification_complete',**result})+'\n').encode());conn.flush()
                            print('Attendance verified:',result.get('verified'),message['event_id'])
                    except Exception as exc:
                        print('Request failed:',exc)
        except (serial.SerialException,OSError) as exc:
            print('Waiting for serial:',exc);time.sleep(2)
if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:print('Stopped')

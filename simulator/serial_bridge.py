"""USB Serial bridge for the two-stage attendance API and enrollment capture."""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv

load_dotenv(ROOT / '.env')

try:
    import serial
except ImportError as error:
    raise SystemExit('Missing pyserial: install backend/requirements.txt') from error


def post_json(server: str, endpoint: str, payload: dict) -> dict:
    request = urllib.request.Request(
        server.rstrip('/') + endpoint,
        data=json.dumps(payload).encode(),
        method='POST',
        headers={
            'Content-Type': 'application/json',
            'X-Device-Token': os.getenv('DEVICE_TOKEN', ''),
        },
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        return json.loads(response.read())


def send_event(server: str, connection, event: dict) -> None:
    event_type = event.get('type')
    event_id = str(event.get('event_id', ''))

    if event_type == 'scan':
        payload = {'event_id': event_id, 'card_uid': event['card_uid']}
        if event.get('session_id') is not None:
            payload['session_id'] = event['session_id']
        result = post_json(server, '/api/v1/verification/start', payload)
        if result.get('status') == 'pending':
            # The device can forward this template to its face-matching module.
            message = {
                'type': 'face_template',
                'event_id': event_id,
                'face_embedding': result['face_embedding'],
                'embedding_dim': result['embedding_dim'],
                'model_name': result['model_name'],
                'model_version': result['model_version'],
            }
            connection.write((json.dumps(message) + '\n').encode())
            connection.flush()
        else:
            connection.write((f"RESULT {event_id} {result.get('status')}\n").encode())
            connection.flush()
        print('NFC stage:', result.get('status'), event_id)
        return

    if event_type == 'face_result':
        face_result = event.get('face_result')
        if face_result not in (True, False, 1, 0):
            raise ValueError('face_result must be boolean or 0/1')
        result = post_json(server, '/api/v1/verification/complete', {
            'event_id': event_id,
            'face_result': bool(face_result),
        })
        connection.write((f"ACK {event_id} {result.get('status')}\n").encode())
        connection.flush()
        print('Face stage:', result.get('status'), event_id)
        return

    if event_type == 'registration_capture':
        payload = {key: value for key, value in event.items() if key != 'type'}
        result = post_json(server, '/api/v1/registrations/capture', payload)
        connection.write((f"ACK {event_id} {result.get('status')}\n").encode())
        connection.flush()
        print('Registration capture:', result.get('status'), result.get('registration_id'))
        return

    print('Ignored unknown serial event type:', event_type)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', required=True)
    parser.add_argument('--baud', type=int, default=115200)
    parser.add_argument('--server', default='http://127.0.0.1:8000')
    args = parser.parse_args()

    while True:
        try:
            with serial.Serial(args.port, args.baud, timeout=1, write_timeout=3) as connection:
                time.sleep(2)
                print('USB bridge', args.port, '->', args.server)
                while True:
                    raw = connection.readline()
                    if not raw:
                        continue
                    line = raw.decode(errors='replace').strip()
                    if not line.startswith('{'):
                        if line:
                            print('[DEVICE]', line)
                        continue
                    try:
                        send_event(args.server, connection, json.loads(line))
                    except (KeyError, ValueError, urllib.error.URLError, urllib.error.HTTPError) as error:
                        print('Device event was not accepted:', error)
        except (serial.SerialException, OSError) as error:
            print('Waiting for serial connection:', error)
            time.sleep(2)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Stopped')

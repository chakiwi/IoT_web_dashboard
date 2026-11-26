"""Simulate one two-stage attendance check-in against the Attenda API."""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv

load_dotenv(ROOT / '.env')


def post_json(server: str, endpoint: str, payload: dict) -> dict:
    request = urllib.request.Request(
        server.rstrip('/') + endpoint,
        data=json.dumps(payload).encode(),
        headers={
            'Content-Type': 'application/json',
            'X-Device-Token': os.getenv('DEVICE_TOKEN', ''),
        },
        method='POST',
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())


def main() -> None:
    parser = argparse.ArgumentParser(description='Simulate NFC then face verification')
    parser.add_argument('--server', default='http://127.0.0.1:8000')
    parser.add_argument('--uid', required=True, help='UID of an approved NFC card')
    parser.add_argument('--event-id', default=None)
    parser.add_argument('--session-id', type=int, default=None)
    parser.add_argument('--face-result', choices=('match', 'mismatch'), default='match')
    args = parser.parse_args()

    event_id = args.event_id or 'SIM-' + uuid.uuid4().hex.upper()
    start_payload = {'event_id': event_id, 'card_uid': args.uid}
    if args.session_id is not None:
        start_payload['session_id'] = args.session_id

    try:
        started = post_json(args.server, '/api/v1/verification/start', start_payload)
        print('NFC stage:')
        print(json.dumps(started, ensure_ascii=False, indent=2))
        if started.get('status') != 'pending':
            print('Attendance was not recorded. Face verification cannot continue.')
            return

        completed = post_json(args.server, '/api/v1/verification/complete', {
            'event_id': event_id,
            'face_result': args.face_result == 'match',
        })
        print('\nFace stage:')
        print(json.dumps(completed, ensure_ascii=False, indent=2))
    except urllib.error.HTTPError as error:
        print('HTTP', error.code, error.read().decode(errors='replace'))
        raise SystemExit(1)
    except OSError as error:
        print('Could not connect to backend:', error)
        raise SystemExit(1)


if __name__ == '__main__':
    main()

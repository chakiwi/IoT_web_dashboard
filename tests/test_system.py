import base64
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TEMP = tempfile.TemporaryDirectory()
os.environ['ATTENDA_DB_PATH'] = str(Path(TEMP.name) / 'test.db')
os.environ['DEMO_MODE'] = 'true'
os.environ['ADMIN_USERNAME'] = 'admin'
os.environ['ADMIN_PASSWORD'] = 'test-password'
os.environ['APP_SECRET'] = 'test-secret-long-enough-for-local-test-only'
os.environ['DEVICE_TOKEN'] = 'test-device-token-long-enough'

from backend.app.main import app


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = TestClient(app)
        cls.client = cls.context.__enter__()
        token = cls.client.post('/api/v1/auth/login', json={
            'username': 'admin', 'password': 'test-password'
        }).json()['access_token']
        cls.admin_headers = {'Authorization': 'Bearer ' + token}
        cls.device_headers = {'X-Device-Token': 'test-device-token-long-enough'}

    @classmethod
    def tearDownClass(cls):
        cls.context.__exit__(None, None, None)
        TEMP.cleanup()

    def test_health_schema_and_no_station_api(self):
        health = self.client.get('/api/v1/health').json()
        self.assertEqual(health['schema_version'], 3)
        with __import__('sqlite3').connect(os.environ['ATTENDA_DB_PATH']) as db:
            names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({'students', 'nfc_cards', 'face_templates', 'attendance_sessions', 'scan_events',
                         'attendance_records', 'card_inventory', 'registration_queue', 'verification_attempts'} <= names)
        self.assertNotIn('stations', names)
        self.assertEqual(self.client.get('/api/v1/stations', headers=self.admin_headers).status_code, 404)

    def test_card_inventory_registration_capture_and_approval(self):
        add_card = self.client.post('/api/v1/cards/inventory', json={'card_uid': 'C0FFEE01'}, headers=self.admin_headers)
        self.assertEqual(add_card.status_code, 201, add_card.text)
        blank_code = self.client.post('/api/v1/registrations', json={
            'student_code': '   ', 'full_name': 'Test Registration', 'class_name': 'TEST01'
        }, headers=self.admin_headers)
        self.assertEqual(blank_code.status_code, 422)
        registration = self.client.post('/api/v1/registrations', json={
            'student_code': '99900001', 'full_name': 'Test Registration', 'class_name': 'TEST01'
        }, headers=self.admin_headers)
        self.assertEqual(registration.status_code, 201, registration.text)
        data = registration.json()
        self.assertEqual(data['card_uid'], 'C0FFEE01')
        self.assertEqual(self.client.post('/api/v1/students', json={}, headers=self.admin_headers).status_code, 410)
        approve_too_early = self.client.post(f"/api/v1/registrations/{data['registration_id']}/approve", headers=self.admin_headers)
        self.assertEqual(approve_too_early.status_code, 409)
        wrong_card = self.client.post('/api/v1/registrations/capture', headers=self.device_headers, json={
            'event_id': 'ENROLL-WRONG-CARD',
            'card_uid': 'DEADBEEF',
            'face_embedding': base64.b64encode(b'1234').decode(),
            'embedding_dim': 1,
            'model_name': 'test-model',
            'model_version': '1',
            'face_image_base64': base64.b64encode(b'\xff\xd8\xff\xe0' + b'\x00' * 20 + b'\xff\xd9').decode(),
            'image_mime': 'image/jpeg',
        })
        self.assertEqual(wrong_card.status_code, 404)
        self.assertNotIn('99900001', [student['student_code'] for student in self.client.get('/api/v1/students', headers=self.admin_headers).json()])

        embedding = base64.b64encode(b'1234').decode()
        image = base64.b64encode(b'\xff\xd8\xff\xe0' + b'\x00' * 20 + b'\xff\xd9').decode()
        capture = self.client.post('/api/v1/registrations/capture', headers=self.device_headers, json={
            'card_uid': data['card_uid'],
            'face_embedding': embedding,
            'embedding_dim': 1,
            'face_image_base64': image,
        })
        self.assertEqual(capture.status_code, 201, capture.text)
        self.assertEqual(capture.json()['registration_id'], data['registration_id'])
        self.assertEqual(capture.json()['status'], 'captured')
        repeated_capture = self.client.post('/api/v1/registrations/capture', headers=self.device_headers, json={
            'card_uid': data['card_uid'],
            'face_embedding': embedding,
            'embedding_dim': 1,
            'face_image_base64': image,
        })
        self.assertFalse(repeated_capture.json()['created'])
        self.assertEqual(repeated_capture.json()['registration_id'], data['registration_id'])
        queue = self.client.get('/api/v1/registrations', headers=self.admin_headers).json()
        self.assertEqual(queue[0]['status'], 'captured')
        face_image = self.client.get(f"/api/v1/registrations/{data['registration_id']}/image", headers=self.admin_headers)
        self.assertEqual(face_image.status_code, 200)
        self.assertTrue(face_image.content.startswith(b'\xff\xd8\xff'))

        approved = self.client.post(f"/api/v1/registrations/{data['registration_id']}/approve", headers=self.admin_headers)
        self.assertEqual(approved.status_code, 200, approved.text)
        students = self.client.get('/api/v1/students', headers=self.admin_headers).json()
        new_student = next(student for student in students if student['student_code'] == '99900001')
        self.assertEqual(new_student['card_uid'], 'C0FFEE01')
        self.assertEqual(new_student['has_face'], 1)
        inventory = self.client.get('/api/v1/cards/inventory', headers=self.admin_headers).json()
        self.assertEqual(inventory[0]['status'], 'assigned')

    def test_rejection_releases_reserved_card_for_next_registration(self):
        add_card = self.client.post('/api/v1/cards/inventory', json={'card_uid': 'C0FFEE02'}, headers=self.admin_headers)
        self.assertEqual(add_card.status_code, 201, add_card.text)
        first = self.client.post('/api/v1/registrations', json={
            'student_code': '99900002', 'full_name': 'First Candidate', 'class_name': 'TEST01'
        }, headers=self.admin_headers)
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(first.json()['card_uid'], 'C0FFEE02')

        rejected = self.client.post(
            f"/api/v1/registrations/{first.json()['registration_id']}/reject",
            headers=self.admin_headers,
        )
        self.assertEqual(rejected.status_code, 200, rejected.text)
        cards = self.client.get('/api/v1/cards/inventory', headers=self.admin_headers).json()
        returned = next(card for card in cards if card['uid'] == 'C0FFEE02')
        self.assertEqual(returned['status'], 'available')

        second = self.client.post('/api/v1/registrations', json={
            'student_code': '99900003', 'full_name': 'Second Candidate', 'class_name': 'TEST01'
        }, headers=self.admin_headers)
        self.assertEqual(second.status_code, 201, second.text)
        self.assertEqual(second.json()['card_uid'], 'C0FFEE02')

    def test_attendance_needs_both_nfc_and_face(self):
        student = self.client.get('/api/v1/students', headers=self.admin_headers).json()[0]
        if not student['has_face']:
            face = self.client.post('/api/v1/faces', headers=self.admin_headers, json={
                'face_id': 'FACE-ATTENDANCE-TEST',
                'student_id': student['id'],
                'face_embedding': base64.b64encode(b'1234').decode(),
                'embedding_dim': 1,
                'model_name': 'test-model',
                'model_version': '1',
                'is_active': True,
            })
            self.assertEqual(face.status_code, 201, face.text)
        now = datetime.now(timezone.utc)
        session = self.client.post('/api/v1/sessions', headers=self.admin_headers, json={
            'title': 'Test session',
            'starts_at': (now - timedelta(minutes=5)).isoformat(),
            'ends_at': (now + timedelta(minutes=60)).isoformat(),
            'is_active': True,
        })
        self.assertEqual(session.status_code, 201, session.text)
        session_id = session.json()['id']

        failed_start = self.client.post('/api/v1/verification/start', headers=self.device_headers, json={
            'event_id': 'ATTEND-FAIL', 'card_uid': student['card_uid'], 'session_id': session_id
        })
        self.assertEqual(failed_start.status_code, 200, failed_start.text)
        self.assertEqual(failed_start.json()['status'], 'pending')
        self.assertEqual(self.client.get('/api/v1/attendance', headers=self.admin_headers).json(), [])
        failed_complete = self.client.post('/api/v1/verification/complete', headers=self.device_headers, json={
            'event_id': 'ATTEND-FAIL', 'face_result': False
        })
        self.assertEqual(failed_complete.json()['status'], 'face_mismatch')
        self.assertEqual(self.client.get('/api/v1/attendance', headers=self.admin_headers).json(), [])

        good_start = self.client.post('/api/v1/verification/start', headers=self.device_headers, json={
            'event_id': 'ATTEND-OK', 'card_uid': student['card_uid'], 'session_id': session_id
        })
        self.assertEqual(good_start.status_code, 200, good_start.text)
        self.assertIn('face_embedding', good_start.json())
        good_complete = self.client.post('/api/v1/verification/complete', headers=self.device_headers, json={
            'event_id': 'ATTEND-OK', 'face_result': True
        })
        self.assertEqual(good_complete.json()['status'], 'verified')
        attendance = self.client.get('/api/v1/attendance', headers=self.admin_headers).json()
        self.assertEqual(len(attendance), 1)
        repeated = self.client.post('/api/v1/verification/complete', headers=self.device_headers, json={
            'event_id': 'ATTEND-OK', 'face_result': True
        })
        self.assertFalse(repeated.json()['created'])
        self.assertEqual(len(self.client.get('/api/v1/attendance', headers=self.admin_headers).json()), 1)


if __name__ == '__main__':
    unittest.main()

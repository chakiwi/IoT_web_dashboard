from .db import connect

if __name__ == '__main__':
    with connect() as db:
        for name in ('students', 'nfc_cards', 'face_templates', 'card_inventory', 'registration_queue', 'verification_attempts', 'scan_events', 'attendance_records'):
            print(name, db.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0])
        print('Recent verification attempts:')
        for row in db.execute('''SELECT a.event_id,a.card_uid,s.full_name,a.status,a.started_at
                                 FROM verification_attempts a
                                 LEFT JOIN students s ON s.id=a.student_id
                                 ORDER BY a.started_at DESC LIMIT 10'''):
            print(dict(row))

from .db import connect
if __name__=='__main__':
    with connect() as db:
        for name in ('students','nfc_cards','stations','scan_events'):
            print(name, db.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0])
        print('Recent events:')
        for row in db.execute('SELECT station_name,full_name,card_uid,result,occurred_at FROM v_recent_scans ORDER BY received_at DESC LIMIT 10'):
            print(dict(row))

"""Explicitly delete existing data only after typing a confirmation phrase."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from database.db import db_path
from database.seed import seed
p=db_path()
print('WARNING: This will erase ALL records from:',p)
confirm=input('Type DELETE DEMO DATABASE to continue: ')
if confirm!='DELETE DEMO DATABASE':
    print('Cancelled.');raise SystemExit(1)
for item in (p,Path(str(p)+'-wal'),Path(str(p)+'-shm')):
    item.unlink(missing_ok=True)
seed()
print('Demo data restored:',p)

"""Safe online backup using SQLite backup API."""
from datetime import datetime
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from database.db import connect
import sqlite3
folder=Path(__file__).resolve().parents[1]/'backups'
folder.mkdir(exist_ok=True)
file=folder/('attendance-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.db')
with connect() as source, sqlite3.connect(file) as dest:
    source.backup(dest)
print('Backup saved:',file)

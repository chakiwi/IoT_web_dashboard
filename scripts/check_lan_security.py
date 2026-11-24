"""Block accidental exposure of default credentials on a LAN."""
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1]/'.env',override=True)
errors=[]
if os.getenv('ADMIN_PASSWORD','') in ('','attenda123','admin','password'):
    errors.append('ADMIN_PASSWORD con de mac dinh')
secret=os.getenv('APP_SECRET','')
if len(secret)<32 or secret.startswith('replace-'):
    errors.append('APP_SECRET phai la chuoi ngau nhien >= 32 ky tu')
device=os.getenv('DEVICE_TOKEN','')
if len(device)<20 or device.startswith('replace-'):
    errors.append('DEVICE_TOKEN can doi thanh khoa moi >= 20 ky tu')
if errors:
    for e in errors: print('[SECURITY]',e)
    raise SystemExit(1)
print('Secrets meet local LAN checks. Do NOT expose port 8000 to the Internet.')

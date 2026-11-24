"""Run from project root: python -m database.setup"""
import argparse
from .db import initialize, db_path
from .seed import seed
if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--empty',action='store_true',help='Create schema only (no demo data)')
    args=ap.parse_args()
    initialize() if args.empty else seed()
    print('Ready:',db_path())

"""Run from project root: python -m database.setup"""
import argparse
from .db import initialize, db_path
from .seed import seed

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-demo", action="store_true", help="Add fictional demo students/cards to an empty database")
    parser.add_argument("--empty", action="store_true", help="Compatibility flag: create/upgrade schema only")
    args = parser.parse_args()
    if args.seed_demo:
        seed()
    else:
        initialize()
    print("SQLite ready:", db_path())

"""
Creates the database, all tables, triggers, views and demo data in one go.
Run:  python setup_db.py      (it asks for YOUR PostgreSQL password)
WARNING: running it again resets the 'malkhana' schema to the demo data.
"""
import getpass
import os
import sys
from pathlib import Path

import psycopg2
from psycopg2 import sql

HERE = Path(__file__).parent
HOST = os.getenv("DB_HOST", "localhost")
PORT = os.getenv("DB_PORT", "5432")
USER = os.getenv("DB_USER", "postgres")
NAME = os.getenv("DB_NAME", "malkhana_db")
PASSWORD = os.getenv("DB_PASSWORD") or getpass.getpass("Enter YOUR PostgreSQL password (typing is hidden): ")


def connect(dbname):
    return psycopg2.connect(host=HOST, port=PORT, user=USER, password=PASSWORD, dbname=dbname)


try:
    c = connect("postgres")
    c.autocommit = True
    cur = c.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (NAME,))
    if not cur.fetchone():
        cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(NAME)))
        print(f"Created database {NAME}")
    c.close()

    c = connect(NAME)
    cur = c.cursor()
    for f in ("schema.sql", "sample_data_and_queries.sql"):
        print("Running", f, "...")
        cur.execute((HERE / "database" / f).read_text(encoding="utf-8"))
    c.commit()
    c.close()
    print("\nDone. Database is ready. Now run:  python app.py")
except Exception as e:
    print("\nSETUP FAILED:", e)
    print("Check: is PostgreSQL running, and is the password correct?")
    sys.exit(1)

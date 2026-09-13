"""
ESGenuine — create the full schema in an EMPTY Supabase project.

Applies, in order: database/schema.sql, the dated migrations (oldest first), the RPC
functions, and finally the row-level-security migration. Every file runs in its own
transaction and the script stops at the first error.

    python backend/scripts/bootstrap_db.py            # apply everything
    python backend/scripts/bootstrap_db.py --no-rls   # leave RLS off (local experiments)

Safety: schema.sql begins with `DROP TABLE IF EXISTS claims CASCADE`. If a `claims`
table already exists this script SKIPS schema.sql rather than wiping it; pass
--force-schema only if you really mean to drop and recreate the claims table.

Needs DATABASE_URL in .env. On Supabase, use the "Session pooler" connection string
(IPv4-compatible); the "Direct connection" host is IPv6-only on the free tier.
"""
import argparse
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]           # backend/
DB_DIR = ROOT / "database"
RLS = "2026-08-09_enable_rls.sql"
load_dotenv(ROOT.parent / ".env")


def plan(skip_schema: bool, rls: bool) -> list:
    files = [] if skip_schema else [DB_DIR / "schema.sql"]
    files += sorted(p for p in DB_DIR.glob("2026-*.sql") if p.name != RLS)
    files += sorted(DB_DIR.glob("*_rpc.sql"))
    if rls:
        files.append(DB_DIR / RLS)
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-rls", action="store_true", help="do not apply the RLS migration")
    ap.add_argument("--force-schema", action="store_true",
                    help="run schema.sql even if claims exists (DROPS the claims table)")
    a = ap.parse_args()

    url = os.getenv("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL not set. Add it to your .env first.")

    conn = psycopg2.connect(url, connect_timeout=20)
    with conn.cursor() as cur:
        cur.execute("select to_regclass('public.claims') is not null")
        claims_exists = cur.fetchone()[0]
    skip_schema = claims_exists and not a.force_schema
    if skip_schema:
        print("claims table already exists -> skipping schema.sql (it would DROP the table)")

    for f in plan(skip_schema, not a.no_rls):
        sql = f.read_text(encoding="utf-8")
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
            print(f"  ok    {f.name}")
        except Exception as e:
            conn.rollback()
            print(f"  FAIL  {f.name}: {str(e).strip().splitlines()[0]}")
            sys.exit(1)

    with conn.cursor() as cur:
        cur.execute("""select table_name from information_schema.tables
                       where table_schema = 'public' and table_type = 'BASE TABLE'
                       and table_name not like 'claims\\_%' order by 1""")
        print("tables:", ", ".join(r[0] for r in cur.fetchall()))
    conn.close()
    print("done.")


if __name__ == "__main__":
    main()

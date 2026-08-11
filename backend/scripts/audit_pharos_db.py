import os
from urllib.parse import urlsplit

import psycopg2
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# No default. A KeyError here is the correct outcome: falling back to a literal would
# reintroduce the hardcoded superuser credential this file used to carry.
conn_str = os.environ["DATABASE_URL"]

def audit_db():
    print(f"Connecting to: {urlsplit(conn_str).hostname}")
    try:
        conn = psycopg2.connect(conn_str)
        cur = conn.cursor()
        
        # 1. Total claims
        cur.execute("SELECT count(*) FROM claims;")
        total = cur.fetchone()[0]
        print(f"Total claims in DB: {total}")

        # 2. Partitions check
        cur.execute("""
            SELECT nmsp_parent.nspname AS parent_schema,
                   parent.relname AS parent_name,
                   nmsp_child.nspname AS child_schema,
                   child.relname AS child_name
            FROM pg_inherits
                JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
                JOIN pg_class child ON pg_inherits.inhrelid = child.oid
                JOIN pg_namespace nmsp_parent ON nmsp_parent.oid = parent.relnamespace
                JOIN pg_namespace nmsp_child ON nmsp_child.oid = child.relnamespace
            WHERE parent.relname = 'claims';
        """)
        partitions = cur.fetchall()
        print(f"Found {len(partitions)} database partitions.")
        for p in partitions:
            print(f"   - {p[3]}")

        # 3. Last 5 claims count by aspect
        cur.execute("SELECT normalized_aspect, count(*) FROM claims GROUP BY normalized_aspect ORDER BY count DESC LIMIT 5;")
        aspects = cur.fetchall()
        print("\nTop Aspects Ingested:")
        for a in aspects:
            print(f"   - {a[0]}: {a[1]}")

        # 4. Reports metadata
        cur.execute("SELECT count(*) FROM reports;")
        reports_count = cur.fetchone()[0]
        print(f"\nTotal reports in catalog: {reports_count}")

        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"Connection FAILED: {e}")

if __name__ == "__main__":
    audit_db()

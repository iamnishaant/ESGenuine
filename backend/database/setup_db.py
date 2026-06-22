import psycopg2
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the project root (backend/database/ -> project root).
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

# Direct connection string read from env (do NOT hardcode credentials in source).
# Add to .env:  DATABASE_URL=postgresql://postgres:<password>@db.<ref>.supabase.co:5432/postgres
conn_str = os.getenv("DATABASE_URL")
if not conn_str:
    raise SystemExit("DATABASE_URL not set. Add it to your .env before running this script.")

print("Connecting to Supabase Postgres...")
try:
    conn = psycopg2.connect(conn_str)
    cur = conn.cursor()
    
    print(f"Reading schema from {SCHEMA_PATH}")
    with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
        sql = f.read()

    print("Executing schema...")
    cur.execute(sql)
    conn.commit()
    
    cur.close()
    conn.close()
    print("Schema applied successfully!")
except Exception as e:
    print(f"Execution failed: {e}")

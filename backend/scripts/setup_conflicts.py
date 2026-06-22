import os
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

# Load environment from the project root (backend/scripts/ -> project root).
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

URL = os.getenv("VITE_SUPABASE_URL")
KEY = os.getenv("VITE_SUPABASE_PUBLISHABLE_KEY")

supabase = create_client(URL, KEY)

def init_conflicts():
    print("Setting up contradictions table...")
    
    # We can't easily run DDL (CREATE TABLE) directly via the Supabase JS/Python client
    # unless we use postgres connection or rpc. 
    # Let's check what we can do via psycopg2.
    import psycopg2
    
    # Assuming standard Supabase Postgres connection string format:
    # We need the direct DB connection string. The user usually has it in .env, let's grab it or ask.
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not found in .env. Falling back to the claims we have.")
        return False
        
    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        
        # Create table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS contradictions (
                id SERIAL PRIMARY KEY,
                claim_a_id UUID NOT NULL,
                claim_b_id UUID NOT NULL,
                severity TEXT NOT NULL,
                conflict_type TEXT NOT NULL,
                reasoning TEXT NOT NULL,
                confidence FLOAT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)
        conn.commit()
        print("Table 'contradictions' created successfully.")
        
        # Insert a mock contradiction if empty to give the UI something to show
        cur.execute("SELECT COUNT(*) FROM contradictions;")
        if cur.fetchone()[0] == 0:
            print("Injecting a demo contradiction...")
            # Grab two existing claims from the DB to link them
            cur.execute("SELECT claim_id, source_sentence FROM claims LIMIT 2;")
            claims = cur.fetchall()
            
            if len(claims) >= 2:
                c1_id = claims[0][0]
                c2_id = claims[1][0]
                
                cur.execute("""
                    INSERT INTO contradictions 
                    (claim_a_id, claim_b_id, severity, conflict_type, reasoning, confidence)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (c1_id, c2_id, 'High', 'Metric', 'Demo conflict: Values differ by 20% in the same reporting period.', 0.95))
                conn.commit()
                print("Demo contradiction injected using real claim IDs!")
                
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    init_conflicts()

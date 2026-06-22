import psycopg2

CONN_STR = "postgresql://postgres:***REMOVED***@db.fpxgspimlsgiuvalwcmx.supabase.co:5432/postgres"

def clean_db():
    print("Connecting to Supabase for rigorous cleanup...")
    try:
        conn = psycopg2.connect(CONN_STR)
        cur = conn.cursor()
        
        # 1. Delete rows where metric_value exists but metric_unit is null/unspecified
        cur.execute("""
            DELETE FROM claims
            WHERE metric_value IS NOT NULL 
              AND (metric_unit IS NULL OR LOWER(metric_unit) IN ('unspecified', 'none', 'null', ''));
        """)
        deleted_units = cur.rowcount
        
        # 2. Delete rows with excessively high vagueness score (> 0.8)
        cur.execute("""
            DELETE FROM claims
            WHERE vagueness_score > 0.8;
        """)
        deleted_vague = cur.rowcount
        
        # 3. Apply fallback location to claims missing locations
        cur.execute("""
            UPDATE claims
            SET location_scope = 'Global'
            WHERE location_scope IS NULL OR location_scope = '';
        """)
        updated_locs = cur.rowcount
        
        conn.commit()
        print(f"[SUCCESS] Deleted {deleted_units} claims with invalid/unspecified metric units.")
        print(f"[SUCCESS] Deleted {deleted_vague} highly vague claims.")
        print(f"[SUCCESS] Applied 'Global' fallback location to {updated_locs} claims.")
        
        cur.execute("SELECT count(*) FROM claims;")
        remaining = cur.fetchone()[0]
        print(f"[INFO] Total groundable claims remaining in knowledge base: {remaining}")
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error during cleanup: {e}")

if __name__ == "__main__":
    clean_db()

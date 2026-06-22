import os
import re
import psycopg2
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Load .env from the project root (backend/scripts/ -> project root).
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# Connection config read from env (do NOT hardcode credentials in source).
CONN_STR = os.getenv("DATABASE_URL")
if not CONN_STR:
    raise SystemExit("DATABASE_URL not set. Add it to your .env before running this script.")

# Resolve relative to this file (backend/scripts/ -> backend/ESG_Reports/) for portability.
ESG_DIR = Path(__file__).resolve().parents[1] / "ESG_Reports"

def infer_metadata(filename: str) -> dict:
    stem = Path(filename).stem
    
    # Try to extract year
    year_match = re.search(r'20\d{2}', stem)
    fy_match = re.search(r'(\d{4})-(\d{2})', stem)   # e.g. 2023-24
    
    if fy_match:
        year = int(fy_match.group(1)) + 1  # FY2023-24 -> 2024
    elif year_match:
        year = int(year_match.group(0))
    else:
        year = 2024

    # Company name extraction
    name_part = stem
    name_part = re.sub(r'[-_]?\d{4}[-_]?\d{0,2}', ' ', name_part)
    for suffix in ['esg', 'sustainability', 'environmental', 'report', 'brsr', 'business', 'responsibility', 'and', 'of']:
        name_part = re.sub(rf'[-_\s]{suffix}', ' ', name_part, flags=re.I)
    name_part = re.sub(r'[-_]+', ' ', name_part).strip()
    company_name = ' '.join(w.capitalize() for w in name_part.split() if len(w) > 1)
    
    if not company_name or len(company_name) < 3:
        # Fallback for "business-responsibility..."
        if "business" in stem.lower(): company_name = "Tata Power" # Known from previous session
        else: company_name = stem[:20].title()

    company_id = re.sub(r'[^a-z0-9]+', '_', company_name.lower()).strip('_')
    report_id = f"{company_id}_{year}"

    return {
        "report_id": report_id,
        "company_id": company_id,
        "company_name": company_name,
        "report_year": year,
        "file_path": str(filename)
    }

def populate():
    print(f"Scanning reports in {ESG_DIR}...")
    pdf_files = list(ESG_DIR.glob("*.pdf"))
    
    try:
        conn = psycopg2.connect(CONN_STR)
        cur = conn.cursor()
        
        for pdf in pdf_files:
            meta = infer_metadata(pdf.name)
            print(f"Processing: {meta['company_name']} ({meta['report_year']})")
            
            # Count claims for this report
            cur.execute("SELECT count(*) FROM claims WHERE company_id = %s AND report_year = %s;", 
                        (meta['company_id'], meta['report_year']))
            claim_count = cur.fetchone()[0]
            
            # Upsert into reports
            cur.execute("""
                INSERT INTO reports (report_id, company_id, company_name, report_year, file_path, claim_count)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (report_id) DO UPDATE SET
                    claim_count = EXCLUDED.claim_count,
                    file_path = EXCLUDED.file_path;
            """, (meta['report_id'], meta['company_id'], meta['company_name'], 
                  meta['report_year'], str(pdf), claim_count))
            
            # Update claims that might be missing these fields but match the report_id pattern
            # (Safety step for ingestion that might have missed metadata)
            cur.execute("""
                UPDATE claims SET 
                    company_id = %s, 
                    company_name = %s, 
                    report_year = %s, 
                    report_id = %s
                WHERE (company_id IS NULL OR company_id = '') 
                AND (source_sentence LIKE %s OR doc_id LIKE %s);
            """, (meta['company_id'], meta['company_name'], meta['report_year'], meta['report_id'],
                  f"%{meta['company_name']}%", f"%{meta['company_id']}%"))

        conn.commit()
        cur.close()
        conn.close()
        print("\n✅ Reports metadata populated successfully.")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    populate()

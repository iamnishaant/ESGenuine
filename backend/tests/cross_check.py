"""
Cross-validation script: Verifies pipeline output against actual PDF content.
"""
import json
import fitz  # PyMuPDF
from pathlib import Path

# Resolve relative to this file (backend/tests/ -> backend/...) for portability.
_BACKEND = Path(__file__).resolve().parents[1]
PDF_PATH = _BACKEND / "ESG_Reports" / "business-responsibility-and-sustainability-report-2023-24.pdf"
OUTPUT_DIR = _BACKEND / "parsed"

doc = fitz.open(PDF_PATH)

# ─── 1. SECTIONS VERIFICATION ───
print("=" * 70)
print("1. SECTIONS VERIFICATION")
print("=" * 70)

with open(OUTPUT_DIR / "08dbf8224013_sections.json", "r", encoding="utf-8") as f:
    sections = json.load(f)

print(f"Total sections parsed: {len(sections)}")
print(f"\nFirst 25 sections:")
for i, s in enumerate(sections[:25]):
    page = s.get("page_number", "?")
    level = s.get("heading_level", "?")
    title = s.get("title", "?")[:80]
    print(f"  [{i:3d}] p.{page:<3} L{level} | {title}")

# ─── 2. TABLE ROWS VERIFICATION ───
print("\n" + "=" * 70)
print("2. TABLE ROWS VERIFICATION")
print("=" * 70)

with open(OUTPUT_DIR / "08dbf8224013_table_rows.json", "r", encoding="utf-8") as f:
    tables = json.load(f)

print(f"Total table rows: {len(tables)}")

# Group by table_id
table_groups = {}
for t in tables:
    tid = t.get("table_id", "unknown")
    if tid not in table_groups:
        table_groups[tid] = []
    table_groups[tid].append(t)

print(f"Total distinct tables: {len(table_groups)}")
print(f"\nTable summary:")
for tid, rows in list(table_groups.items())[:10]:
    page = rows[0].get("page_number", "?")
    cells_sample = rows[0].get("cells", {})
    headers = list(cells_sample.keys())[:5]
    print(f"  {tid} | p.{page} | {len(rows)} rows | Headers: {headers}")

# Show a few full table rows to understand the structure
print(f"\nSample table rows (first 5):")
for i, t in enumerate(tables[:5]):
    print(f"\n  Row {i}: table={t.get('table_id','?')} page={t.get('page_number','?')}")
    for k, v in t.get("cells", {}).items():
        print(f"    '{k}': '{v}'")

# ─── 3. CLAIMS vs ACTUAL PDF CROSS-CHECK ───
print("\n" + "=" * 70)
print("3. CLAIMS vs ACTUAL PDF CROSS-CHECK")
print("=" * 70)

with open(OUTPUT_DIR / "08dbf8224013_claims.json", "r", encoding="utf-8") as f:
    claims = json.load(f)

print(f"Total claims: {len(claims)}")

# Verify 5 specific claims by checking if source_sentence exists at the claimed page
errors = []
verified = 0
for i, claim in enumerate(claims[:15]):
    prov = claim["provenance"]
    human_page_num = prov["page_number"]
    source = prov["source_sentence"][:60]

    # Get actual page text (PyMuPDF is 0-indexed)
    pdf_page_idx = human_page_num - 1
    if 0 <= pdf_page_idx < doc.page_count:
        actual_text = doc[pdf_page_idx].get_text()
        # Check if key words appear on that page
        words = source.split()[:5]
        key_phrase = " ".join(words[:3])
        found = key_phrase.lower() in actual_text.lower()

        status = "[PASS]" if found else "[FAIL]"
        if not found:
            errors.append(f"Claim {i}: '{source}' NOT found on page {human_page_num} (PyMuPDF idx {pdf_page_idx})")
        else:
            verified += 1
        print(f"  Claim {i:2d} | p.{human_page_num:2d} | {status} | {claim['aspect']:15s} | {source}...")

print(f"\nVerified: {verified}/15 claims have matching text on their claimed page")
if errors:
    print(f"Errors ({len(errors)}):")
    for e in errors:
        print(f"  {e}")

# ─── 4. SPECIFIC HIGH-VALUE CLAIM CHECK ───
print("\n" + "=" * 70)
print("4. HIGH-VALUE ENVIRONMENTAL DATA CHECK")
print("=" * 70)

# Page 31 (index 30): Should have Scope 1 emissions = 3,86,71,851 tCO2e
page31_text = doc[30].get_text()
print("Page 31 - GHG Emissions Data:")
if "3,86,71,851" in page31_text:
    print("  [PASS] Scope 1 emissions value (3,86,71,851 tCO2e) found in PDF")
else:
    print("  [FAIL] Scope 1 emissions value NOT found")

if "28,86,646" in page31_text:
    print("  [PASS] Scope 2 emissions value (28,86,646 tCO2e) found in PDF")
else:
    print("  [FAIL] Scope 2 emissions value NOT found")

# Check if any claim captured these values
scope1_claims = [c for c in claims if "scope 1" in c.get("provenance",{}).get("source_sentence","").lower()
                 or "scope 1" in c.get("aspect","").lower()]
print(f"  Claims referencing Scope 1: {len(scope1_claims)}")
for c in scope1_claims:
    print(f"    -> {c['aspect']} | {c['action']} | metric: {c.get('metric')}")

# Page 30 (index 29): Water discharge data
page30_text = doc[29].get_text()
print("\nPage 30 - Water Discharge Data:")
if "1,24,89,82,509" in page30_text:
    print("  [PASS] Water discharge value found in PDF")
else:
    print("  [FAIL] Water discharge value NOT found")

water_claims = [c for c in claims if c["aspect"] == "water"]
print(f"  Water claims extracted: {len(water_claims)}")
for c in water_claims[:3]:
    src = c["provenance"]["source_sentence"][:60]
    print(f"    -> {c['aspect']} | {c['action']} | {src}...")

# ─── 5. MISSING CRITICAL DATA ───
print("\n" + "=" * 70)
print("5. CRITICAL DATA THE PIPELINE MISSED")
print("=" * 70)

# Check what key ESG metrics exist in the PDF but weren't extracted
critical_values = {
    "Scope 1 emissions": "3,86,71,851",
    "Scope 2 emissions": "28,86,646",
    "Water discharge (surface)": "1,24,89,82,509",
    "Water discharge (sea)": "4,53,60,99,593",
    "Fly ash generation": "55,45,589",
    "Net Zero target": "2045",
    "PAT cycle heat rate (CGPL)": "2,253",
    "Trees planted": None,
    "Renewable capacity 40%": "40%",
}

for label, value in critical_values.items():
    # Check if any claim captured this
    found_in_claim = False
    for c in claims:
        src = c["provenance"]["source_sentence"].lower()
        if value and value.lower() in src:
            found_in_claim = True
            break
        if label.lower().split()[0] in src and label.lower().split()[-1] in src:
            found_in_claim = True
            break

    status = "[CAPTURED]" if found_in_claim else "[MISSED]"
    print(f"  {status:12s} | {label}: {value or 'N/A'}")

doc.close()

print("\n" + "=" * 70)
print("CROSS-CHECK COMPLETE")
print("=" * 70)

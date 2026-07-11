"""
Satellite Evidence v2 — batch runner.

Pulls optical_possible claims from the live DB, runs the committed NDVI
pipeline over each, writes results to the satellite_evidence table and a JSON
report. Free APIs only (Nominatim 1 req/s + Planetary Computer anonymous);
geocode results are disk-cached so re-runs cost nothing.

    python backend/scripts/run_satellite_checks.py [--limit N] [--dry-run]
"""
import argparse
import json
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT.parent / ".env")
sys.path.insert(0, str(ROOT / "src"))

from verification.satellite_evidence import verify_claim  # noqa: E402


def _db():
    import psycopg2
    import psycopg2.extras
    url = None
    for line in open(ROOT.parent / ".env", encoding="utf-8"):
        m = re.match(r'DATABASE_URL="?([^"\n]+)"?', line.strip())
        if m:
            url = m.group(1)
    conn = psycopg2.connect(url, connect_timeout=15)
    return conn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="check at most N claims")
    ap.add_argument("--dry-run", action="store_true", help="no DB writes")
    ap.add_argument("--out", default=str(ROOT / "test_results" / "satellite_checks.json"))
    args = ap.parse_args()

    import psycopg2.extras
    conn = _db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""select claim_id, report_id, report_year, company_name, location_text,
                          normalized_aspect, source_sentence
                   from claims where observability_type='optical_possible'
                   order by report_id, claim_id""")
    claims = [dict(r) for r in cur.fetchall()]
    if args.limit:
        claims = claims[:args.limit]
    print(f"[sat] {len(claims)} optical_possible claims to check")

    results = []
    counts = {}
    for i, c in enumerate(claims, 1):
        res = verify_claim(c)
        results.append(res)
        counts[res["verdict"]] = counts.get(res["verdict"], 0) + 1
        tag = res["verdict"] + (f" ({res.get('reason')})" if res.get("reason") else "")
        print(f"[sat] {i}/{len(claims)} {c['company_name'][:10]:>10} | "
              f"{(c['location_text'] or '-')[:30]:<30} -> {tag}", flush=True)
        # Persist real checks; skip rows the pipeline never looked at (wrong
        # aspect / junk location) so the table stays an evidence log, not a dump.
        skip_reasons = ("no_optical_expectation_for_aspect", "no_geocodable_location")
        if not args.dry_run and res.get("reason") not in skip_reasons:
            cur.execute(
                """insert into satellite_evidence
                   (claim_id, report_id, verdict, reason, ndvi_delta, z_score, bundle, bundle_sha256)
                   values (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (res["claim_id"], res.get("report_id"), res["verdict"], res.get("reason"),
                 res.get("ndvi_delta"), res.get("z_score"),
                 json.dumps(res, default=str), res["bundle_sha256"]))
            conn.commit()

    Path(args.out).write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
    print(f"[sat] verdicts: {counts}")
    print(f"[sat] wrote {args.out}")
    conn.close()


if __name__ == "__main__":
    main()

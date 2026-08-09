"""
Satellite Evidence v2 — batch runner.

Pulls optical_possible claims from the live DB, runs the committed NDVI
pipeline over each, writes results to the satellite_evidence table and a JSON
report. Uses the Supabase REST API (IPv4-backed via Cloudflare) rather than the
direct Postgres host — the db.*.supabase.co hostname is IPv6-only and vanishes
whenever the local network loses IPv6. Free APIs only (Nominatim 1 req/s +
Planetary Computer anonymous); geocode results are disk-cached.

    python backend/scripts/run_satellite_checks.py [--limit N] [--dry-run]
"""
import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT.parent / ".env")
sys.path.insert(0, str(ROOT / "src"))

from verification.satellite_evidence import verify_claim  # noqa: E402


def _sb():
    import os
    from supabase import create_client
    # Writes satellite_evidence — needs the RLS-bypassing service-role key once
    # 2026-08-09_enable_rls.sql is applied. Anon fallback for pre-migration use.
    return create_client(os.environ["VITE_SUPABASE_URL"],
                         os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
                         or os.environ["VITE_SUPABASE_PUBLISHABLE_KEY"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="check at most N claims")
    ap.add_argument("--dry-run", action="store_true", help="no DB writes")
    ap.add_argument("--out", default=str(ROOT / "test_results" / "satellite_checks.json"))
    args = ap.parse_args()

    sb = _sb()
    claims = []
    page = 0
    while True:  # REST caps at 1000 rows/request — page through
        r = (sb.table("claims")
             .select("claim_id,report_id,report_year,time_bucket,company_name,"
                     "location_text,normalized_aspect,source_sentence")
             .eq("observability_type", "optical_possible")
             .order("report_id").order("claim_id")
             .range(page * 1000, page * 1000 + 999).execute())
        claims.extend(r.data or [])
        if not r.data or len(r.data) < 1000:
            break
        page += 1
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
        print(f"[sat] {i}/{len(claims)} {(c.get('company_name') or '?')[:10]:>10} | "
              f"{(c.get('location_text') or '-')[:30]:<30} -> {tag}", flush=True)
        # Persist real checks; skip rows the pipeline never looked at (wrong
        # aspect / junk location) so the table stays an evidence log, not a dump.
        skip_reasons = ("no_optical_expectation_for_aspect", "no_geocodable_location")
        if not args.dry_run and res.get("reason") not in skip_reasons:
            try:
                sb.table("satellite_evidence").insert({
                    "claim_id": res["claim_id"], "check_key": res.get("check_key"),
                    "report_id": res.get("report_id"),
                    "verdict": res["verdict"], "reason": res.get("reason"),
                    "ndvi_delta": res.get("ndvi_delta"), "z_score": res.get("z_score"),
                    "bundle": json.loads(json.dumps(res, default=str)),
                    "bundle_sha256": res["bundle_sha256"],
                }).execute()
            except Exception as e:
                print(f"[sat]   insert failed for {res['claim_id']}: {str(e)[:100]}")

    Path(args.out).write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
    print(f"[sat] verdicts: {counts}")
    print(f"[sat] wrote {args.out}")


if __name__ == "__main__":
    main()

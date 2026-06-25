"""
Backfill observability_type for claims rows that predate the column
(migration 2026-06-25_observability_type.sql).

obs_type depends only on has_metric / has_time / has_location (booleans) plus the raw
aspect keyword match — all of which are stored on the row — so this reproduces exactly
what a fresh ingest would compute (location.specificity only affects the groundability
*score*, not the type). We call the real GroundabilityClassifier.score() via lightweight
shim objects so there is zero logic drift from the ingest path.

Idempotent: only rows WHERE observability_type IS NULL are touched.

Usage:
    python backend/scripts/backfill_observability_type.py            # apply
    python backend/scripts/backfill_observability_type.py --dry-run  # preview only
"""
import os
import sys
import collections
from pathlib import Path
from types import SimpleNamespace as NS

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Make `extractors` importable (backend/src on path), regardless of CWD.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
try:
    from extractors.models import GroundabilityClassifier
except ImportError:  # pragma: no cover
    from src.extractors.models import GroundabilityClassifier

load_dotenv()

_SELECT = """
    SELECT claim_id, metric_value, time_start, time_end,
           location_text, location_scope, aspect
    FROM claims
    WHERE observability_type IS NULL
"""


def _obs_type(row: dict) -> str:
    """Reconstruct the minimal claim shape score() reads, return its observability_type."""
    claim = NS(
        metric=NS(value=row["metric_value"]),
        time=NS(start_date=row["time_start"], end_date=row["time_end"]),
        location=NS(raw_text=row["location_text"], specificity=row["location_scope"]),
        aspect=row["aspect"],
    )
    _score, obs_type = GroundabilityClassifier.score(claim)
    return obs_type


def main(dry_run: bool) -> None:
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise SystemExit("DATABASE_URL not set in environment / .env")

    conn = psycopg2.connect(dsn, connect_timeout=15)
    conn.autocommit = False
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(_SELECT)
            rows = cur.fetchall()

        updates = [(_obs_type(r), r["claim_id"]) for r in rows]
        dist = collections.Counter(o for o, _ in updates)
        print(f"rows needing backfill: {len(updates)}")
        for k, v in sorted(dist.items(), key=lambda kv: -kv[1]):
            print(f"  {k:<22} {v}")

        if dry_run:
            print("dry-run: no rows written.")
            return
        if not updates:
            print("nothing to backfill.")
            return

        with conn.cursor() as cur:
            cur.executemany(
                "UPDATE claims SET observability_type = %s "
                "WHERE claim_id = %s AND observability_type IS NULL",
                updates,
            )
            written = cur.rowcount
        conn.commit()

        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM claims WHERE observability_type IS NULL")
            remaining = cur.fetchone()[0]
        print(f"updated rows: {written}; still NULL: {remaining}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)

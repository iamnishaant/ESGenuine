"""
Resumable claim checkpoint.

A long extraction run makes dozens of LLM calls (one per section-window / table-page).
Without checkpointing, a single crash — a network read-timeout, a bad-JSON reply, a
killed process — discards every claim produced so far and forces a full, credit-burning
re-run. This records each completed LLM unit's claims as a **line-atomic** JSON record,
so:

  * a crash loses at most the one unit that was mid-flight (its line is never written);
  * a re-run RESUMES — units already in the checkpoint are skipped, not re-paid for;
  * `--force` clears the checkpoint to run from scratch.

On load we "scan through all stored" and keep only good data:
  * a truncated/corrupt trailing line (crash mid-write) is dropped -> that unit re-runs;
  * any individual stored claim that no longer validates against the model is dropped,
    so a bad claim can never be silently carried forward into the final output.

Unit keys are namespaced by the producing path ("sec::<i>" for section windows,
"tbl::<page>" for table pages) so the section and table pipelines can safely share one
checkpoint file.
"""
import json
import os
import threading
from typing import List, Set, Tuple

from .models import ExtractedClaim


class ClaimCheckpoint:
    def __init__(self, path: str):
        self.path = str(path)
        self._lock = threading.Lock()

    def load(self) -> Tuple[Set[str], List[ExtractedClaim]]:
        """Return (done_unit_keys, valid_claims). Drops corrupt lines + invalid claims."""
        done: Set[str] = set()
        claims: List[ExtractedClaim] = []
        if not os.path.exists(self.path):
            return done, claims

        dropped_lines = dropped_claims = 0
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    unit = rec["unit"]
                    raws = rec.get("claims", [])
                except Exception:
                    dropped_lines += 1          # truncated/corrupt tail -> unit re-runs
                    continue
                for d in raws:
                    try:
                        claims.append(ExtractedClaim.model_validate(d))
                    except Exception:
                        dropped_claims += 1      # bad claim never carried forward
                done.add(unit)

        if dropped_lines or dropped_claims:
            print(f"[Checkpoint] scan: dropped {dropped_lines} corrupt line(s), "
                  f"{dropped_claims} invalid claim(s).")
        return done, claims

    def record(self, unit: str, claims: List[ExtractedClaim]) -> None:
        """Append one completed unit's claims as a single line (atomic + fsync'd)."""
        rec = {"unit": unit, "claims": [c.model_dump(mode="json") for c in claims]}
        line = json.dumps(rec, ensure_ascii=False, default=str)
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
                os.fsync(f.fileno())

    def clear(self) -> None:
        try:
            os.remove(self.path)
        except OSError:
            pass

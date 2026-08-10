"""
ESGenuine — GOLD-SET TAMPER GATE (audit 2026-08-10, roadmap 6.3)
================================================================

Fails CI when a gold LABEL changes without an explicit, documented version bump.

WHY THIS EXISTS
---------------
The 2026-08-10 audit found ground truth being edited in the same commits as the system
changes being measured against it:

  * `48555ea` "ontology round 2 (Shell gap classes) — out-of-sample 81.1 -> 89.7"
    added 14 taxonomy nodes AND rewrote 2 Shell gold labels to match the new node names
    (`emissions.methane_reporting` -> `emissions.methane`,
     `waste.recycling` -> `waste.recycled`).
  * `95e1f20` (ontology round 3) rewrote 4 Tata gold labels to child nodes introduced in
    that same commit.

Each individual edit had a defensible rationale. That is exactly why a review cannot be
relied on to catch them: they look like housekeeping in a large diff. The aggregate is
six labels moved toward the system, and a measurement that quietly stopped being
independent of the thing it measures.

A hash gate makes the edit IMPOSSIBLE TO MAKE SILENTLY. Changing a label is still
allowed — annotation genuinely does improve — but it now costs a deliberate manifest
update, which lands in the diff as a statement of intent rather than a side effect.

WHAT IS HASHED
--------------
Only the semantic label content: for every claim, the fields that scoring reads
(`claim_id`, `is_esg_claim`, `aspect`, `value`, `value_ambiguous`, `unit_base`,
`claim_type`), canonicalised and sorted. Deliberately EXCLUDED:

  * `_meta`      — so documentation, provenance and audit notes can be improved freely
  * `note`       — free-text annotator commentary, not scored
  * file layout  — indentation and key order do not affect the hash

So this gate ignores everything that cannot move a number, and trips on everything that
can.

WHEN IT FAILS
-------------
The failure message prints the exact per-field diff. Then either revert the label, or —
if the relabel is genuinely correct — record it:

    python backend/tests/test_gold_integrity.py --update

...which rewrites the manifest, and REQUIRES you to describe the change in
`tests/eval/GOLD_CHANGELOG.md`. A manifest update with no changelog entry also fails.
"""
import hashlib
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_EVAL = _HERE / "eval"
_MANIFEST = _EVAL / "GOLD_HASHES.json"
_CHANGELOG = _EVAL / "GOLD_CHANGELOG.md"

GOLD_FILES = ["gold_set.json", "gold_set_docling_tata.json", "gold_set_shell_v03.json"]

# Exactly the fields run_evaluation.py reads. A change to any of them can move a score;
# anything not listed here provably cannot.
SCORED_FIELDS = ("claim_id", "is_esg_claim", "aspect", "value",
                 "value_ambiguous", "unit_base", "claim_type")


def _labels(path: Path) -> dict:
    """{claim_id: {scored field: value}} — the semantic content, stripped of everything else."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for c in doc["claims"]:
        out[c["claim_id"]] = {f: c.get(f) for f in SCORED_FIELDS}
    return out


def _digest(path: Path) -> str:
    payload = json.dumps(_labels(path), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_manifest() -> dict:
    if not _MANIFEST.exists():
        return {}
    return json.loads(_MANIFEST.read_text(encoding="utf-8"))


def _diff(expected_labels: dict, actual_labels: dict) -> list:
    lines = []
    for cid in sorted(set(expected_labels) | set(actual_labels)):
        a, b = expected_labels.get(cid), actual_labels.get(cid)
        if a is None:
            lines.append(f"    + ADDED   {cid}")
        elif b is None:
            lines.append(f"    - REMOVED {cid}")
        elif a != b:
            for f in SCORED_FIELDS:
                if a.get(f) != b.get(f):
                    lines.append(f"    ~ {cid}  {f}: {a.get(f)!r} -> {b.get(f)!r}")
    return lines


def test_gold_labels_unchanged():
    """Every gold file's scored labels match the committed manifest."""
    manifest = _load_manifest()
    assert manifest, (
        f"No gold manifest at {_MANIFEST.relative_to(_HERE.parent)}. "
        f"Create it with:  python backend/tests/test_gold_integrity.py --update")

    failures = []
    for name in GOLD_FILES:
        path = _EVAL / name
        entry = manifest.get(name)
        assert entry, f"{name} is not in the manifest — add it via --update"

        actual = _digest(path)
        if actual == entry["sha256"]:
            continue

        detail = "\n".join(_diff(entry.get("labels", {}), _labels(path))) or "    (no field-level diff)"
        failures.append(
            f"\n  {name}: GOLD LABELS CHANGED\n"
            f"    manifest sha256 : {entry['sha256'][:16]}...  (version {entry.get('version')})\n"
            f"    actual   sha256 : {actual[:16]}...\n"
            f"{detail}")

    assert not failures, (
        "Ground truth was modified.\n"
        + "".join(failures)
        + "\n\n  Ground truth must not drift toward the system it measures. Either revert,\n"
          "  or if the relabel is genuinely correct, record it deliberately:\n"
          "      python backend/tests/test_gold_integrity.py --update\n"
          "  and describe WHY in tests/eval/GOLD_CHANGELOG.md (required — the manifest\n"
          "  and the changelog are checked against each other).\n")


def test_manifest_has_changelog():
    """A manifest version must be explained. Prevents --update becoming a silent rubber stamp."""
    manifest = _load_manifest()
    if not manifest:
        return
    assert _CHANGELOG.exists(), (
        f"{_CHANGELOG.name} is missing. Every gold manifest version needs a written "
        f"rationale, or the tamper gate is just a speed bump.")
    text = _CHANGELOG.read_text(encoding="utf-8")
    missing = [f"{name} v{e.get('version')}" for name, e in manifest.items()
               if f"{name} v{e.get('version')}" not in text]
    assert not missing, (
        "Manifest versions with no changelog entry: " + ", ".join(missing)
        + f"\n  Add a section to {_CHANGELOG.name} saying what changed and why.")


def _update():
    manifest = _load_manifest()
    for name in GOLD_FILES:
        path = _EVAL / name
        old = manifest.get(name, {})
        new_digest = _digest(path)
        if old.get("sha256") == new_digest:
            print(f"  unchanged  {name}  (v{old.get('version')})")
            continue
        version = int(old.get("version", 0)) + 1
        manifest[name] = {
            "version": version,
            "sha256": new_digest,
            "claims": len(_labels(path)),
            "labels": _labels(path),
        }
        print(f"  UPDATED    {name}  -> v{version}  {new_digest[:16]}...")
        print(f"             now add a '{name} v{version}' section to {_CHANGELOG.name}")
    _MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"\nwrote {_MANIFEST}")


if __name__ == "__main__":
    if "--update" in sys.argv:
        _update()
    else:
        test_gold_labels_unchanged()
        test_manifest_has_changelog()
        print("gold labels match the manifest")

"""
ESGenuine — Docling layout-aware table extraction (app-venv side).

Root-cause fix for the extraction ceiling (external_evaluation_notes.md #1): the
PyMuPDF+pdfplumber path flattens multi-column tables into headerless number-soup,
so the LLM extracts ghosts (wrong scope, hallucinated values, diversity->biodiversity).
Docling's layout model + TableFormer recover the real table structure (headers, row
labels, units, year columns).

Docling is HEAVY and pulls its own torch, so it is kept in an ISOLATED venv
(`.venv-docling`) and driven here as a subprocess — it is never imported into the
app venv. Output matches the VLM path exactly: [{"page_number": int, "markdown": str}],
fed straight into ClaimExtractor.extract_from_table_markdown().

Enable via  USE_DOCLING_TABLES=1  (see pipeline.py). Gracefully returns [] when the
isolated venv is absent, so the pipeline falls back to the structured pdfplumber path.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional, Set

_REPO = Path(__file__).resolve().parents[3]   # backend/src/parsers/ -> repo root
_WORKER = Path(__file__).with_name("_docling_worker.py")
_CACHE_DIR = Path(os.environ.get("DOCLING_CACHE_DIR", _REPO / "backend" / ".docling_cache"))


class DoclingTableExtractor:
    def __init__(self, docling_python: str = None, timeout: int = None):
        self.docling_python = docling_python or os.environ.get("DOCLING_PYTHON") or self._default_python()
        self.timeout = timeout or int(os.environ.get("DOCLING_TIMEOUT", "1800"))

    @staticmethod
    def _default_python() -> str:
        """Locate the isolated docling venv's interpreter (Windows / POSIX)."""
        win = _REPO / ".venv-docling" / "Scripts" / "python.exe"
        posix = _REPO / ".venv-docling" / "bin" / "python"
        return str(win if win.exists() else posix)

    def available(self) -> bool:
        return Path(self.docling_python).exists() and _WORKER.exists()

    @staticmethod
    def _cache_key(pdf_path: str, pages: Optional[Set[int]]) -> Path:
        """Cache by file content hash + page selection. Docling conversion is minutes
        of CPU per report; the same PDF was being re-converted on every run."""
        h = hashlib.sha256(Path(pdf_path).read_bytes()).hexdigest()[:16]
        sig = "all" if not pages else "p" + "-".join(str(p) for p in sorted(pages))
        return _CACHE_DIR / f"{h}_{sig}.json"

    def extract(self, pdf_path: str, pages: Optional[Set[int]] = None) -> List[Dict[str, Any]]:
        """Return [{'page_number': int, 'markdown': str}] for pages with tables.
        `pages`: optional page-number set — converts ONLY those pages (fast targeted
        runs). Results are cached on disk keyed by (file hash, page selection)."""
        if not self.available():
            print(f"[Docling] isolated venv not found at {self.docling_python}; "
                  f"skipping (pipeline will fall back to pdfplumber).")
            return []

        cache = self._cache_key(pdf_path, pages)
        if cache.exists():
            tables = json.loads(cache.read_text(encoding="utf-8"))
            print(f"[Docling] cache hit ({cache.name}): {len(tables)} table-page(s).")
            return tables

        out_fd, out_path = tempfile.mkstemp(suffix=".json", prefix="docling_")
        os.close(out_fd)
        try:
            cmd = [self.docling_python, str(_WORKER), pdf_path, out_path]
            if pages:
                cmd.append(",".join(str(p) for p in sorted(pages)))
            proc = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=self.timeout,
            )
            # Surface the worker's own log lines even on success — silent per-page
            # preprocess failures inside docling are only visible there.
            for line in (proc.stderr or "").splitlines():
                if "[docling_worker]" in line or "failed" in line.lower():
                    print(f"  {line.strip()}")
            if proc.returncode != 0:
                print(f"[Docling] worker exited {proc.returncode}.")
                return []
            with open(out_path, encoding="utf-8") as f:
                tables = json.load(f)
            print(f"[Docling] {os.path.basename(pdf_path)}: {len(tables)} table-page(s).")
            try:
                _CACHE_DIR.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(tables, ensure_ascii=False), encoding="utf-8")
            except OSError:
                pass   # cache is best-effort
            return tables
        except subprocess.TimeoutExpired:
            print(f"[Docling] timed out after {self.timeout}s on {os.path.basename(pdf_path)}.")
            return []
        except Exception as e:
            print(f"[Docling] failed: {e}")
            return []
        finally:
            try:
                os.remove(out_path)
            except OSError:
                pass


if __name__ == "__main__":
    # Smoke test (no LLM): dump Docling's table markdown for a PDF.
    ex = DoclingTableExtractor()
    print(f"docling_python: {ex.docling_python}  available={ex.available()}")
    if len(sys.argv) > 1:
        res = ex.extract(sys.argv[1])
        for t in res[:4]:
            print(f"\n--- page {t['page_number']} ---\n{t['markdown'][:1500]}")
        print(f"\n[{len(res)} table-pages total]")

"""
ESGenuine — Phase 2: VLM-based table extraction (document-AI).

Replaces the noisy pdfplumber table scan (existing_issues #5: ~45% junk rows).
Strategy: detect pages that contain real tables, render each to an image, and use
an NVIDIA vision-language model to read every table as clean GitHub-markdown —
preserving headers, numbers, units, and current-vs-previous-year columns.

Output feeds ClaimExtractor.extract_from_table_markdown() -> structured claims.
"""
import os
import base64
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any

import fitz          # PyMuPDF (render)
import pdfplumber    # table-page detection
import requests


class VLMTableExtractor:
    def __init__(self, model: str = None, dpi: int = None, max_pages: int = 0, max_workers: int = None):
        self.model = model or os.environ.get("NVIDIA_VLM_MODEL", "nvidia/nemotron-nano-12b-v2-vl")
        self.dpi = int(dpi or os.environ.get("VLM_DPI", "110"))
        self.max_pages = max_pages  # cap number of table pages (0 = all)
        self.max_workers = int(max_workers or os.environ.get("VLM_CONCURRENCY", "3"))
        self.key = os.environ.get("NVIDIA_API_KEY")
        self.url = "https://integrate.api.nvidia.com/v1/chat/completions"

    # ── table-page detection (cheap pdfplumber pass) ──
    def find_table_pages(self, pdf_path: str) -> List[int]:
        pages: List[int] = []
        with pdfplumber.open(pdf_path) as pdf:
            for i, pg in enumerate(pdf.pages):
                try:
                    tabs = pg.find_tables()
                except Exception:
                    continue
                for t in tabs:
                    ext = t.extract()
                    # real table: several rows + at least 2 columns (skips layout fragments)
                    if ext and len(ext) >= 4 and len(ext[0]) >= 2:
                        pages.append(i)
                        break
        return pages

    def _page_png_b64(self, doc, page_idx: int) -> str:
        pix = doc[page_idx].get_pixmap(dpi=self.dpi)
        return base64.b64encode(pix.tobytes("png")).decode()

    def _vlm(self, b64: str) -> str:
        prompt = (
            "Extract EVERY data table on this page as GitHub-flavored markdown tables. "
            "Preserve all numbers, units, and column headers exactly as shown. "
            "If a table shows the current year and a previous year, keep BOTH columns. "
            "Do not summarize or omit rows. Output ONLY the markdown tables, nothing else."
        )
        r = requests.post(
            self.url,
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ]}],
                "max_tokens": 1800,
                "temperature": 0,
            },
            timeout=(15, 180),
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def extract(self, pdf_path: str) -> List[Dict[str, Any]]:
        """Return [{'page_number': int, 'markdown': str}] for every table page."""
        if not self.key:
            print("[VLM] No NVIDIA_API_KEY set; skipping VLM table extraction.")
            return []

        table_pages = self.find_table_pages(pdf_path)
        if self.max_pages:
            table_pages = table_pages[:self.max_pages]
        print(f"[VLM] {len(table_pages)} table pages in {os.path.basename(pdf_path)} "
              f"(model={self.model}, {self.max_workers}-way)")
        if not table_pages:
            return []

        doc = fitz.open(pdf_path)
        imgs = [(pno, self._page_png_b64(doc, pno)) for pno in table_pages]
        doc.close()

        def work(item):
            pno, b64 = item
            try:
                md = self._vlm(b64)
                print(f"  [VLM] page {pno + 1}: {len(md)} chars")
                return {"page_number": pno + 1, "markdown": md}
            except Exception as e:
                print(f"  [VLM] page {pno + 1} failed: {e}")
                return None

        out: List[Dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            for res in ex.map(work, imgs):
                if res:
                    out.append(res)
        return out

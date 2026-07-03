"""
Docling worker — runs INSIDE the isolated `.venv-docling` (its own torch), never
in the app venv. Invoked as a subprocess by `docling_tables.DoclingTableExtractor`.

    <.venv-docling python> _docling_worker.py <pdf_path> <out_json> [pages]

`pages` (optional): comma-separated page numbers — converts ONLY the contiguous
runs containing them (a 3-page target takes ~1 min instead of a full-doc ~8 min).

Converts a digital PDF into clean, structure-preserving markdown tables and writes
`[{"page_number": int, "markdown": str}]` to <out_json> — the exact shape
ClaimExtractor.extract_from_table_markdown() already consumes (same as the VLM path).

Design notes:
  - OCR is OFF by default (DOCLING_OCR=1 to force on). Digital ESG PDFs have a text
    layer; RapidOCR full-page rasterization is what OOMs (std::bad_alloc) on CPU.
  - Pages are converted in bounded batches (DOCLING_BATCH, default 16) so memory
    stays flat on 100+ page reports (Shell). page_no from docling is absolute.
"""
import json
import os
import sys


def _page_count(pdf: str) -> int:
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(pdf)
    try:
        return len(doc)
    finally:
        doc.close()


def _is_data_table(md: str) -> bool:
    """Keep only tables that carry numeric data. Docling also extracts layout/nav/index
    tables (e.g. a report's topic grid) — those have no numbers and, fed to the LLM,
    yield fabricated `0.0 unspecified` claims. Require >=2 body cells containing a digit."""
    import re
    numeric_cells = 0
    for line in md.splitlines():
        if not line.strip().startswith("|") or set(line.strip()) <= {"|", "-", " ", ":"}:
            continue  # not a row / separator row
        for cell in line.split("|"):
            if re.search(r"\d", cell):
                numeric_cells += 1
                if numeric_cells >= 2:
                    return True
    return False


def _convert_range(pdf: str, lo: int, hi: int, ocr: bool):
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    opts = PdfPipelineOptions()
    opts.do_ocr = ocr
    opts.do_table_structure = True
    opts.table_structure_options.do_cell_matching = True

    conv = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
    )
    res = conv.convert(pdf, page_range=(lo, hi))
    doc = res.document

    by_page = {}
    for tbl in doc.tables:
        try:
            pno = tbl.prov[0].page_no
        except Exception:
            pno = None
        if pno is None:
            continue
        try:
            md = tbl.export_to_markdown(doc)      # doc arg required in recent docling
        except TypeError:
            md = tbl.export_to_markdown()
        except Exception:
            continue
        if md and md.strip() and _is_data_table(md):
            by_page.setdefault(pno, []).append(md.strip())
    return by_page


def _ranges(pages, batch):
    """Group wanted pages into contiguous runs, split to <=batch-size chunks."""
    runs = []
    for p in sorted(pages):
        if runs and p == runs[-1][1] + 1 and (p - runs[-1][0]) < batch:
            runs[-1] = (runs[-1][0], p)
        else:
            runs.append((p, p))
    return runs


def main():
    pdf, out_path = sys.argv[1], sys.argv[2]
    want = {int(p) for p in sys.argv[3].split(",")} if len(sys.argv) > 3 and sys.argv[3].strip() else None
    ocr = os.environ.get("DOCLING_OCR", "0") == "1"
    # 8, not 16: docling's per-conversion memory grows with the page range, and on
    # larger batches the TAIL pages fail preprocess silently (observed: 16-page
    # batches lost pages 12-16 / 27-32 of a 42-page report; an 8-page range kept all).
    batch = int(os.environ.get("DOCLING_BATCH", "8"))

    n = _page_count(pdf)
    merged = {}

    if want:
        # Targeted mode: convert only the runs containing wanted pages.
        for lo, hi in _ranges({p for p in want if 1 <= p <= n}, batch):
            try:
                got = _convert_range(pdf, lo, hi, ocr)
                for pno, mds in got.items():
                    if pno in want:
                        merged.setdefault(pno, []).extend(mds)
                sys.stderr.write(f"[docling_worker] range {lo}-{hi}: tables on pages {sorted(got)}\n")
            except Exception as e:
                sys.stderr.write(f"[docling_worker] range {lo}-{hi} failed: {e}\n")
        _write(merged, out_path, n)
        return

    lo = 1
    while lo <= n:
        hi = min(lo + batch - 1, n)
        try:
            got = _convert_range(pdf, lo, hi, ocr)
            for pno, mds in got.items():
                merged.setdefault(pno, []).extend(mds)
            sys.stderr.write(f"[docling_worker] batch {lo}-{hi}: tables on pages {sorted(got)}\n")
        except Exception as e:
            sys.stderr.write(f"[docling_worker] batch {lo}-{hi} failed: {e}\n")
        lo = hi + 1

    _write(merged, out_path, n)


def _write(merged, out_path, n):
    tables = [
        {"page_number": pno, "markdown": "\n\n".join(mds)}
        for pno, mds in sorted(merged.items())
    ]
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(tables, f, ensure_ascii=False)
    sys.stderr.write(f"[docling_worker] {len(tables)} table-page(s) from {n} pages -> {out_path}\n")


if __name__ == "__main__":
    main()

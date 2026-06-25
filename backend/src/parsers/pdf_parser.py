"""
ESGenuine — Week 2: Production Document Parsing Pipeline
================================================================

8-Step Layered Pipeline:

  Step 1: PDF Structural Extraction (PyMuPDF + pdfplumber → raw_blocks)
  Step 2: Layout Classification (heading/paragraph/table/list/caption/footnote)
  Step 3: Section Hierarchy Reconstruction (document tree via NetworkX)
  Step 4: Sentence Segmentation (spaCy)
  Step 5: Table Extraction (structured rows with units)
  Step 6: Claim Candidate Detection (rule-based filtering)
  Step 7: Context Window Construction (semantic chunks — only here)
  Step 8: Provenance Linking (page/bbox/sentence/section/table_ref)

Architecture:
  PDF → structured blocks → document graph → sentences → candidate claims → chunking
  NOT:
  PDF → chunks
"""

import fitz  # PyMuPDF
import pdfplumber
import spacy
import json
import hashlib
import re
import statistics
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any, Tuple
from pathlib import Path
from collections import defaultdict

try:
    from ftfy import fix_text
except ImportError:
    def fix_text(s):  # graceful no-op if ftfy is unavailable
        return s

try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False
    print("[Warning] networkx not installed. Document graph will use dict fallback.")


class PDFValidationError(Exception):
    """Raised when a PDF cannot be processed (encrypted, corrupt, or empty).

    Lets callers (e.g. the API) return a clear 4xx instead of a generic 500.
    """
    pass


# ══════════════════════════════════════════════
# DATA MODELS (Layered, not flat)
# ══════════════════════════════════════════════

@dataclass
class BBox:
    x0: float
    y0: float
    x1: float
    y1: float

@dataclass
class RawBlock:
    """Step 1 output: raw extracted block with font metadata."""
    block_id: str
    page_number: int
    text: str
    bbox: BBox
    font_size: float
    font_name: str
    is_bold: bool
    line_count: int

@dataclass
class ClassifiedBlock:
    """Step 2 output: block with layout classification."""
    block_id: str
    page_number: int
    text: str
    bbox: BBox
    font_size: float
    font_name: str
    is_bold: bool
    block_type: str  # heading, paragraph, table, list, caption, footnote, page_header, page_footer

@dataclass
class SectionNode:
    """Step 3 output: a node in the document tree."""
    section_id: str
    title: str
    level: int  # 1 = top-level, 2 = sub-section, etc.
    page_number: int
    children_ids: List[str] = field(default_factory=list)
    block_ids: List[str] = field(default_factory=list)

@dataclass
class Sentence:
    """Step 4 output: individual sentence with full provenance."""
    sentence_id: str
    text: str
    block_id: str
    page_number: int
    section_id: Optional[str]
    section_title: Optional[str]
    bbox: BBox
    sentence_index: int  # position within block

@dataclass
class TableRow:
    """Step 5 output: structured table data."""
    table_id: str
    page_number: int
    row_index: int
    cells: Dict[str, str]  # column_header → cell_value
    section_id: Optional[str] = None

@dataclass
class ClaimCandidate:
    """Step 6 output: sentences likely containing ESG claims."""
    candidate_id: str
    sentence_id: str
    text: str
    score: float  # 0–1 claim likelihood
    features: Dict[str, bool] = field(default_factory=dict)
    page_number: int = 0
    section_id: Optional[str] = None
    section_title: Optional[str] = None
    bbox: Optional[BBox] = None

@dataclass
class SemanticChunk:
    """Step 7 output: context window for ML model input."""
    chunk_id: str
    candidate_id: str
    section_title: str
    context_before: str
    target_sentence: str
    context_after: str
    full_text: str  # concatenated for model input
    page_number: int
    bbox: Optional[BBox] = None

@dataclass
class ProvenanceRecord:
    """Step 8 output: complete provenance chain."""
    chunk_id: str
    sentence_id: str
    block_id: str
    page_number: int
    section_id: Optional[str]
    section_title: Optional[str]
    bbox: BBox
    table_reference: Optional[str] = None


# ══════════════════════════════════════════════
# STEP 0: INGEST & TRIAGE
# ══════════════════════════════════════════════

class Step0_IngestTriage:
    """
    Validate and profile a PDF *before* the heavy parsing steps run.

    Adapted from the ingest/triage stage of a separate pipeline. Produces a
    triage record:
      - file_hash:         full-file SHA-256 (a stable dedup key)
      - page_count:        number of pages
      - extraction_path:   "digital" or "scanned" (scanned PDFs need OCR)
      - avg_chars_per_page
      - flags:             e.g. ["multi_column", "scanned"]
      - warnings:          human-readable advisories

    Raises PDFValidationError for encrypted / corrupt / empty PDFs so the caller
    can return a clear 4xx instead of silently producing an empty result.
    """

    MIN_CHARS_PER_PAGE_DIGITAL = 100   # below this avg → likely a scanned PDF
    SAMPLE_PAGES = 5                    # pages sampled for digital/scan detection

    def run(self, pdf_path: str) -> Dict[str, Any]:
        path = Path(pdf_path)
        if not path.exists():
            raise PDFValidationError(f"File not found: {pdf_path}")

        try:
            doc = fitz.open(str(path))
        except Exception as e:
            raise PDFValidationError(f"Could not open PDF (corrupt or unsupported): {e}")

        try:
            # Encrypted / password-protected (try empty password first)
            if doc.is_encrypted and not doc.authenticate(""):
                raise PDFValidationError("PDF is password-protected / encrypted.")

            page_count = doc.page_count
            if page_count == 0:
                raise PDFValidationError("PDF has 0 pages.")

            # Digital vs scanned: sample text density of the first few pages
            sample_n = min(self.SAMPLE_PAGES, page_count)
            total_chars = sum(len(doc[i].get_text("text").strip()) for i in range(sample_n))
            avg_chars = total_chars / sample_n if sample_n else 0
            extraction_path = "digital" if avg_chars >= self.MIN_CHARS_PER_PAGE_DIGITAL else "scanned"

            # Multi-column heuristic: wide spread of text-block x-origins
            flags: List[str] = []
            for i in range(min(3, page_count)):
                blocks = doc[i].get_text("blocks")
                xs = [b[0] for b in blocks if len(b) > 4 and str(b[4]).strip()]
                if xs:
                    width = doc[i].rect.width or 1
                    if (max(xs) - min(xs)) > width * 0.4:
                        flags.append("multi_column")
                        break
        finally:
            doc.close()

        file_hash = self._hash_file(path)

        warnings: List[str] = []
        if extraction_path == "scanned":
            flags.append("scanned")
            warnings.append(
                f"Low text density (~{avg_chars:.0f} chars/page) — this looks like a "
                f"scanned PDF. Text and claim extraction will be sparse without OCR."
            )

        triage = {
            "file_hash": file_hash,
            "page_count": page_count,
            "extraction_path": extraction_path,
            "avg_chars_per_page": round(avg_chars, 1),
            "flags": flags,
            "warnings": warnings,
        }
        print(f"  [Step 0] Triage: pages={page_count} | path={extraction_path} | "
              f"avg_chars={avg_chars:.0f} | flags={flags}")
        return triage

    @staticmethod
    def _hash_file(path: Path) -> str:
        """Full-file SHA-256 for robust deduplication."""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()


# ══════════════════════════════════════════════
# STEP 1: PDF STRUCTURAL EXTRACTION
# ══════════════════════════════════════════════

class Step1_StructuralExtractor:
    """Extract raw blocks with font metadata and bounding boxes using PyMuPDF."""

    def extract(self, pdf_path: str) -> Tuple[List[RawBlock], Dict[str, Any]]:
        doc = fitz.open(pdf_path)
        blocks: List[RawBlock] = []
        metadata = doc.metadata or {}

        for page_idx, page in enumerate(doc):
            page_blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]

            for block_idx, block in enumerate(page_blocks):
                if block["type"] != 0:  # Skip image blocks
                    continue

                full_text = ""
                max_font_size = 0.0
                font_name = ""
                is_bold = False
                line_count = 0

                for line in block.get("lines", []):
                    line_count += 1
                    for span in line.get("spans", []):
                        full_text += span["text"]
                        if span["size"] > max_font_size:
                            max_font_size = span["size"]
                            font_name = span["font"]
                        if "bold" in span["font"].lower():
                            is_bold = True
                    full_text += "\n"

                # Repair mojibake / double-encoded UTF-8 (e.g. "Indiaâ€™s" -> "India's")
                full_text = fix_text(full_text).strip()
                if not full_text or len(full_text) < 3:
                    continue

                blocks.append(RawBlock(
                    block_id=f"p{page_idx + 1}_b{block_idx}",
                    page_number=page_idx + 1,
                    text=full_text,
                    bbox=BBox(*block["bbox"]),
                    font_size=round(max_font_size, 1),
                    font_name=font_name,
                    is_bold=is_bold,
                    line_count=line_count,
                ))

        doc.close()
        print(f"  [Step 1] Extracted {len(blocks)} raw blocks from {page_idx + 1} pages.")
        return blocks, metadata


# ══════════════════════════════════════════════
# STEP 2: LAYOUT CLASSIFICATION
# ══════════════════════════════════════════════

class Step2_LayoutClassifier:
    """
    Classify each block as: heading, paragraph, table, list, caption, footnote,
    page_header, page_footer.

    Uses rule-based heuristics on font size, position, and text patterns.
    """

    def __init__(self):
        self.page_height = 792  # Default letter size, updated per page

    def classify(self, raw_blocks: List[RawBlock]) -> List[ClassifiedBlock]:
        # Compute median font size for relative comparison
        font_sizes = [b.font_size for b in raw_blocks if b.font_size > 0]
        if not font_sizes:
            median_font = 10.0
        else:
            median_font = statistics.median(font_sizes)

        classified: List[ClassifiedBlock] = []

        for block in raw_blocks:
            block_type = self._classify_block(block, median_font)
            classified.append(ClassifiedBlock(
                block_id=block.block_id,
                page_number=block.page_number,
                text=block.text,
                bbox=block.bbox,
                font_size=block.font_size,
                font_name=block.font_name,
                is_bold=block.is_bold,
                block_type=block_type,
            ))

        # Filter repeated page headers/footers
        classified = self._filter_repeated_headers_footers(classified)

        counts = defaultdict(int)
        for b in classified:
            counts[b.block_type] += 1
        print(f"  [Step 2] Classified: {dict(counts)}")
        return classified

    def _classify_block(self, block: RawBlock, median_font: float) -> str:
        text = block.text.strip()
        lower = text.lower()

        # Page header/footer detection (top/bottom 8% of page)
        if block.bbox.y0 < 60:
            return "page_header"
        if block.bbox.y1 > 750:
            return "page_footer"

        # Footnote detection
        if block.font_size < median_font * 0.75 and block.bbox.y1 > 650:
            return "footnote"

        # Heading detection: larger font, bold, short text
        if (block.font_size > median_font * 1.2 or block.is_bold) and len(text) < 200:
            if block.line_count <= 3:
                return "heading"

        # Caption detection: small text near figures
        if block.font_size < median_font * 0.85 and len(text) < 150:
            if any(kw in lower for kw in ["figure", "chart", "graph", "source:", "note:"]):
                return "caption"

        # List detection: starts with bullet, number, or dash
        if re.match(r'^[\s]*[•\-–—\*\d]+[\.\)]\s', text):
            return "list"

        # Default: paragraph
        return "paragraph"

    def _filter_repeated_headers_footers(self, blocks: List[ClassifiedBlock]) -> List[ClassifiedBlock]:
        """Remove blocks that repeat on every page (page numbers, company names)."""
        header_texts = defaultdict(int)
        footer_texts = defaultdict(int)
        total_pages = max(b.page_number for b in blocks) if blocks else 1

        for b in blocks:
            if b.block_type == "page_header":
                header_texts[b.text.strip()[:50]] += 1
            elif b.block_type == "page_footer":
                footer_texts[b.text.strip()[:50]] += 1

        # If a header/footer appears on >60% of pages, it's a repeater — mark for removal
        repeating = set()
        threshold = max(3, total_pages * 0.6)
        for text, count in {**header_texts, **footer_texts}.items():
            if count >= threshold:
                repeating.add(text)

        filtered = []
        removed = 0
        for b in blocks:
            if b.block_type in ("page_header", "page_footer") and b.text.strip()[:50] in repeating:
                removed += 1
                continue
            filtered.append(b)

        if removed:
            print(f"  [Step 2] Filtered {removed} repeating headers/footers.")
        return filtered


# ══════════════════════════════════════════════
# STEP 3: SECTION HIERARCHY RECONSTRUCTION
# ══════════════════════════════════════════════

class Step3_SectionHierarchy:
    """
    Build a document tree from heading blocks.

    Output:
      Document
       ├─ Section (heading level 1)
       │   ├─ Paragraph block
       │   ├─ Paragraph block
       │   └─ Sub-Section (heading level 2)
       │       ├─ Paragraph block
       │       └─ Table block
    """

    # Known ESG section keywords for labeling
    ESG_KEYWORDS = {
        "environmental": "Environmental Performance",
        "emissions": "Environmental Performance",
        "carbon": "Environmental Performance",
        "climate": "Environmental Performance",
        "energy": "Environmental Performance",
        "water": "Environmental Performance",
        "waste": "Environmental Performance",
        "biodiversity": "Environmental Performance",
        "pollution": "Environmental Performance",
        "social": "Social Initiatives",
        "employee": "Social Initiatives",
        "workforce": "Social Initiatives",
        "health": "Social Initiatives",
        "safety": "Social Initiatives",
        "human rights": "Social Initiatives",
        "community": "Social Initiatives",
        "diversity": "Social Initiatives",
        "governance": "Governance",
        "board": "Governance",
        "ethics": "Governance",
        "compliance": "Governance",
        "risk management": "Governance",
        "anti-corruption": "Governance",
        "gri": "GRI Index",
        "sasb": "SASB Disclosure",
        "tcfd": "TCFD Alignment",
        "sdg": "SDG Mapping",
        "appendix": "Appendix",
        "methodology": "Methodology",
        "assurance": "Assurance Statement",
        "about this report": "Report Overview",
        "ceo": "Executive Summary",
        "chairman": "Executive Summary",
        "stakeholder": "Executive Summary",
    }

    def build(self, classified_blocks: List[ClassifiedBlock]) -> Tuple[List[SectionNode], Dict[str, str]]:
        """
        Returns:
          - sections: list of SectionNode objects
          - block_section_map: {block_id → section_id} mapping
        """
        sections: List[SectionNode] = []
        block_section_map: Dict[str, str] = {}

        # Get all heading blocks sorted by page + vertical position
        headings = [b for b in classified_blocks if b.block_type == "heading"]
        heading_font_sizes = sorted(set(h.font_size for h in headings), reverse=True)

        # Map font sizes to heading levels
        font_to_level = {}
        for i, fs in enumerate(heading_font_sizes[:4]):  # Max 4 levels
            font_to_level[fs] = i + 1

        # Create section nodes from headings
        current_sections: Dict[int, str] = {}  # level → section_id
        section_counter = 0

        for heading in headings:
            section_counter += 1
            level = font_to_level.get(heading.font_size, 3)
            section_id = f"sec_{section_counter:03d}"

            # Try to match to a known ESG category
            esg_label = self._match_esg_category(heading.text)
            title = esg_label if esg_label else heading.text.strip()[:100]

            section = SectionNode(
                section_id=section_id,
                title=title,
                level=level,
                page_number=heading.page_number,
            )
            sections.append(section)
            current_sections[level] = section_id

            # Assign heading block to its own section
            block_section_map[heading.block_id] = section_id

            # Wire parent-child relationships
            if level > 1:
                parent_level = level - 1
                while parent_level >= 1:
                    if parent_level in current_sections:
                        parent_id = current_sections[parent_level]
                        parent = next((s for s in sections if s.section_id == parent_id), None)
                        if parent:
                            parent.children_ids.append(section_id)
                        break
                    parent_level -= 1

        # Now assign every non-heading block to its nearest preceding section
        sorted_blocks = sorted(classified_blocks, key=lambda b: (b.page_number, b.bbox.y0))
        current_section_id = sections[0].section_id if sections else "sec_root"

        for block in sorted_blocks:
            if block.block_id in block_section_map:
                current_section_id = block_section_map[block.block_id]
                continue

            block_section_map[block.block_id] = current_section_id

            # Also add block to section's block list
            sec = next((s for s in sections if s.section_id == current_section_id), None)
            if sec:
                sec.block_ids.append(block.block_id)

        print(f"  [Step 3] Built {len(sections)} sections, "
              f"{len(heading_font_sizes)} heading levels detected.")

        # Build NetworkX graph if available
        if HAS_NETWORKX:
            self._build_graph(sections)

        return sections, block_section_map

    def _match_esg_category(self, text: str) -> Optional[str]:
        lower = text.lower().strip()
        for keyword, label in self.ESG_KEYWORDS.items():
            if keyword in lower:
                return label
        return None

    def _build_graph(self, sections: List[SectionNode]):
        """Build a NetworkX directed graph of the document structure."""
        G = nx.DiGraph()
        G.add_node("root", title="Document", level=0)

        for sec in sections:
            G.add_node(sec.section_id, title=sec.title, level=sec.level)

        # Connect top-level sections to root, sub-sections to their parents
        for sec in sections:
            if sec.level == 1:
                G.add_edge("root", sec.section_id)
            for child_id in sec.children_ids:
                G.add_edge(sec.section_id, child_id)

        self.document_graph = G
        print(f"  [Step 3] Document graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges.")


# ══════════════════════════════════════════════
# STEP 4: SENTENCE SEGMENTATION
# ══════════════════════════════════════════════

class Step4_SentenceSegmenter:
    """Split paragraph blocks into individual sentences using spaCy, preserving provenance."""

    def __init__(self):
        try:
            self.nlp = spacy.load("en_core_web_sm", disable=["ner", "lemmatizer"])
        except OSError:
            print("[Step 4] Downloading spaCy model...")
            from spacy.cli import download
            download("en_core_web_sm")
            self.nlp = spacy.load("en_core_web_sm", disable=["ner", "lemmatizer"])

        # Increase max length for long documents
        self.nlp.max_length = 2_000_000

    def segment(
        self,
        classified_blocks: List[ClassifiedBlock],
        block_section_map: Dict[str, str],
        sections: List[SectionNode],
    ) -> List[Sentence]:
        sentences: List[Sentence] = []
        sent_counter = 0
        section_lookup = {s.section_id: s.title for s in sections}

        for block in classified_blocks:
            # Only segment paragraphs and list items
            if block.block_type not in ("paragraph", "list"):
                continue

            doc = self.nlp(block.text)
            for sent_idx, sent in enumerate(doc.sents):
                text = sent.text.strip()
                if len(text) < 10:  # Skip tiny fragments
                    continue

                sent_counter += 1
                section_id = block_section_map.get(block.block_id)

                sentences.append(Sentence(
                    sentence_id=f"sent_{sent_counter:05d}",
                    text=text,
                    block_id=block.block_id,
                    page_number=block.page_number,
                    section_id=section_id,
                    section_title=section_lookup.get(section_id, "Unknown"),
                    bbox=block.bbox,
                    sentence_index=sent_idx,
                ))

        print(f"  [Step 4] Segmented into {len(sentences)} sentences.")
        return sentences


# ══════════════════════════════════════════════
# STEP 5: TABLE EXTRACTION
# ══════════════════════════════════════════════

class Step5_TableExtractor:
    """Extract structured tables with column headers mapped to cell values."""

    def extract(
        self,
        pdf_path: str,
        block_section_map: Dict[str, str],
    ) -> List[TableRow]:
        rows: List[TableRow] = []
        table_counter = 0
        skipped_tables = 0
        skipped_rows = 0

        with pdfplumber.open(pdf_path) as pdf:
            for page_idx, page in enumerate(pdf.pages):
                try:
                    tables = page.extract_tables()
                except Exception as e:
                    print(f"  [Step 5] Warning: Could not extract tables from page {page_idx+1}: {e}")
                    continue
                for t_idx, table in enumerate(tables):
                    if not table or len(table) < 2:
                        continue

                    raw_headers = [str(h or "").strip() for h in table[0]]
                    # (#5) Only keep columns that have a real header. A table whose
                    # header row is mostly empty is a layout fragment / page furniture,
                    # not a data table — skip it (previously these became "tables" with
                    # empty-string keys like {"": "7"}).
                    header_cols = [(i, h) for i, h in enumerate(raw_headers) if h]
                    if len(header_cols) < 2:
                        skipped_tables += 1
                        continue

                    # De-duplicate colliding header names so columns don't silently
                    # overwrite each other in the cells dict.
                    seen: Dict[str, int] = {}
                    col_names: Dict[int, str] = {}
                    for i, h in header_cols:
                        if h in seen:
                            seen[h] += 1
                            col_names[i] = f"{h} ({seen[h]})"
                        else:
                            seen[h] = 0
                            col_names[i] = h

                    table_counter += 1
                    table_id = f"tbl_{table_counter:03d}"

                    for row_idx, row in enumerate(table[1:]):
                        cells = {}
                        for col_idx, name in col_names.items():
                            if col_idx < len(row):
                                val = str(row[col_idx] or "").strip()
                                if val:
                                    cells[name] = val

                        # (#5) Drop near-empty rows: require real content under real
                        # headers (>2 chars total), not page-furniture scraps.
                        if cells and sum(len(v) for v in cells.values()) > 2:
                            rows.append(TableRow(
                                table_id=table_id,
                                page_number=page_idx + 1,
                                row_index=row_idx,
                                cells=cells,
                            ))
                        else:
                            skipped_rows += 1

        print(f"  [Step 5] Extracted {len(rows)} table rows from {table_counter} tables "
              f"(skipped {skipped_tables} fragment-tables, {skipped_rows} noise-rows).")
        return rows


# ══════════════════════════════════════════════
# STEP 6: CLAIM CANDIDATE DETECTION
# ══════════════════════════════════════════════

class Step6_ClaimCandidateDetector:
    """
    Rule-based filtering to find sentences likely containing ESG claims.

    Features scored:
      - Contains a number/percentage (+0.3)
      - Contains units (tonnes, hectares, MWh, etc.) (+0.2)
      - Contains action verbs (reduced, achieved, increased, etc.) (+0.2)
      - Contains ESG keywords (+0.2)
      - Is in a relevant ESG section (+0.1)
    """

    UNITS = re.compile(
        r'\b(tonnes?|mt|co2e?|hectares?|ha|kwh|mwh|gwh|litres?|liters?|'
        r'gallons?|cubic\s*m|m3|percent|%|MW|GW)\b', re.IGNORECASE
    )

    NUMBERS = re.compile(r'\b\d[\d,]*\.?\d*\s*(%|percent)?\b')

    ACTION_VERBS = re.compile(
        r'\b(reduced?|increased?|achieved?|maintained|eliminated?|'
        r'planted|restored|protected|offset|diverted|recycled|'
        r'conserved|invested|deployed|installed|generated|sourced|'
        r'committed|certified|decreased|improved|expanded)\b', re.IGNORECASE
    )

    ESG_KEYWORDS = re.compile(
        r'\b(carbon|emission|renewable|solar|wind|biodiversity|'
        r'deforestation|reforestation|water|waste|energy|recycl|'
        r'sustainab|ESG|climate|net.?zero|scope\s*[123]|'
        r'greenhouse|GHG|pollution|circular\s*economy)\b', re.IGNORECASE
    )

    RELEVANT_SECTIONS = {
        "Environmental Performance", "Social Initiatives",
        "GRI Index", "SASB Disclosure", "TCFD Alignment",
    }

    def detect(self, sentences: List[Sentence]) -> List[ClaimCandidate]:
        candidates: List[ClaimCandidate] = []
        cand_counter = 0

        for sent in sentences:
            features = {
                "has_number": bool(self.NUMBERS.search(sent.text)),
                "has_unit": bool(self.UNITS.search(sent.text)),
                "has_action_verb": bool(self.ACTION_VERBS.search(sent.text)),
                "has_esg_keyword": bool(self.ESG_KEYWORDS.search(sent.text)),
                "in_esg_section": sent.section_title in self.RELEVANT_SECTIONS,
            }

            score = sum([
                0.3 if features["has_number"] else 0,
                0.2 if features["has_unit"] else 0,
                0.2 if features["has_action_verb"] else 0,
                0.2 if features["has_esg_keyword"] else 0,
                0.1 if features["in_esg_section"] else 0,
            ])

            # Only keep sentences scoring >= 0.4 (at least 2 strong features)
            if score >= 0.4:
                cand_counter += 1
                candidates.append(ClaimCandidate(
                    candidate_id=f"cand_{cand_counter:04d}",
                    sentence_id=sent.sentence_id,
                    text=sent.text,
                    score=round(score, 2),
                    features=features,
                    page_number=sent.page_number,
                    section_id=sent.section_id,
                    section_title=sent.section_title,
                    bbox=sent.bbox,
                ))

        print(f"  [Step 6] Found {len(candidates)} claim candidates "
              f"from {len(sentences)} sentences (threshold >= 0.4).")
        return candidates


# ══════════════════════════════════════════════
# STEP 7: CONTEXT WINDOW CONSTRUCTION
# ══════════════════════════════════════════════

class Step7_ContextWindowBuilder:
    """
    Build semantic chunks by wrapping each claim candidate in its context window:

      [section title]
      previous sentence
      >>> TARGET SENTENCE <<<
      next sentence

    This is the input format for the Week 3 claim extraction model.
    Chunking happens ONLY here.
    """

    def build(self, candidates: List[ClaimCandidate], all_sentences: List[Sentence]) -> List[SemanticChunk]:
        # Build sentence index for fast neighbor lookup
        sent_by_id = {s.sentence_id: s for s in all_sentences}
        # Group sentences by block for context retrieval
        block_sentences: Dict[str, List[Sentence]] = defaultdict(list)
        for s in all_sentences:
            block_sentences[s.block_id].append(s)

        chunks: List[SemanticChunk] = []
        chunk_counter = 0

        for cand in candidates:
            target_sent = sent_by_id.get(cand.sentence_id)
            if not target_sent:
                continue

            # Get neighboring sentences in the same block
            block_sents = block_sentences.get(target_sent.block_id, [])
            target_idx = next(
                (i for i, s in enumerate(block_sents) if s.sentence_id == target_sent.sentence_id),
                -1,
            )

            context_before = ""
            context_after = ""
            if target_idx > 0:
                context_before = block_sents[target_idx - 1].text
            if target_idx < len(block_sents) - 1:
                context_after = block_sents[target_idx + 1].text

            section_title = cand.section_title or "Unknown Section"

            # Assemble model input
            full_text = f"[Section: {section_title}]\n"
            if context_before:
                full_text += f"{context_before}\n"
            full_text += f"{cand.text}\n"
            if context_after:
                full_text += f"{context_after}"

            chunk_counter += 1
            chunks.append(SemanticChunk(
                chunk_id=f"chunk_{chunk_counter:04d}",
                candidate_id=cand.candidate_id,
                section_title=section_title,
                context_before=context_before,
                target_sentence=cand.text,
                context_after=context_after,
                full_text=full_text.strip(),
                page_number=cand.page_number,
                bbox=cand.bbox,
            ))

        print(f"  [Step 7] Built {len(chunks)} semantic chunks with context windows.")
        return chunks


# ══════════════════════════════════════════════
# STEP 8: PROVENANCE LINKING
# ══════════════════════════════════════════════

class Step8_ProvenanceLinker:
    """Build the final provenance chain linking every chunk back to its source."""

    def link(
        self,
        chunks: List[SemanticChunk],
        candidates: List[ClaimCandidate],
        sentences: List[Sentence],
    ) -> List[ProvenanceRecord]:
        cand_by_id = {c.candidate_id: c for c in candidates}
        sent_by_id = {s.sentence_id: s for s in sentences}

        records: List[ProvenanceRecord] = []

        for chunk in chunks:
            cand = cand_by_id.get(chunk.candidate_id)
            if not cand:
                continue

            sent = sent_by_id.get(cand.sentence_id)
            if not sent:
                continue

            records.append(ProvenanceRecord(
                chunk_id=chunk.chunk_id,
                sentence_id=sent.sentence_id,
                block_id=sent.block_id,
                page_number=sent.page_number,
                section_id=sent.section_id,
                section_title=sent.section_title,
                bbox=sent.bbox,
            ))

        print(f"  [Step 8] Linked {len(records)} provenance records.")
        return records


# ══════════════════════════════════════════════
# ORCHESTRATOR: Runs all 8 steps
# ══════════════════════════════════════════════

class DocumentParsingPipeline:
    """
    Orchestrates the full 8-step document parsing pipeline.

    Usage:
        pipeline = DocumentParsingPipeline("report.pdf")
        result = pipeline.run()
    """

    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.document_id = hashlib.md5(
            Path(pdf_path).read_bytes()[:4096]
        ).hexdigest()[:12]

    def run(self, skip_tables: bool = False) -> Dict[str, Any]:
        # skip_tables=True bypasses the slow pdfplumber table scan (Step 5) when the
        # caller only needs text/sentences (e.g. section-level extraction).
        print(f"\n{'='*60}")
        print(f"ESGenuine - Document Parsing Pipeline")
        print(f"Document: {Path(self.pdf_path).name}")
        print(f"{'='*60}\n")

        # Step 0: Ingest & triage (validates + profiles before heavy parsing).
        # Raises PDFValidationError for encrypted/corrupt/empty PDFs.
        step0 = Step0_IngestTriage()
        triage = step0.run(self.pdf_path)

        # Step 1
        step1 = Step1_StructuralExtractor()
        raw_blocks, metadata = step1.extract(self.pdf_path)

        # Step 2
        step2 = Step2_LayoutClassifier()
        classified_blocks = step2.classify(raw_blocks)

        # Step 3
        step3 = Step3_SectionHierarchy()
        sections, block_section_map = step3.build(classified_blocks)

        # Step 4
        step4 = Step4_SentenceSegmenter()
        sentences = step4.segment(classified_blocks, block_section_map, sections)

        # Step 5 (skippable — pdfplumber table scan is the parse bottleneck)
        if skip_tables:
            print("  [Step 5] Skipped (skip_tables=True).")
            table_rows = []
        else:
            step5 = Step5_TableExtractor()
            table_rows = step5.extract(self.pdf_path, block_section_map)

        # Step 6
        step6 = Step6_ClaimCandidateDetector()
        candidates = step6.detect(sentences)

        # Step 7
        step7 = Step7_ContextWindowBuilder()
        chunks = step7.build(candidates, sentences)

        # Step 8
        step8 = Step8_ProvenanceLinker()
        provenance = step8.link(chunks, candidates, sentences)

        # Assemble result
        result = {
            "document_id": self.document_id,
            "file_hash": triage["file_hash"],
            "filename": Path(self.pdf_path).name,
            "metadata": metadata,
            "triage": triage,
            "total_pages": max((b.page_number for b in raw_blocks), default=0) or triage["page_count"],
            "statistics": {
                "raw_blocks": len(raw_blocks),
                "classified_blocks": len(classified_blocks),
                "sections": len(sections),
                "sentences": len(sentences),
                "table_rows": len(table_rows),
                "claim_candidates": len(candidates),
                "semantic_chunks": len(chunks),
                "provenance_records": len(provenance),
            },
            "sections": [asdict(s) for s in sections],
            "sentences": [asdict(s) for s in sentences],
            "table_rows": [asdict(t) for t in table_rows],
            "candidates": [asdict(c) for c in candidates],
            "chunks": [asdict(c) for c in chunks],
            "provenance": [asdict(p) for p in provenance],
        }

        print(f"\n{'='*60}")
        print(f"Pipeline Complete [OK]")
        for key, val in result["statistics"].items():
            print(f"  {key}: {val}")
        print(f"{'='*60}\n")

        return result

    def save(self, result: Dict[str, Any], output_dir: str) -> Dict[str, str]:
        """Save all pipeline outputs to JSON files."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        files = {}
        for key in ["sections", "sentences", "table_rows", "candidates", "chunks", "provenance"]:
            filepath = out / f"{self.document_id}_{key}.json"
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(result[key], f, indent=2, ensure_ascii=False)
            files[key] = str(filepath)

        # Save full result
        full_path = out / f"{self.document_id}_full.json"
        with open(full_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        files["full"] = str(full_path)

        print(f"[Saved] {len(files)} output files to {output_dir}")
        return files


# ══════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python pdf_parser.py <path_to_esg_report.pdf>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    pipeline = DocumentParsingPipeline(pdf_path)
    result = pipeline.run()
    pipeline.save(result, str(Path(pdf_path).parent / "parsed_output"))

"""
ESGenuine — Phase 3: Automated ESG Report Collector
===========================================================

Crawls public company sustainability pages, detects PDF links,
downloads reports, and stores metadata.

Usage:
    collector = ReportCollector(output_dir="data/reports")
    collector.collect(companies=[
        {"name": "Tata Steel", "url": "https://www.tatasteel.com/sustainability/"},
        {"name": "Reliance", "url": "https://www.ril.com/sustainability/"},
    ])

Output:
    data/reports/{company_slug}/{year}.pdf
    data/reports_metadata.json
"""

import os
import re
import json
import time
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from urllib.parse import urljoin, urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    raise ImportError("Install required packages: pip install requests beautifulsoup4")

logging.basicConfig(level=logging.INFO, format="[Collector] %(message)s")
logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════
# KEYWORD SIGNALS for identifying ESG reports
# ══════════════════════════════════════════════

ESG_KEYWORDS = [
    "sustainability report",
    "esg report",
    "integrated report",
    "environmental report",
    "corporate responsibility",
    "annual sustainability",
    "sustainability disclosure",
    "progress report",
    "responsible business",
    "brsr",  # Business Responsibility and Sustainability Report (India)
    "climate report",
    "net zero",
    "esg-report",
    "sustainability-report",
]

# PDFs that are NOT ESG reports (avoid false positives)
NOISE_KEYWORDS = [
    "press-release", "press_release", "pressrelease",
    "code-of-conduct", "code_of_conduct",
    "policy", "terms-of-service", "terms_of_service",
    "vendor", "supplier-code",
    "proxy", "shareholder",
    "whitepaper", "brochure", "catalogue", "catalog",
    "recruitment", "careers",
]

YEAR_PATTERN = re.compile(r'20(1[5-9]|2[0-9])')  # 2015–2029


class ReportCollector:
    """
    Crawls company sustainability pages and collects ESG report PDFs.
    """

    def __init__(self, output_dir: str = "data/reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.output_dir.parent / "reports_metadata.json"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; ESGenuine/1.0; ESG Research Bot)"
        })
        self._load_metadata()

    def _load_metadata(self):
        """Load existing download metadata to avoid re-downloading."""
        if self.metadata_file.exists():
            with open(self.metadata_file, "r") as f:
                self.metadata: List[Dict] = json.load(f)
        else:
            self.metadata: List[Dict] = []

    def _save_metadata(self):
        with open(self.metadata_file, "w") as f:
            json.dump(self.metadata, f, indent=2, default=str)

    def _slug(self, name: str) -> str:
        return re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')

    def _is_esg_pdf(self, url: str, link_text: str) -> bool:
        """Check if a URL looks like an ESG report PDF — and not a noise document."""
        combined = (url + " " + link_text).lower()
        if not url.lower().endswith(".pdf"):
            return False
        # Must match at least one ESG keyword
        if not any(kw in combined for kw in ESG_KEYWORDS):
            return False
        # Must NOT match noise keywords
        if any(nk in combined for nk in NOISE_KEYWORDS):
            return False
        return True

    def _extract_year(self, url: str, text: str) -> str:
        """Extract report year from URL or link text."""
        for source in [url, text]:
            match = YEAR_PATTERN.search(source)
            if match:
                return match.group(0)
        return str(datetime.now().year)

    def _get_pdf_links(self, page_url: str) -> List[Dict]:
        """Crawl a URL and return all PDF links that look like ESG reports."""
        try:
            resp = self.session.get(page_url, timeout=15, verify=False)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"Could not fetch {page_url}: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        found = []

        for tag in soup.find_all("a", href=True):
            href = tag["href"]
            text = tag.get_text(strip=True)
            absolute = urljoin(page_url, href)

            if self._is_esg_pdf(absolute, text):
                year = self._extract_year(absolute, text)
                found.append({
                    "url": absolute,
                    "text": text,
                    "year": year,
                })

        logger.info(f"Found {len(found)} ESG PDF links on {page_url}")
        return found

    def _download_pdf(
        self, url: str, company_slug: str, year: str
    ) -> Optional[str]:
        """Download a PDF and return its local file path."""
        company_dir = self.output_dir / company_slug
        company_dir.mkdir(parents=True, exist_ok=True)
        file_path = company_dir / f"{year}.pdf"

        if file_path.exists():
            logger.info(f"Already exists, skipping: {file_path}")
            return str(file_path)

        try:
            resp = self.session.get(url, timeout=60, stream=True, verify=False)
            resp.raise_for_status()

            with open(file_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            logger.info(f"Downloaded → {file_path}")
            return str(file_path)

        except Exception as e:
            logger.error(f"Download failed for {url}: {e}")
            return None

    def collect(self, companies: List[Dict]) -> List[Dict]:
        """
        Main entry point.

        Args:
            companies: list of {"name": "Company Name", "url": "https://..."}

        Returns:
            List of metadata records for all downloaded reports.
        """
        results = []

        for company in companies:
            name = company["name"]
            url = company["url"]
            slug = self._slug(name)

            logger.info(f"\n{'='*50}")
            logger.info(f"Collecting: {name}")
            logger.info(f"URL: {url}")

            pdf_links = self._get_pdf_links(url)

            if not pdf_links:
                logger.warning(f"No ESG PDFs found for {name}")
                continue

            for link in pdf_links:
                file_path = self._download_pdf(link["url"], slug, link["year"])
                if not file_path:
                    continue

                record = {
                    "company_id": slug,
                    "company_name": name,
                    "report_year": int(link["year"]),
                    "report_type": "esg",
                    "report_url": link["url"],
                    "file_path": file_path,
                    "download_timestamp": datetime.utcnow().isoformat(),
                }

                results.append(record)
                self.metadata.append(record)
                self._save_metadata()

                time.sleep(1)  # Be a polite scraper

        logger.info(f"\nCollection complete. {len(results)} reports downloaded.")
        return results

    def ingest_to_supabase(self, reports: list, supabase_url: str, supabase_key: str):
        """Insert collected report metadata into the Supabase `reports` table."""
        try:
            from supabase import create_client
            supabase = create_client(supabase_url, supabase_key)

            rows = [
                {
                    "report_id":    r["company_id"] + "_" + str(r["report_year"]),
                    "company_id":   r["company_id"],
                    "company_name": r["company_name"],
                    "report_year":  r["report_year"],
                    "report_type":  r.get("report_type", "esg"),
                    "source_url":   r.get("report_url"),
                    "file_path":    r.get("file_path"),
                    "ingested_at":  r.get("download_timestamp"),
                }
                for r in reports
            ]

            result = supabase.table("reports").upsert(rows, on_conflict="report_id").execute()
            inserted = len(result.data) if result.data else 0
            logger.info(f"Inserted {inserted} report records into Supabase reports table.")
            return inserted

        except Exception as e:
            logger.error(f"Failed to ingest reports to Supabase: {e}")
            return 0

    def get_all_reports(self) -> List[Dict]:
        """Return all metadata records (downloaded + previously collected)."""
        return self.metadata


# ══════════════════════════════════════════════
# CLI / Quick Test
# ══════════════════════════════════════════════

if __name__ == "__main__":
    # Dry-run mode with well-known public ESG report pages
    test_companies = [
        {
            "name": "Tata Consultancy Services",
            "url": "https://www.tcs.com/sustainability/reports",
        },
        {
            "name": "Infosys",
            "url": "https://www.infosys.com/sustainability/reports.html",
        },
    ]

    collector = ReportCollector(output_dir="data/reports")
    reports = collector.collect(companies=test_companies)

    print(f"\nCollected {len(reports)} reports:")
    for r in reports:
        print(f"  {r['company_name']} ({r['report_year']}) → {r['file_path']}")

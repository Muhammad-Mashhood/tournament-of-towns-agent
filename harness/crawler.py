"""
crawler.py — Build a full inventory of Tournament of Towns problem sets.

Crawls https://www.turgor.ru/en/problems/allproblems.php and each
per-tournament index page to discover source URLs, format, and language.

Returns a list of SourceRecord dataclasses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

from harness import fetcher
from harness.classify import classify_level, classify_variant, source_key

INDEX_URL = "https://www.turgor.ru/en/problems/allproblems.php"
BASE_URL = "https://www.turgor.ru"

# Tournaments with known Russian inline text for basic variants (approx range)
# Advanced variants in these eras are PDFs (Russian)
RUSSIAN_INLINE_TOURNAMENT_RANGE = range(1, 36)  # 1st–35th (≤2013-14)

# Tournaments where English PDFs are directly available
ENGLISH_PDF_TOURNAMENT_RANGE = range(38, 100)   # 38th onward (2016+)


@dataclass
class SourceRecord:
    key: str                       # Stable ID e.g. "31-fall-2009-10-18-junior-basic"
    tournament: int                # Tournament number
    round_name: str                # "fall" or "spring"
    date: str                      # ISO date of the session e.g. "2009-10-18"
    level: str                     # "junior" or "senior"
    variant: str                   # "basic" or "advanced"
    source_url: str                # Primary source URL
    source_type: str               # "html_inline_russian" | "pdf_russian" | "pdf_english" | "doc_russian"
    needs_translation: bool        # False if source is already English
    english_control_url: Optional[str] = None   # Official English PDF if available
    notes: List[str] = field(default_factory=list)
    scope: str = "included"        # "included" | "excluded"


def _detect_source_type(url: str) -> str:
    url_lower = url.lower()
    if url_lower.endswith(".pdf"):
        if "eng" in url_lower:
            return "pdf_english"
        return "pdf_russian"
    if url_lower.endswith(".doc") or url_lower.endswith(".docx"):
        return "doc_russian"
    return "html_inline_russian"


def _parse_index_page(html: str, tournament: int) -> List[dict]:
    """
    Parse a per-tournament index page and return a list of raw entry dicts.
    Each dict has: round, date_str, level_raw, variant_raw, url, source_type
    """
    soup = BeautifulSoup(html, "lxml")
    entries = []

    # Strategy: look for known header patterns in text content
    # Pattern: "Осенний тур" (Fall) / "Весенний тур" (Spring)
    #           "8 - 9 классы" / "10 - 11 классы"
    #           "базовый вариант" / "сложный вариант"
    #           Then date e.g. "18 октября 2009 г."

    text = soup.get_text(separator="\n")
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # Find all PDF links
    pdf_links = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.endswith(".pdf") or href.endswith(".doc") or href.endswith(".docx"):
            full = href if href.startswith("http") else BASE_URL + href
            label = a.get_text(strip=True).lower()
            pdf_links[label] = full

    return pdf_links  # caller handles interpretation


def _build_known_records() -> List[SourceRecord]:
    """
    Hard-coded inventory for the 31st Tournament (2009-10) demo targets
    plus a template for crawling remaining tournaments.
    
    The 2009 demo targets have unusual source formats that need explicit handling:
    - Basic (Oct 18): inline Russian text in page HTML
    - Advanced (Oct 25): single Russian PDF containing both grade levels
    """
    records = []

    # === 31st Tournament, Fall 2009 ===
    t31_base = "https://www.turgor.ru/en/problems/31/"

    # Oct 18 — basic (O-level), 8-9 classes → junior/basic
    records.append(SourceRecord(
        key="31-fall-2009-10-18-junior-basic",
        tournament=31,
        round_name="fall",
        date="2009-10-18",
        level="junior",
        variant="basic",
        source_url=t31_base + "index.php",
        source_type="html_inline_russian",
        needs_translation=True,
        notes=["Basic variant 8-9 cl inline on index page; extract by header marker"]
    ))

    # Oct 18 — basic (O-level), 10-11 classes → senior/basic
    records.append(SourceRecord(
        key="31-fall-2009-10-18-senior-basic",
        tournament=31,
        round_name="fall",
        date="2009-10-18",
        level="senior",
        variant="basic",
        source_url=t31_base + "index.php",
        source_type="html_inline_russian",
        needs_translation=True,
        notes=["Basic variant 10-11 cl inline on index page; extract by header marker"]
    ))

    # Oct 25 — advanced (A-level), 8-9 classes → junior/advanced
    records.append(SourceRecord(
        key="31-fall-2009-10-25-junior-advanced",
        tournament=31,
        round_name="fall",
        date="2009-10-25",
        level="junior",
        variant="advanced",
        source_url=t31_base + "os31sl.pdf",
        source_type="pdf_russian",
        needs_translation=True,
        notes=["Advanced variants for both grades in single PDF; split by header 8-9/10-11"]
    ))

    # Oct 25 — advanced (A-level), 10-11 classes → senior/advanced
    records.append(SourceRecord(
        key="31-fall-2009-10-25-senior-advanced",
        tournament=31,
        round_name="fall",
        date="2009-10-25",
        level="senior",
        variant="advanced",
        source_url=t31_base + "os31sl.pdf",
        source_type="pdf_russian",
        needs_translation=True,
        notes=["Advanced variants for both grades in single PDF; split by header 8-9/10-11"]
    ))

    return records


def build_full_inventory() -> List[SourceRecord]:
    """
    Build the complete inventory by crawling the archive index page.
    Supplements with hard-coded records for ambiguous older tournaments.
    """
    records = []
    seen_keys = set()

    # Fetch the main index
    try:
        html_bytes, _, from_cache = fetcher.fetch(INDEX_URL)
        html = html_bytes.decode("utf-8", errors="replace")
        soup = BeautifulSoup(html, "lxml")
    except Exception as e:
        print(f"[crawler] Could not fetch archive index: {e}")
        return _build_known_records()

    # Find all tournament-level entries
    # Pattern in allproblems.php: links to /en/problems/NN/fall-NN-O-eng-auth.pdf etc.
    pdf_pattern = re.compile(
        r"/en/problems/(\d+)/(fall|spring|spr)-(\d+)-(O|A)-(eng|rus)-auth\.pdf",
        re.IGNORECASE
    )

    for a in soup.find_all("a", href=True):
        href = a["href"]
        m = pdf_pattern.search(href)
        if not m:
            continue
        tourn_num = int(m.group(1))
        round_raw = m.group(2).lower()
        round_name = "fall" if round_raw == "fall" else "spring"
        level_code = m.group(4).upper()  # O or A
        lang = m.group(5).lower()        # eng or rus

        level = "junior" if level_code == "O" else "senior"
        variant = "basic" if level_code == "O" else "advanced"

        # Try to infer date from surrounding text (best-effort)
        date = _infer_date(tourn_num, round_name)

        full_url = BASE_URL + href if href.startswith("/") else href
        source_type = "pdf_english" if lang == "eng" else "pdf_russian"
        needs_translation = (lang != "eng")

        # For O-level English PDFs, note they cover both junior levels in one file
        # We treat as a single "combined" record for the full corpus
        # (not split into 8-9 / 10-11 — English PDFs are not split by grade on turgor.ru)
        key_combined = f"{tourn_num}-{round_name}-{date}-{level}-{variant}"
        if key_combined in seen_keys:
            continue
        seen_keys.add(key_combined)

        records.append(SourceRecord(
            key=key_combined,
            tournament=tourn_num,
            round_name=round_name,
            date=date,
            level=level,
            variant=variant,
            source_url=full_url,
            source_type=source_type,
            needs_translation=needs_translation,
            scope="included"
        ))

    # Add hard-coded demo records (may already be in list for older crawls)
    demo_records = _build_known_records()
    demo_keys = {r.key for r in demo_records}
    for r in demo_records:
        if r.key not in seen_keys:
            records.append(r)
            seen_keys.add(r.key)

    # Mark scope exclusions: Summer Conferences, Distant Contest
    for r in records:
        if "summer" in r.key.lower() or "distant" in r.key.lower():
            r.scope = "excluded"
            r.notes.append("Out of scope: not a written problem set round")

    return sorted(records, key=lambda r: (r.tournament, r.round_name, r.level, r.variant))


def build_demo_inventory() -> List[SourceRecord]:
    """Return only the 4 demonstration targets."""
    return _build_known_records()


# Date lookup for known tournaments (approximate — used when not in PDF filename)
_TOURNAMENT_DATES = {
    (31, "fall"):   {"junior-basic": "2009-10-18", "senior-basic": "2009-10-18",
                     "junior-advanced": "2009-10-25", "senior-advanced": "2009-10-25"},
    (31, "spring"): {"junior-basic": "2010-02-28", "senior-basic": "2010-02-28",
                     "junior-advanced": "2010-03-14", "senior-advanced": "2010-03-14"},
}


def _infer_date(tournament: int, round_name: str,
                level: str = "junior", variant: str = "basic") -> str:
    key = f"{level}-{variant}"
    dates = _TOURNAMENT_DATES.get((tournament, round_name), {})
    return dates.get(key, f"{2009 + (tournament - 31)}-{'10' if round_name == 'fall' else '03'}-01")

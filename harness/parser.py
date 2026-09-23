"""
parser.py — Extract structured problem data from Tournament of Towns sources.

Handles source formats:
  1. HTML inline Russian text (pre-2015 basic variants)
  2. Russian PDF (pre-2015 advanced variants, combined or single grade)
  3. English PDF (2016+ — no translation needed, just extract structure)
  4. DOC/DOCX (rare older tournaments)

Output schema:
  {
    "header": {
      "tournament": int,
      "round": str,
      "date": str,
      "level_raw": str,
      "variant_raw": str,
      "scoring_note": str
    },
    "problems": [
      {"number": int, "points": int|null, "text": str, "author": str}
    ],
    "raw_text": str,
    "warnings": [str]
  }
"""

from __future__ import annotations

import io
import re
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup


# ──────────────────────────────────────────────────────────────────────────────
# Solution-block detection (strip these out)
# ──────────────────────────────────────────────────────────────────────────────
SOLUTION_MARKERS_RU = [
    r"решени[ея]",    # "Решение", "Решения"
    r"доказательство",
    r"ответ\s*:",
]
SOLUTION_MARKERS_EN = [
    r"\bsolution\b",
    r"\bproof\b",
    r"\banswer\s*:",
]
_SOLUTION_RE = re.compile(
    "|".join(SOLUTION_MARKERS_RU + SOLUTION_MARKERS_EN),
    re.IGNORECASE
)

# Russian months for date parsing
_RU_MONTHS = {
    "января": "01", "февраля": "02", "марта": "03", "апреля": "04",
    "мая": "05", "июня": "06", "июля": "07", "августа": "08",
    "сентября": "09", "октября": "10", "ноября": "11", "декабря": "12",
}

_DATE_RU_RE = re.compile(
    r"(\d{1,2})\s+(" + "|".join(_RU_MONTHS) + r")\s+(\d{4})"
)


def _parse_date_ru(text: str) -> Optional[str]:
    m = _DATE_RU_RE.search(text.lower())
    if m:
        day = m.group(1).zfill(2)
        month = _RU_MONTHS[m.group(2)]
        year = m.group(3)
        return f"{year}-{month}-{day}"
    return None


def _strip_solutions(text: str) -> Tuple[str, bool]:
    """Remove solution sections. Returns (cleaned_text, had_solutions)."""
    lines = text.split("\n")
    cleaned = []
    in_solution = False
    had_solutions = False
    for line in lines:
        if _SOLUTION_RE.search(line):
            in_solution = True
            had_solutions = True
            continue
        # Blank line after solution marker ends the block
        if in_solution and line.strip() == "":
            in_solution = False
            continue
        if not in_solution:
            cleaned.append(line)
    return "\n".join(cleaned), had_solutions


def _extract_scoring_note(text: str) -> str:
    """Extract scoring rules like '(Итог подводится по трем задачам...)'."""
    m = re.search(r"\((?:итог\s+подводится|score\s+is\s+based)[^)]+\)", text, re.IGNORECASE)
    if m:
        return m.group(0).replace("\r", " ").replace("\n", " ")
    m = re.search(r"\(.*?(?:наилучш|лучш)[^)]+\)", text, re.IGNORECASE)
    return m.group(0).replace("\r", " ").replace("\n", " ") if m else ""


# ──────────────────────────────────────────────────────────────────────────────
# HTML source parser (inline Russian text on index pages)
# ──────────────────────────────────────────────────────────────────────────────

def parse_html(html: str, source_record) -> Dict[str, Any]:
    """
    Extract problem set from HTML index page.
    Matches the section for source_record.level and source_record.variant.
    """
    warnings = []
    soup = BeautifulSoup(html, "lxml")
    full_text = soup.get_text(separator="\n")

    sections = _split_html_sections(full_text)

    target_level_num = "8" if source_record.level == "junior" else "10"
    target_variant_ru = "базовый" if source_record.variant == "basic" else "сложный"

    matched_section = None
    for sec in sections:
        hdr = sec.get("header", "").lower()
        if target_level_num in hdr and (target_variant_ru in hdr or source_record.variant in hdr):
            matched_section = sec
            break

    if not matched_section:
        warnings.append(
            f"Could not find matching section for level={source_record.level} "
            f"variant={source_record.variant} in HTML"
        )
        matched_section = {"header": "", "body": full_text, "date": None, "level_raw": "", "variant_raw": ""}

    body = matched_section["body"]
    body, had_solutions = _strip_solutions(body)
    if had_solutions:
        warnings.append("Solution sections stripped from HTML source")

    problems = _parse_problems_from_html_body(body, warnings)
    date = matched_section.get("date") or source_record.date
    scoring = _extract_scoring_note(matched_section.get("header", "")) or _extract_scoring_note(body[:500])

    return {
        "header": {
            "tournament": source_record.tournament,
            "round": source_record.round_name,
            "date": date,
            "level_raw": matched_section.get("level_raw") or ("8-9" if source_record.level == "junior" else "10-11"),
            "variant_raw": matched_section.get("variant_raw") or ("базовый" if source_record.variant == "basic" else "сложный"),
            "scoring_note": scoring,
        },
        "problems": problems,
        "raw_text": body,
        "warnings": warnings,
    }


def _split_html_sections(text: str) -> List[Dict]:
    """Split full HTML text into per-section dicts by dashed separator lines."""
    sections = []
    sep_re = re.compile(r"-{20,}")
    sep_positions = [m.start() for m in sep_re.finditer(text)]

    if len(sep_positions) < 2:
        return [{"header": "", "body": text, "date": None, "level_raw": "", "variant_raw": ""}]

    i = 0
    while i + 1 < len(sep_positions):
        header_text = text[sep_positions[i]:sep_positions[i + 1]]
        body_start = sep_positions[i + 1]
        body_end = sep_positions[i + 2] if i + 2 < len(sep_positions) else len(text)
        body_text = text[body_start:body_end]

        date = _parse_date_ru(header_text)
        level_raw = "10-11" if re.search(r"10\s*[-–]\s*11", header_text) else ("8-9" if re.search(r"8\s*[-–]\s*9", header_text) else "")
        variant_raw = "базовый" if "базовый" in header_text.lower() else ("сложный" if "сложный" in header_text.lower() else "")

        sections.append({
            "header": header_text,
            "body": body_text,
            "date": date,
            "level_raw": level_raw,
            "variant_raw": variant_raw,
        })
        i += 2

    return sections


def _parse_problems_from_html_body(body: str, warnings: List[str]) -> List[Dict]:
    """
    Parse problems from HTML plain-text layout:
          1. Problem first line...
      3      Problem second line with points in col 1...
             Author in parens at the end
    """
    lines = body.split("\n")
    problems = []
    curr_num = None
    curr_pts = None
    curr_lines = []

    prob_header_re = re.compile(r"^\s*(\d{1,2})\.\s*(.*)$")
    pts_line_re = re.compile(r"^\s*(\d{1,2})\s{3,}(.*)$")
    author_re = re.compile(r"^\s*\(([А-ЯA-Z][^)]{2,60})\)\s*$")

    for line in lines:
        m_prob = prob_header_re.match(line)
        if m_prob:
            if curr_num is not None:
                problems.append(_finalize_html_problem(curr_num, curr_pts, curr_lines))
            curr_num = int(m_prob.group(1))
            curr_pts = None
            curr_lines = [m_prob.group(2)]
            continue

        if curr_num is not None:
            m_pts = pts_line_re.match(line)
            if m_pts and curr_pts is None:
                curr_pts = int(m_pts.group(1))
                curr_lines.append(m_pts.group(2))
            else:
                curr_lines.append(line)

    if curr_num is not None:
        problems.append(_finalize_html_problem(curr_num, curr_pts, curr_lines))

    # Fallback to general parsing if no problems matched
    if not problems:
        return _parse_problems_from_text(body, warnings)

    return problems


def _finalize_html_problem(num: int, pts: Optional[int], lines: List[str]) -> Dict:
    author = ""
    clean_lines = []
    author_re = re.compile(r"^\s*\(([А-ЯA-Z][^)]{2,60})\)\s*$")
    for l in lines:
        m_auth = author_re.match(l)
        if m_auth:
            author = m_auth.group(1).strip()
        else:
            clean_lines.append(l)

    # Clean leading/trailing empty lines
    text = "\n".join(clean_lines).strip()
    return {"number": num, "points": pts, "text": text, "author": author}


# ──────────────────────────────────────────────────────────────────────────────
# PDF source parser
# ──────────────────────────────────────────────────────────────────────────────

def parse_pdf(pdf_bytes: bytes, source_record) -> Dict[str, Any]:
    """
    Extract text from a Russian or English PDF and parse problem sections.
    Handles multi-page combined PDFs where Page 1 = Junior and Page 2 = Senior.
    """
    warnings = []
    pages_text = _extract_pdf_pages(pdf_bytes, warnings)

    if not pages_text:
        return {
            "header": {"tournament": source_record.tournament, "round": source_record.round_name,
                       "date": source_record.date, "level_raw": "", "variant_raw": "", "scoring_note": ""},
            "problems": [],
            "raw_text": "",
            "warnings": warnings + ["Empty or unreadable PDF"],
        }

    # Match page for level
    target_page_text = None
    level_pat = (
        r"(?:8\s*[-–]\s*9|8\s*класс|junior|o-level)"
        if source_record.level == "junior"
        else r"(?:10\s*[-–]\s*11|10\s*класс|senior|a-level)"
    )

    for page_str in pages_text:
        first_chunk = page_str[:400].lower()
        if re.search(level_pat, first_chunk):
            target_page_text = page_str
            break

    if not target_page_text:
        # Fallback to page 0 for junior, page 1 for senior if 2 pages exist
        if len(pages_text) >= 2 and source_record.level == "senior":
            target_page_text = pages_text[1]
        else:
            target_page_text = pages_text[0]
            if len(pages_text) > 1:
                warnings.append(f"Could not uniquely match level={source_record.level} in PDF pages; selected page")

    target_page_text, had_solutions = _strip_solutions(target_page_text)
    if had_solutions:
        warnings.append("Solution sections stripped from PDF source")

    scoring = _extract_scoring_note(target_page_text)
    date = _parse_date_ru(target_page_text[:400]) or source_record.date

    problems = _parse_problems_from_pdf_text(target_page_text, warnings)

    return {
        "header": {
            "tournament": source_record.tournament,
            "round": source_record.round_name,
            "date": date,
            "level_raw": "8-9" if source_record.level == "junior" else "10-11",
            "variant_raw": "сложный" if source_record.variant == "advanced" else "базовый",
            "scoring_note": scoring,
        },
        "problems": problems,
        "raw_text": target_page_text,
        "warnings": warnings,
    }


def _clean_pdf_text(text: str) -> str:
    """Normalize typographic ligatures, TeX extracted glyphs, and non-WinAnsi symbols."""
    if not text:
        return ""
    reps = {
        '\ufb00': 'ff',
        '\ufb01': 'fi',
        '\ufb02': 'fl',
        '\ufb03': 'ffi',
        '\ufb04': 'ffl',
        '\ufb05': 'ft',
        '\ufb06': 'st',
        '\u2a7d': '≤',
        '\u2a7e': '≥',
        '\u2212': '-',
        '\u25e6': '°',
        '\u2218': '°',
    }
    for k, v in reps.items():
        text = text.replace(k, v)
    return text


def _extract_pdf_pages(pdf_bytes: bytes, warnings: List[str]) -> List[str]:
    """Extract page text list using PyMuPDF (fitz) or PyPDF2 fallback."""
    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        return [_clean_pdf_text(page.get_text()) for page in doc]
    except Exception as e:
        warnings.append(f"PyMuPDF failed: {e}; trying PyPDF2")

    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        return [_clean_pdf_text(page.extract_text() or "") for page in reader.pages]
    except Exception as e:
        warnings.append(f"PyPDF2 failed: {e}")
        return []


def _parse_problems_from_pdf_text(page_text: str, warnings: List[str]) -> List[Dict]:
    """
    Parse problems from PDF text layout:
      4
      1.
      Problem text line 1
      Problem text line 2
      Author Name
      6
      2.
      ...
    """
    lines = [l.strip() for l in page_text.split("\n") if l.strip()]

    # Skip contest header lines until after "баллы", "задачи"
    start_idx = 0
    for i, l in enumerate(lines[:20]):
        if l in ("баллы", "задачи", "баллы задачи", "Points", "Problems"):
            start_idx = i + 1

    content_lines = lines[start_idx:]

    # Find problem number lines: "1.", "2.", etc.
    prob_indices = []
    for i, l in enumerate(content_lines):
        m = re.match(r"^(\d{1,2})\.$", l)
        if m:
            prob_indices.append((int(m.group(1)), i))

    if not prob_indices:
        # Try generic parser
        return _parse_problems_from_text(page_text, warnings)

    problems = []
    for idx, (num, line_idx) in enumerate(prob_indices):
        pts = None
        if line_idx > 0 and content_lines[line_idx - 1].isdigit():
            pts = int(content_lines[line_idx - 1])

        next_line_idx = prob_indices[idx + 1][1] if idx + 1 < len(prob_indices) else len(content_lines)

        end_text_idx = next_line_idx
        if idx + 1 < len(prob_indices) and next_line_idx > 0 and content_lines[next_line_idx - 1].isdigit():
            end_text_idx = next_line_idx - 1

        prob_body_lines = list(content_lines[line_idx + 1 : end_text_idx])

        # If points wasn't on preceding line (e.g. subparts 2 a) and 7 b)), sum subparts
        if pts is None:
            sub_pts = 0
            for k in range(len(prob_body_lines) - 1):
                if prob_body_lines[k].isdigit() and prob_body_lines[k + 1] in ("а)", "б)", "в)", "г)", "a)", "b)", "c)"):
                    sub_pts += int(prob_body_lines[k])
            if sub_pts > 0:
                pts = sub_pts

        # Author extraction from trailing line or parentheses
        author = ""
        if prob_body_lines:
            last_line = prob_body_lines[-1]
            # Match author with or without parens
            m_paren = re.match(r"^\(([А-ЯA-Z][^)]{2,60})\)$", last_line)
            if m_paren:
                author = m_paren.group(1).strip()
                prob_body_lines = prob_body_lines[:-1]
            elif re.match(r"^([А-ЯA-Z][а-яa-zА-ЯA-Z\s.,-]+)$", last_line) and len(last_line) < 60 and not last_line.endswith("."):
                author = last_line
                prob_body_lines = prob_body_lines[:-1]

        text = " ".join(prob_body_lines).strip()
        problems.append({"number": num, "points": pts, "text": text, "author": author})

    return problems


# ──────────────────────────────────────────────────────────────────────────────
# Generic fallback problem parser
# ──────────────────────────────────────────────────────────────────────────────

def _parse_problems_from_text(text: str, warnings: List[str]) -> List[Dict]:
    """Fallback parser for generic plain text."""
    problems = []
    pts_prefix = re.compile(r"\[(\d+)\s*балл[аов]*\]\s*(.*?)(?=\[\d+\s*балл|\Z)", re.DOTALL)
    classic = re.compile(r"^\s{0,10}(\d{1,2})\.\s+(.+?)(?=^\s{0,10}\d{1,2}\.\s|\Z)", re.DOTALL | re.MULTILINE)

    matches_a = list(pts_prefix.finditer(text))
    matches_b = list(classic.finditer(text))

    if matches_a and len(matches_a) >= 2:
        for i, m in enumerate(matches_a, 1):
            pts = int(m.group(1))
            body, _ = _strip_solutions(m.group(2).strip())
            problems.append({"number": i, "points": pts, "text": body, "author": ""})
    elif matches_b and len(matches_b) >= 1:
        for m in matches_b:
            num = int(m.group(1))
            body, _ = _strip_solutions(m.group(2).strip())
            problems.append({"number": num, "points": None, "text": body, "author": ""})
    else:
        warnings.append("Could not parse individual problems — returning full text as single block")
        body, _ = _strip_solutions(text)
        problems.append({"number": 1, "points": None, "text": body, "author": ""})

    return problems


# ──────────────────────────────────────────────────────────────────────────────
# DOC/DOCX source parser
# ──────────────────────────────────────────────────────────────────────────────

def parse_doc(doc_bytes: bytes, source_record) -> Dict[str, Any]:
    warnings = []
    try:
        import docx
        doc = docx.Document(io.BytesIO(doc_bytes))
        text = "\n".join(p.text for p in doc.paragraphs)
    except Exception as e:
        warnings.append(f"python-docx failed: {e}")
        text = ""

    text, had_solutions = _strip_solutions(text)
    if had_solutions:
        warnings.append("Solution sections stripped from DOC source")

    problems = _parse_problems_from_text(text, warnings)
    return {
        "header": {
            "tournament": source_record.tournament,
            "round": source_record.round_name,
            "date": source_record.date,
            "level_raw": source_record.level,
            "variant_raw": source_record.variant,
            "scoring_note": "",
        },
        "problems": problems,
        "raw_text": text,
        "warnings": warnings,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Dispatcher
# ──────────────────────────────────────────────────────────────────────────────

def extract(content: bytes, content_type: str, source_record) -> Dict[str, Any]:
    """Route to correct parser based on content type and source record."""
    st = source_record.source_type

    if st == "html_inline_russian":
        html = content.decode("utf-8", errors="replace")
        return parse_html(html, source_record)

    if st in ("pdf_russian", "pdf_english"):
        return parse_pdf(content, source_record)

    if st in ("doc_russian", "docx_russian"):
        return parse_doc(content, source_record)

    html = content.decode("utf-8", errors="replace")
    return parse_html(html, source_record)

"""
validator.py — Post-render validation and QA checks for generated PDFs.

Checks run after every PDF is generated:
  1. Render check: PDF is non-empty and parseable
  2. Problem count: matches source
  3. No-solutions: scan for solution keywords in output
  4. Math preservation: $ delimiter count within tolerance
  5. Control comparison: diff against official English PDF (if available)

Returns a list of issue strings and a status code.
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Status codes
STATUS_OK = "ok"
STATUS_WARN = "warn"
STATUS_ERROR = "error"

_SOLUTION_RE = re.compile(
    r"\b(solution|proof|answer\s*:)\b", re.IGNORECASE
)
_MATH_DELIM_RE = re.compile(r"\$")


def _extract_pdf_text(pdf_path: Path) -> str:
    """Extract text from a PDF for validation purposes."""
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        return "\n".join(page.get_text() for page in doc)
    except ImportError:
        pass
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(str(pdf_path))
        return "\n".join(p.extract_text() or "" for p in reader.pages)
    except Exception:
        return ""


def check_render(pdf_path: Path) -> List[str]:
    """Check the PDF is non-empty and parseable."""
    issues = []
    if not pdf_path.exists():
        issues.append(f"ERROR: PDF not created at {pdf_path}")
        return issues
    size = pdf_path.stat().st_size
    if size < 500:
        issues.append(f"ERROR: PDF suspiciously small ({size} bytes) — may be corrupt")
        return issues
    text = _extract_pdf_text(pdf_path)
    if not text.strip():
        issues.append("WARN: Could not extract any text from PDF (may be image-only)")
    return issues


def check_problem_count(pdf_path: Path, source_parsed: Dict) -> List[str]:
    """Verify the number of problems in the PDF matches the source."""
    issues = []
    expected = len(source_parsed.get("problems", []))
    if expected == 0:
        return ["WARN: Source parsed zero problems — cannot validate count"]

    text = _extract_pdf_text(pdf_path)
    # Count "Problem N." occurrences in PDF text
    found = len(re.findall(r"\bProblem\s+\d+\b", text))
    if found == 0:
        issues.append(
            f"WARN: No 'Problem N' headers found in PDF; "
            f"expected {expected}"
        )
    elif abs(found - expected) > 1:
        issues.append(
            f"WARN: Problem count mismatch — source has {expected}, "
            f"PDF appears to have {found}"
        )
    return issues


def check_no_solutions(pdf_path: Path) -> List[str]:
    """Ensure no solution text leaked into the PDF."""
    issues = []
    text = _extract_pdf_text(pdf_path)
    matches = _SOLUTION_RE.findall(text)
    if matches:
        # Allow one match — the footer disclaimer says "Solutions not included"
        unique = set(m.lower() for m in matches)
        if unique - {"solution"}:  # non-"solution" hits are suspicious
            issues.append(
                f"WARN: Possible solution text detected in PDF: {list(unique)}"
            )
        elif len(matches) > 2:
            issues.append(
                f"WARN: 'solution' appears {len(matches)} times in PDF — "
                f"check that solutions were not included"
            )
    return issues


def check_math_preservation(pdf_path: Path, source_parsed: Dict,
                             tolerance: float = 0.15) -> List[str]:
    """
    Compare math delimiter density between source and rendered PDF.
    Uses $ count as a proxy (not perfect for pdflatex output which strips $
    from rendered PDF text, but useful for WeasyPrint/HTML output).
    """
    issues = []
    source_text = source_parsed.get("raw_text", "")
    source_dollar_count = len(_MATH_DELIM_RE.findall(source_text))

    if source_dollar_count < 2:
        # Not enough math in source to check
        return issues

    pdf_text = _extract_pdf_text(pdf_path)
    pdf_dollar_count = len(_MATH_DELIM_RE.findall(pdf_text))

    # For pdflatex-rendered PDFs, $ are consumed; check for math symbols instead
    math_symbols = len(re.findall(r"[+\-×÷=≤≥≠∈∉⊂⊃∪∩∞√∑∏∫∂π±]", pdf_text))

    if pdf_dollar_count == 0 and math_symbols < source_dollar_count / 4:
        issues.append(
            f"WARN: Math may not have rendered correctly — "
            f"source has {source_dollar_count} $ delimiters, "
            f"PDF has {pdf_dollar_count} dollar signs and "
            f"{math_symbols} math symbols"
        )
    return issues


def check_control_comparison(pdf_path: Path, control_url: str) -> List[str]:
    """
    Download official English PDF (control) and compare first problem text.
    Records divergences as warnings (does NOT fail on divergence — translation may legitimately differ).
    """
    issues = []
    if not control_url:
        return issues
    try:
        from harness import fetcher
        content, _, from_cache = fetcher.fetch(control_url)
        control_text = ""
        try:
            import fitz
            doc = fitz.open(stream=content, filetype="pdf")
            control_text = "\n".join(page.get_text() for page in doc)
        except Exception:
            pass

        if not control_text.strip():
            return ["WARN: Could not extract text from control PDF"]

        our_text = _extract_pdf_text(pdf_path)

        # Very rough comparison: check first 200 chars of first problem
        ctrl_first = _first_problem_text(control_text)[:200]
        our_first = _first_problem_text(our_text)[:200]

        if ctrl_first and our_first:
            dist = _edit_distance_ratio(ctrl_first.lower(), our_first.lower())
            if dist > 0.40:
                issues.append(
                    f"NOTE (control comparison): First problem differs significantly "
                    f"from official English edition (edit distance ratio={dist:.2f}). "
                    f"This may be acceptable as a translation difference."
                )
    except Exception as e:
        issues.append(f"WARN: Control comparison failed: {e}")
    return issues


def _first_problem_text(text: str) -> str:
    """Extract the first problem statement from PDF text."""
    m = re.search(r"Problem\s+1\b.*?\n(.*?)(?=Problem\s+2|\Z)", text,
                  re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else text[:300]


def _edit_distance_ratio(s1: str, s2: str) -> float:
    """Simple Levenshtein distance ratio."""
    if not s1 or not s2:
        return 1.0
    m, n = len(s1), len(s2)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev, dp[0] = dp[0], i
        for j in range(1, n + 1):
            temp = dp[j]
            dp[j] = prev if s1[i-1] == s2[j-1] else 1 + min(prev, dp[j], dp[j-1])
            prev = temp
    return dp[n] / max(m, n)


def validate(pdf_path: Path, source_parsed: Dict,
             source_record) -> Tuple[str, List[str]]:
    """
    Run all checks and return (status, issues_list).
    status: "ok" | "warn" | "error"
    """
    all_issues = []

    all_issues.extend(check_render(pdf_path))
    all_issues.extend(check_problem_count(pdf_path, source_parsed))
    all_issues.extend(check_no_solutions(pdf_path))
    all_issues.extend(check_math_preservation(pdf_path, source_parsed))

    if getattr(source_record, "english_control_url", None):
        all_issues.extend(
            check_control_comparison(pdf_path, source_record.english_control_url)
        )

    # Determine status
    if any(i.startswith("ERROR") for i in all_issues):
        status = STATUS_ERROR
    elif any(i.startswith("WARN") for i in all_issues):
        status = STATUS_WARN
    else:
        status = STATUS_OK

    return status, all_issues

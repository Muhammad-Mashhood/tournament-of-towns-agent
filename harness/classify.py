"""
classify.py — Map Tournament of Towns source labels to output folder structure.

Output folder layout:
  output/
    junior/   (8–9 classes, O-level equivalent)
      basic/
      advanced/
    senior/   (10–11 classes, A-level equivalent)
      basic/
      advanced/
"""

import re


def classify_level(raw_text: str) -> str:
    """Return 'junior' or 'senior' from source text or metadata."""
    t = raw_text.lower()
    if any(k in t for k in ("8-9", "8 - 9", "8–9", "o-level", "o level", "junior")):
        return "junior"
    if any(k in t for k in ("10-11", "10 - 11", "10–11", "a-level", "a level", "senior")):
        return "senior"
    raise ValueError(f"Cannot classify level from: {raw_text!r}")


def classify_variant(raw_text: str) -> str:
    """Return 'basic' or 'advanced' from source text or metadata."""
    t = raw_text.lower()
    if any(k in t for k in ("базовый", "basic", "o-level")):
        return "basic"
    if any(k in t for k in ("сложный", "advanced", "a-level")):
        return "advanced"
    raise ValueError(f"Cannot classify variant from: {raw_text!r}")


def output_folder(level: str, variant: str) -> str:
    """Return relative output path like 'output/junior/basic'."""
    return f"output/{level}/{variant}"


def output_filename(tournament: int, round_name: str, date: str,
                    level: str, variant: str) -> str:
    """Return the PDF filename (no path)."""
    # e.g. 31-fall-2009-10-18-junior-basic.pdf
    return f"{tournament}-{round_name}-{date}-{level}-{variant}.pdf"


def source_key(tournament: int, round_name: str, date: str,
               level: str, variant: str) -> str:
    """Stable string key used in checkpoints and manifest."""
    return f"{tournament}-{round_name}-{date}-{level}-{variant}"

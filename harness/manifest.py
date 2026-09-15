"""
manifest.py — Write and update the source inventory manifest (JSON + CSV).

Manifest fields per record:
  key, tournament, round, date, level, variant,
  source_url, source_type, needs_translation, model_used,
  problem_count, output_path, sha256, status, cost_usd, issues, scope, notes
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

MANIFEST_JSON = Path("manifest.json")
MANIFEST_CSV = Path("manifest.csv")

_FIELDNAMES = [
    "key", "tournament", "round", "date", "level", "variant",
    "source_url", "source_type", "needs_translation", "model_used",
    "problem_count", "output_path", "sha256", "status", "cost_usd",
    "scope", "notes", "issues",
]


def _load() -> List[Dict]:
    if MANIFEST_JSON.exists():
        try:
            return json.loads(MANIFEST_JSON.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
    return []


def _save(records: List[Dict]) -> None:
    MANIFEST_JSON.write_text(
        json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    # Also write CSV
    with MANIFEST_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for r in records:
            row = {k: r.get(k, "") for k in _FIELDNAMES}
            row["issues"] = "; ".join(r.get("issues", []))
            row["notes"] = "; ".join(r.get("notes", []))
            writer.writerow(row)


def _sha256(path: Optional[Path]) -> str:
    if path and Path(path).exists():
        h = hashlib.sha256()
        h.update(Path(path).read_bytes())
        return h.hexdigest()
    return ""


def record(source_record, pdf_path: Optional[Path], status: str,
           issues: List[str], translated: Optional[Dict] = None) -> None:
    """Record a successful (or warned) item in the manifest."""
    records = _load()

    # Remove existing entry for this key
    records = [r for r in records if r.get("key") != source_record.key]

    problem_count = 0
    model_used = ""
    cost_usd = 0.0
    if translated:
        problem_count = len(translated.get("problems", []))
        model_used = translated.get("translation_model", "")
        cost_usd = translated.get("translation_cost_usd", 0.0)

    entry = {
        "key": source_record.key,
        "tournament": source_record.tournament,
        "round": source_record.round_name,
        "date": source_record.date,
        "level": source_record.level,
        "variant": source_record.variant,
        "source_url": source_record.source_url,
        "source_type": source_record.source_type,
        "needs_translation": source_record.needs_translation,
        "model_used": model_used,
        "problem_count": problem_count,
        "output_path": str(pdf_path) if pdf_path else "",
        "sha256": _sha256(pdf_path),
        "status": status,
        "cost_usd": round(cost_usd, 8),
        "scope": getattr(source_record, "scope", "included"),
        "notes": getattr(source_record, "notes", []),
        "issues": issues,
    }
    records.append(entry)
    _save(records)


def record_failure(source_record, reason: str) -> None:
    """Record a failed item in the manifest."""
    records = _load()
    records = [r for r in records if r.get("key") != source_record.key]
    entry = {
        "key": source_record.key,
        "tournament": source_record.tournament,
        "round": source_record.round_name,
        "date": source_record.date,
        "level": source_record.level,
        "variant": source_record.variant,
        "source_url": source_record.source_url,
        "source_type": source_record.source_type,
        "needs_translation": source_record.needs_translation,
        "model_used": "",
        "problem_count": 0,
        "output_path": "",
        "sha256": "",
        "status": "error",
        "cost_usd": 0.0,
        "scope": getattr(source_record, "scope", "included"),
        "notes": getattr(source_record, "notes", []),
        "issues": [f"ERROR: {reason}"],
    }
    records.append(entry)
    _save(records)


def record_excluded(source_record, reason: str) -> None:
    """Record an explicitly excluded item."""
    records = _load()
    records = [r for r in records if r.get("key") != source_record.key]
    entry = {
        "key": source_record.key,
        "tournament": source_record.tournament,
        "round": source_record.round_name,
        "date": source_record.date,
        "level": source_record.level,
        "variant": source_record.variant,
        "source_url": source_record.source_url,
        "source_type": source_record.source_type,
        "needs_translation": source_record.needs_translation,
        "model_used": "",
        "problem_count": 0,
        "output_path": "",
        "sha256": "",
        "status": "excluded",
        "cost_usd": 0.0,
        "scope": "excluded",
        "notes": [reason],
        "issues": [],
    }
    records.append(entry)
    _save(records)


def summary() -> Dict[str, Any]:
    records = _load()
    statuses = {}
    for r in records:
        s = r.get("status", "unknown")
        statuses[s] = statuses.get(s, 0) + 1
    return {
        "total": len(records),
        "by_status": statuses,
        "total_cost_usd": round(sum(r.get("cost_usd", 0) for r in records), 4),
    }

"""
checkpoint.py — Resume support via a JSON checkpoint file.

Records which source keys have been successfully processed or failed,
so a re-run skips completed items and retries failed ones (if --retry-failed).
"""

import json
from pathlib import Path

CHECKPOINT_PATH = Path("checkpoint.json")


def _load() -> dict:
    if CHECKPOINT_PATH.exists():
        try:
            return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"processed": [], "failed": {}}
    return {"processed": [], "failed": {}}


def _save(data: dict) -> None:
    CHECKPOINT_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def is_done(key: str) -> bool:
    return key in _load()["processed"]


def is_failed(key: str) -> bool:
    return key in _load()["failed"]


def save(key: str) -> None:
    data = _load()
    if key not in data["processed"]:
        data["processed"].append(key)
    # Remove from failed if it was previously there
    data["failed"].pop(key, None)
    _save(data)


def mark_failed(key: str, reason: str) -> None:
    data = _load()
    data["failed"][key] = reason
    _save(data)


def stats() -> dict:
    data = _load()
    return {
        "processed": len(data["processed"]),
        "failed": len(data["failed"]),
        "failed_keys": list(data["failed"].keys()),
    }


def reset() -> None:
    """Clear checkpoint (start fresh)."""
    _save({"processed": [], "failed": {}})

"""
budget.py — Hard $5 spending cap enforcement and cost ledger.

The OPENROUTER_API_KEY is never written here; only costs are tracked.
"""

import json
import os
import time
from pathlib import Path

HARD_CAP_USD = float(os.getenv("BUDGET_CAP_USD", "5.00"))
LEDGER_PATH = Path("logs/cost_ledger.jsonl")

# Model pricing (USD per 1M tokens, input / output)
# Sourced from openrouter.ai/models
MODEL_PRICES = {
    "meta-llama/llama-3.3-70b-instruct": {"input": 0.10, "output": 0.32},
    "meta-llama/llama-3.1-8b-instruct":  {"input": 0.05, "output": 0.08},
    "google/gemini-2.5-flash-lite":      {"input": 0.10, "output": 0.40},
    "google/gemini-2.5-flash":           {"input": 0.15, "output": 1.25},
    "openai/gpt-4o-mini":                {"input": 0.15, "output": 0.60},
}
DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"


class BudgetExhaustedError(Exception):
    pass


def _load_spent() -> float:
    """Sum all recorded costs from the ledger file."""
    if not LEDGER_PATH.exists():
        return 0.0
    total = 0.0
    for line in LEDGER_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                total += json.loads(line).get("cost_usd", 0.0)
            except json.JSONDecodeError:
                pass
    return total


def remaining() -> float:
    return max(0.0, HARD_CAP_USD - _load_spent())


def spent() -> float:
    return _load_spent()


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    prices = MODEL_PRICES.get(model, MODEL_PRICES[DEFAULT_MODEL])
    return (input_tokens * prices["input"] + output_tokens * prices["output"]) / 1_000_000


def pre_call_check(model: str, estimated_input_tokens: int,
                   estimated_output_tokens: int = 500) -> None:
    """Raise BudgetExhaustedError if estimated call would exceed cap."""
    est = estimate_cost(model, estimated_input_tokens, estimated_output_tokens)
    if spent() + est > HARD_CAP_USD:
        raise BudgetExhaustedError(
            f"Would exceed ${HARD_CAP_USD} cap. "
            f"Spent: ${spent():.4f}, estimate: ${est:.4f}, remaining: ${remaining():.4f}"
        )


def record(source_key: str, model: str, input_tokens: int,
           output_tokens: int, cost_usd: float) -> None:
    """Append one cost record to the ledger."""
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_key": source_key,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost_usd, 8),
        "cumulative_usd": round(spent() + cost_usd, 8),
    }
    with LEDGER_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def summary() -> dict:
    return {
        "spent_usd": round(spent(), 4),
        "remaining_usd": round(remaining(), 4),
        "cap_usd": HARD_CAP_USD,
    }

"""
translator.py — Translate Russian problem sets to English via OpenRouter.

Uses the OpenAI-compatible API with math-preserving prompts.
The OPENROUTER_API_KEY is loaded from env only — never hard-coded here.
Cost is recorded via budget.py after every call.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

import openai

from harness import budget
from harness.budget import BudgetExhaustedError  # re-export for callers

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"
_FALLBACK_MODEL = "google/gemini-2.5-flash-lite"

PROMPT_DIR = Path("prompts/v1")
TRANSLATE_PROMPT_PATH = PROMPT_DIR / "translate_problem_set.md"
ERROR_LOG_DIR = Path("logs/errors")
RUN_TRACE_PATH = Path("logs/run_trace.jsonl")


def _ensure_dirs() -> None:
    """Create log directories lazily (not at import time)."""
    ERROR_LOG_DIR.mkdir(parents=True, exist_ok=True)
    RUN_TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)


def _get_client() -> openai.OpenAI:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "OPENROUTER_API_KEY is not set. "
            "Copy .env.example to .env and add your key."
        )
    return openai.OpenAI(
        base_url=_OPENROUTER_BASE_URL,
        api_key=api_key,
        default_headers={
            "HTTP-Referer": "https://github.com/tournament-of-towns-agent",
            "X-Title": "Tournament of Towns Archive Agent",
        }
    )


def _load_prompt_template() -> str:
    if TRANSLATE_PROMPT_PATH.exists():
        return TRANSLATE_PROMPT_PATH.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Prompt template not found: {TRANSLATE_PROMPT_PATH}")


def _build_prompt(parsed_data: Dict[str, Any]) -> str:
    """Render the translation prompt with the source text inserted."""
    template = _load_prompt_template()
    hdr = parsed_data.get("header", {})

    # Serialize the problem list as a clean block for the model
    problems_text = ""
    for p in parsed_data.get("problems", []):
        pts = f"[{p['points']} points]" if p.get("points") else ""
        author = f"  ({p['author']})" if p.get("author") else ""
        problems_text += f"\nProblem {p['number']} {pts}\n{p['text']}{author}\n"

    source_text = problems_text.strip()

    # Replace placeholder
    prompt = template.replace("{{SOURCE_TEXT}}", source_text)
    prompt = prompt.replace("{{TOURNAMENT}}", str(hdr.get("tournament", "")))
    prompt = prompt.replace("{{ROUND}}", hdr.get("round", ""))
    prompt = prompt.replace("{{DATE}}", hdr.get("date", ""))
    prompt = prompt.replace("{{LEVEL_RAW}}", hdr.get("level_raw", ""))
    prompt = prompt.replace("{{VARIANT_RAW}}", hdr.get("variant_raw", ""))
    return prompt


def _estimate_tokens(text: str) -> int:
    """Rough estimate: 1 token ≈ 4 chars for Russian/English mixed text."""
    return max(1, len(text) // 4)


def _call_model(client: openai.OpenAI, model: str, prompt: str,
                source_key: str) -> Dict[str, Any]:
    """Make the OpenRouter API call and return parsed response."""
    est_input_tokens = _estimate_tokens(prompt)
    budget.pre_call_check(model, est_input_tokens, estimated_output_tokens=800)

    start = time.time()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a precise mathematical translator. "
                    "Output only valid JSON as specified in the user prompt. "
                    "Never include solutions or your own commentary outside JSON."
                )
            },
            {"role": "user", "content": prompt}
        ],
        temperature=0.1,
        max_tokens=2000,
    )
    elapsed = time.time() - start

    usage = response.usage
    input_tokens = usage.prompt_tokens if usage else est_input_tokens
    output_tokens = usage.completion_tokens if usage else 200
    cost = budget.estimate_cost(model, input_tokens, output_tokens)
    budget.record(source_key, model, input_tokens, output_tokens, cost)

    raw_content = response.choices[0].message.content or ""

    # Log to run trace (no API key ever logged)
    _log_trace({
        "source_key": source_key,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 8),
        "elapsed_s": round(elapsed, 2),
        "status": "ok",
    })

    return {"raw": raw_content, "model": model, "cost_usd": cost}


def _clean_json_escapes(s: str) -> str:
    r"""Escape invalid backslashes (such as LaTeX commands like \cdot or \underbrace) in JSON."""
    pattern = r'\\(?!(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))'
    return re.sub(pattern, r'\\\\', s)


def _parse_model_output(raw: str, source_key: str) -> Dict[str, Any]:
    """Extract JSON from model response (may be wrapped in markdown code fences)."""
    # Strip ```json ... ``` if present
    raw = raw.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)```\s*$", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()

    try:
        data = json.loads(raw)
        return data
    except json.JSONDecodeError:
        pass

    # Try after escaping unescaped LaTeX backslashes
    try:
        return json.loads(_clean_json_escapes(raw))
    except json.JSONDecodeError:
        pass

    # Try to extract JSON object from mixed text
    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            try:
                return json.loads(_clean_json_escapes(json_match.group(0)))
            except json.JSONDecodeError:
                pass

    # Save raw output for debugging
    err_path = ERROR_LOG_DIR / f"{source_key}_raw_response.txt"
    err_path.write_text(raw, encoding="utf-8")
    raise ValueError(
        f"Could not parse model output as JSON for {source_key}. "
        f"Raw saved to {err_path}"
    )


def _merge_translation(parsed_source: Dict, translated_json: Dict) -> Dict:
    """Merge translated problem texts back with source metadata."""
    source_problems = parsed_source.get("problems", [])
    translated_problems = translated_json.get("problems", [])

    # Match by problem number where possible
    trans_by_num = {p.get("number"): p for p in translated_problems}

    merged_problems = []
    for sp in source_problems:
        num = sp["number"]
        tp = trans_by_num.get(num, {})
        # Points: take source if present, else model
        pts = sp.get("points") if sp.get("points") is not None else tp.get("points")
        # Author: prefer transliterated English author from model, fallback to Russian source
        author = tp.get("author") if tp.get("author") else sp.get("author", "")
        # Clean up any surrounding parens from author
        if author.startswith("(") and author.endswith(")"):
            author = author[1:-1].strip()
        merged_problems.append({
            "number": num,
            "points": pts,
            "text": tp.get("text", sp.get("text", "")),  # translated first, fallback to Russian
            "author": author,
            "note": tp.get("note", ""),  # [NOTE: ...] flags from model
        })

    return {
        "header": parsed_source["header"],
        "problems": merged_problems,
        "warnings": parsed_source.get("warnings", []),
        "translation_model": translated_json.get("_model", ""),
    }


def translate(parsed_source: Dict[str, Any], source_record) -> Dict[str, Any]:
    """
    Translate a parsed problem set to English.

    If source is already English (needs_translation=False), return as-is.
    Otherwise, call OpenRouter with the translation prompt.
    """
    if not source_record.needs_translation:
        # Already English — no API call needed
        return {**parsed_source, "translation_model": "none (source is English)"}

    client = _get_client()
    prompt = _build_prompt(parsed_source)
    model = _DEFAULT_MODEL

    try:
        result = _call_model(client, model, prompt, source_record.key)
    except BudgetExhaustedError:
        raise
    except Exception as e:
        # Try fallback model
        _log_trace({
            "source_key": source_record.key,
            "model": model,
            "status": "error",
            "error": str(e),
        })
        print(f"  [translator] Primary model failed ({e}), trying fallback")
        model = _FALLBACK_MODEL
        result = _call_model(client, model, prompt, source_record.key)

    translated_json = _parse_model_output(result["raw"], source_record.key)
    translated_json["_model"] = model
    merged = _merge_translation(parsed_source, translated_json)
    merged["translation_model"] = model
    merged["translation_cost_usd"] = result["cost_usd"]
    return merged


def _log_trace(entry: dict) -> None:
    """Append to run_trace.jsonl (never includes API key)."""
    with RUN_TRACE_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

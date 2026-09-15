# Prompts — Tournament of Towns Archive Agent

All prompts are stored here as versioned plain-text files.

## Versioning

- Current version: **v1**
- To update a prompt: create `v2/` directory, copy and modify
- The `translator.py` harness reads from `PROMPT_DIR` (default `prompts/v1`)
- Set `PROMPT_VERSION=v2` env var to switch versions

## Files

| File | Purpose |
|---|---|
| `translate_problem_set.md` | Main translation prompt sent to the LLM |
| `extract_problems.md` | Problem extraction / deduplication prompt (used for QA validation) |
| `latex_template.tex.jinja` | LaTeX document template for PDF rendering |

## Design Principles

1. **Math preservation first**: Every prompt explicitly instructs the model to leave LaTeX delimiters (`$`, `$$`, `\frac`, etc.) untouched.
2. **No solutions**: Prompts reinforce the parser's solution-stripping; model is instructed not to include solutions even if present in source.
3. **Structured output**: JSON schema ensures the harness can parse model output programmatically without fragile regex.
4. **Author attribution**: Authors (e.g. `(А.В.Шаповалов)`) must be preserved in the output.

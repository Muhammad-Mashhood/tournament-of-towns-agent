# Tournament of Towns Archive Agent

An automated agent that fetches, translates (Russian → English), and renders every written problem set from the [Tournament of Towns](https://www.turgor.ru/en/) mathematical olympiad archive as English PDFs.

## Quick Start

### Prerequisites

- Python 3.11+
- **Optional but recommended**: MiKTeX or TeX Live (for high-quality math rendering via pdflatex). If unavailable, WeasyPrint is used as a fallback.
- An [OpenRouter](https://openrouter.ai/) API key (hard $5 spending cap built in)

### Setup

```bash
# 1. Clone / enter the project directory
cd tournament-agent

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Set your API key (never commit this file)
cp .env.example .env
# Edit .env and set: OPENROUTER_API_KEY=sk-or-...
```

### Run the 4 Demonstration PDFs

```bash
python run_demo.py
```

Expected output in:
```
output/
  junior/
    basic/     31-fall-2009-10-18-junior-basic.pdf
    advanced/  31-fall-2009-10-25-junior-advanced.pdf
  senior/
    basic/     31-fall-2009-10-18-senior-basic.pdf
    advanced/  31-fall-2009-10-25-senior-advanced.pdf
```

### Run the Full Corpus

```bash
python run_full.py
```

### Resume an Interrupted Run

```bash
python run_full.py          # Just re-run — checkpoint.json is read automatically
```

### Check Status

```bash
python run_full.py --status
```

---

## Output Structure

```
output/
  junior/               # 8–9 classes (O-level equivalent)
    basic/              # Basic / базовый variant
    advanced/           # Advanced / сложный variant
  senior/               # 10–11 classes (A-level equivalent)
    basic/
    advanced/
```

PDF naming: `{tournament}-{round}-{date}-{level}-{variant}.pdf`  
Example: `31-fall-2009-10-18-junior-basic.pdf`

---

## Inspecting the Work

| File | Contents |
|---|---|
| `manifest.json` | Full inventory: source URL, classification, problem count, SHA-256, status, cost |
| `manifest.csv` | Same data as CSV for spreadsheet use |
| `logs/run_trace.jsonl` | Per-call trace: model, tokens, cost, elapsed time, status |
| `logs/cost_ledger.jsonl` | Running spend ledger (cumulative total tracked here) |
| `logs/qa_notes.md` | Manual QA observations and page-by-page review notes |
| `logs/errors/` | Raw model outputs and stack traces for failed items |
| `checkpoint.json` | Resume state: processed and failed keys |
| `cache/` | Disk cache of fetched URLs (safe to delete to force refresh) |

---

## Model and Cost Choices

| Model | Role | Cost (input/output per 1M tokens) |
|---|---|---|
| `google/gemini-flash-1.5` | Primary translation | $0.075 / $0.30 |
| `meta-llama/llama-3.1-8b-instruct` | Fallback if primary fails | $0.055 / $0.055 |
| (none) | Already-English PDFs (2016+) | $0.00 |

**Why Gemini Flash 1.5?**  
Strong Russian-language understanding, excellent math notation fidelity, fast, and low cost. Remains well within the $5 cap even for the full corpus (~$0.44 estimated).

**$5 cap enforcement:**  
`harness/budget.py` estimates token cost before every API call and raises `BudgetExhaustedError` if the cap would be exceeded. The run stops gracefully.

---

## Prompts (Versioned)

All prompts live in `prompts/v1/`. To use a different prompt version:

```bash
PROMPT_VERSION=v2 python run_demo.py
```

Prompt files:
- `translate_problem_set.md` — Main translation prompt (math-preserving, JSON output, no solutions)
- `latex_template.tex.jinja` — LaTeX document template

---

## Key Design Decisions

1. **Solutions excluded at two levels**: the parser strips "Решение/Solution" headers from source text; the translation prompt also explicitly prohibits including solutions.
2. **Math preservation**: LaTeX delimiters (`$...$`, `\frac`, etc.) are passed through untouched. The prompt instructs the model not to alter them; the `renderer.py` `latex_safe` filter only escapes non-math text.
3. **No hard-coded API key**: Key loaded from env only. If missing, agent raises `EnvironmentError` with instructions — never silently falls back.
4. **Combined PDF splitting**: For older tournaments where one PDF contains both 8–9 and 10–11 class problems (e.g. `os31sl.pdf`), `parser.py` splits by section header and produces two separate output PDFs.
5. **Control sources disclosed**: Official English PDFs from 2016+ are used as QA controls only, not presented as translations. The `validator.py` compares against them and records divergence notes in the manifest.
6. **Resumable**: Every successfully processed item is checkpointed. Re-running is safe and idempotent.

---

## Architecture

```
run_demo.py / run_full.py
    └── harness/agent.py          (orchestration loop)
         ├── crawler.py           (inventory building)
         ├── fetcher.py           (cached HTTP)
         ├── parser.py            (HTML / PDF / DOC extraction)
         ├── translator.py        (OpenRouter API, math-safe prompts)
         ├── renderer.py          (pdflatex → WeasyPrint fallback)
         ├── validator.py         (5-check QA pipeline)
         ├── manifest.py          (JSON + CSV output)
         ├── budget.py            ($5 cap enforcement)
         ├── checkpoint.py        (resume support)
         └── classify.py          (level/variant mapping)
```

---

## Troubleshooting

**`OPENROUTER_API_KEY is not set`** → Edit `.env` and add your key.

**`pdflatex not found`** → Install [MiKTeX](https://miktex.org/) (Windows) or `texlive-latex-base` (Linux/Mac). WeasyPrint will be used automatically if pdflatex is absent.

**Old `.doc` files fail** → Install [LibreOffice](https://www.libreoffice.org/) and ensure `libreoffice` is on PATH. The parser will call it headlessly.

**Item stuck in `failed` state** → Check `logs/errors/<key>_error.txt`, fix the issue, then re-run (failed items are retried automatically).

"""
agent.py — Main agent loop: fetch → translate → render → validate → record.

Designed to be called by run_demo.py (4 targets) or run_full.py (full corpus).
Supports resume via checkpoint.json.
"""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import List, Optional
import io, sys

# Force UTF-8 on Windows to avoid CP-1252 encoding errors with Rich
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from harness import budget, checkpoint, fetcher, manifest
from harness.budget import BudgetExhaustedError
from harness.crawler import SourceRecord
from harness import parser, translator, renderer, validator

# Use a non-legacy console so Unicode characters render on Windows
console = Console(force_terminal=True, legacy_windows=False, highlight=False)


def run(
    sources: List[SourceRecord],
    resume: bool = True,
    dry_run: bool = False,
) -> dict:
    """
    Process a list of SourceRecord items.

    Args:
        sources:  List of SourceRecord objects to process
        resume:   If True, skip already-completed items (from checkpoint)
        dry_run:  If True, fetch and parse but do not call the translation API or render

    Returns:
        Summary dict with counts of ok/warn/error/skipped
    """
    counts = {"ok": 0, "warn": 0, "error": 0, "skipped": 0, "budget_stop": 0}

    console.rule("[bold blue]Tournament of Towns Archive Agent")
    console.print(f"[dim]Processing {len(sources)} source records. Resume={resume}, DryRun={dry_run}[/dim]")
    console.print(f"[dim]Budget: ${budget.spent():.4f} spent / ${budget.remaining():.4f} remaining of ${budget.HARD_CAP_USD}[/dim]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("Processing...", total=len(sources))

        for source in sources:
            progress.update(task, description=f"[cyan]{source.key}")

            # Skip excluded items
            if source.scope == "excluded":
                manifest.record_excluded(source, "; ".join(source.notes))
                counts["skipped"] += 1
                progress.advance(task)
                continue

            # Resume: skip already-done items
            if resume and checkpoint.is_done(source.key):
                counts["skipped"] += 1
                progress.advance(task)
                continue

            try:
                # ── 1. Fetch ──────────────────────────────────────────────
                console.print(f"\n[bold]→ {source.key}[/bold]")
                console.print(f"  Fetching: {source.source_url}")
                content, content_type, from_cache = fetcher.fetch(source.source_url)
                cache_indicator = "[dim](cached)[/dim]" if from_cache else "[dim](fetched)[/dim]"
                console.print(f"  Fetch OK {cache_indicator} — {len(content):,} bytes")

                # ── 2. Parse ──────────────────────────────────────────────
                console.print("  Parsing source...")
                parsed = parser.extract(content, content_type, source)
                n_problems = len(parsed.get("problems", []))
                console.print(f"  Parsed {n_problems} problems")
                if parsed.get("warnings"):
                    for w in parsed["warnings"]:
                        console.print(f"  [yellow]⚠ {w}[/yellow]")

                if dry_run:
                    console.print("  [dim][DRY RUN] Skipping translation and render[/dim]")
                    counts["ok"] += 1
                    progress.advance(task)
                    continue

                # ── 3. Translate ──────────────────────────────────────────
                if source.needs_translation:
                    console.print(f"  Translating via OpenRouter...")
                    translated = translator.translate(parsed, source)
                    console.print(
                        f"  Translated using {translated.get('translation_model')} "
                        f"(${translated.get('translation_cost_usd', 0):.6f})"
                    )
                else:
                    console.print("  [dim]Source is English — no translation needed[/dim]")
                    translated = {**parsed, "translation_model": "none (source is English)",
                                  "translation_cost_usd": 0.0}

                # ── 4. Render ─────────────────────────────────────────────
                console.print("  Rendering PDF...")
                pdf_path = renderer.render(translated, source)
                console.print(f"  PDF: {pdf_path} ({pdf_path.stat().st_size:,} bytes)")

                # ── 5. Validate ───────────────────────────────────────────
                console.print("  Validating...")
                status, issues = validator.validate(pdf_path, parsed, source)
                if issues:
                    for issue in issues:
                        color = "red" if issue.startswith("ERROR") else "yellow"
                        console.print(f"  [{color}]{issue}[/{color}]")

                status_color = {"ok": "green", "warn": "yellow", "error": "red"}.get(status, "white")
                console.print(f"  Status: [{status_color}]{status.upper()}[/{status_color}]")

                # ── 6. Record ─────────────────────────────────────────────
                manifest.record(source, pdf_path, status, issues, translated)
                checkpoint.save(source.key)
                counts[status] = counts.get(status, 0) + 1

            except BudgetExhaustedError as e:
                console.print(f"  [bold red]BUDGET CAP REACHED: {e}[/bold red]")
                manifest.record_failure(source, f"Budget cap: {e}")
                counts["budget_stop"] += 1
                break  # Stop processing

            except Exception as e:
                tb = traceback.format_exc()
                console.print(f"  [bold red]ERROR: {e}[/bold red]")
                err_log = Path("logs/errors") / f"{source.key}_error.txt"
                err_log.parent.mkdir(parents=True, exist_ok=True)
                err_log.write_text(tb, encoding="utf-8")
                manifest.record_failure(source, str(e))
                checkpoint.mark_failed(source.key, str(e))
                counts["error"] += 1

            finally:
                progress.advance(task)

    # ── Summary ───────────────────────────────────────────────────────────────
    console.rule("[bold blue]Run Complete")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Status", style="bold")
    table.add_column("Count", justify="right")
    for k, v in counts.items():
        color = {"ok": "green", "warn": "yellow", "error": "red",
                 "skipped": "dim", "budget_stop": "red"}.get(k, "white")
        table.add_row(f"[{color}]{k.upper()}[/{color}]", str(v))
    console.print(table)

    bud = budget.summary()
    console.print(
        f"\n[bold]Cost:[/bold] ${bud['spent_usd']:.4f} spent, "
        f"${bud['remaining_usd']:.4f} remaining of ${bud['cap_usd']}"
    )
    mfst = manifest.summary()
    console.print(f"[bold]Manifest:[/bold] {mfst['total']} records, "
                  f"{mfst['by_status']}")

    return counts

#!/usr/bin/env python3
"""
run_full.py — Run the agent on the complete Tournament of Towns archive.

Crawls turgor.ru for all available problem sets and processes each one.
Resumes from checkpoint.json automatically on re-run.

Usage:
    python run_full.py                  # Run / resume full corpus
    python run_full.py --fresh          # Start from scratch (dangerous if > $0 spent)
    python run_full.py --dry-run        # Fetch + parse only, no API or render
    python run_full.py --limit 10       # Process only first N unfished items
    python run_full.py --status         # Print current status and exit
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from harness.crawler import build_full_inventory
from harness import checkpoint, manifest, budget, agent


def main():
    parser = argparse.ArgumentParser(
        description="Run the Tournament of Towns archive agent (full corpus)"
    )
    parser.add_argument(
        "--fresh", action="store_true",
        help="Clear checkpoint and restart from the beginning"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Fetch and parse only — no API calls or PDF rendering"
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Maximum number of new items to process in this run"
    )
    parser.add_argument(
        "--status", action="store_true",
        help="Print current run status and exit"
    )
    args = parser.parse_args()

    if args.status:
        cp = checkpoint.stats()
        bud = budget.summary()
        mfst = manifest.summary()
        print(f"Checkpoint: {cp['processed']} done, {cp['failed']} failed")
        print(f"Budget: ${bud['spent_usd']:.4f} spent / ${bud['remaining_usd']:.4f} remaining")
        print(f"Manifest: {mfst['total']} records — {mfst['by_status']}")
        return

    if args.fresh:
        confirm = input(
            f"This will clear checkpoint.json and reprocess the full corpus.\n"
            f"Current spend: ${budget.spent():.4f}. Continue? [y/N] "
        )
        if confirm.lower() != "y":
            print("Aborted.")
            return
        checkpoint.reset()

    print("Building inventory from archive...")
    sources = build_full_inventory()
    print(f"Inventory: {len(sources)} source records")

    # Apply limit (skip already-done items, then cap)
    if args.limit:
        pending = [s for s in sources if not checkpoint.is_done(s.key)]
        sources = pending[:args.limit]
        print(f"Limiting to {len(sources)} pending items")

    counts = agent.run(sources, resume=not args.fresh, dry_run=args.dry_run)

    total_errors = counts.get("error", 0) + counts.get("budget_stop", 0)
    sys.exit(0 if total_errors == 0 else 1)


if __name__ == "__main__":
    main()

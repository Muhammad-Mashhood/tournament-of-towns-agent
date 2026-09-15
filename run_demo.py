#!/usr/bin/env python3
"""
run_demo.py — Run the agent on the 4 required demonstration targets only.

Targets:
  1. 18 October 2009, basic, 8-9 classes  → output/junior/basic/
  2. 18 October 2009, basic, 10-11 classes → output/senior/basic/
  3. 25 October 2009, advanced, 8-9 classes → output/junior/advanced/
  4. 25 October 2009, advanced, 10-11 classes → output/senior/advanced/

Usage:
    python run_demo.py            # Run all 4 demo targets
    python run_demo.py --fresh    # Re-run from scratch (ignore checkpoint)
    python run_demo.py --dry-run  # Fetch + parse only, no API calls
"""

import argparse
import os
import sys

# Ensure we can import harness from project root
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from harness.crawler import build_demo_inventory
from harness import checkpoint, agent

DEMO_KEYS = [
    "31-fall-2009-10-18-junior-basic",
    "31-fall-2009-10-18-senior-basic",
    "31-fall-2009-10-25-junior-advanced",
    "31-fall-2009-10-25-senior-advanced",
]


def main():
    parser = argparse.ArgumentParser(
        description="Run the Tournament of Towns agent on the 4 demo targets"
    )
    parser.add_argument(
        "--fresh", action="store_true",
        help="Ignore checkpoint and reprocess all demo targets"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Fetch and parse only — do not call translation API or render PDFs"
    )
    args = parser.parse_args()

    if args.fresh:
        print("Resetting checkpoint for demo targets...")
        # Only reset the demo keys, not the full checkpoint
        data = checkpoint._load()
        for key in DEMO_KEYS:
            if key in data["processed"]:
                data["processed"].remove(key)
            data["failed"].pop(key, None)
        checkpoint._save(data)

    sources = build_demo_inventory()
    print(f"\nDemo targets ({len(sources)}):")
    for s in sources:
        print(f"  {s.key}")
        print(f"    Level: {s.level}  Variant: {s.variant}")
        print(f"    Source: {s.source_url}")
        print(f"    Type: {s.source_type}  Translate: {s.needs_translation}")
    print()

    counts = agent.run(sources, resume=not args.fresh, dry_run=args.dry_run)
    
    total_errors = counts.get("error", 0) + counts.get("budget_stop", 0)
    sys.exit(0 if total_errors == 0 else 1)


if __name__ == "__main__":
    main()

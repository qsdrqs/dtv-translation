#!/usr/bin/env python3
"""Merge batch result JSONs from parallel workers and print summary.

Usage:
    .venv/bin/python merge_results.py [--result-dir DIR] [--output PATH]

Reads all result/ab_batch_*.json files, merges into a single JSON,
and prints the A/B comparison table.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from run_ab_experiment import RunResult, print_summary

DEFAULT_RESULT_DIR = Path("result")
DEFAULT_OUTPUT = DEFAULT_RESULT_DIR / "ab_merged_results.json"


def load_batch_files(result_dir: Path) -> list[dict]:
    """Load and merge all ab_batch_*.json files."""
    batch_files = sorted(result_dir.glob("ab_batch_*.json"))
    if not batch_files:
        print(f"ERROR: no ab_batch_*.json files found in {result_dir}", file=sys.stderr)
        sys.exit(1)

    all_records: list[dict] = []
    for f in batch_files:
        records = json.loads(f.read_text(encoding="utf-8"))
        print(f"  {f.name}: {len(records)} records", file=sys.stderr)
        all_records.extend(records)

    return all_records


def records_to_results(records: list[dict]) -> list[RunResult]:
    """Convert raw dicts to RunResult dataclass instances."""
    results: list[RunResult] = []
    for r in records:
        results.append(RunResult(
            case_id=r["case_id"],
            config=r["config"],
            final_verdict=r["final_verdict"],
            total_tokens=r["total_tokens"],
            total_steps=r["total_steps"],
            elapsed_s=r["elapsed_s"],
            verify_count=r["verify_count"],
            feedback_count=r["feedback_count"],
            rollback_count=r["rollback_count"],
            commit_count=r["commit_count"],
            compiles=r["compiles"],
            test_passed=r["test_passed"],
            test_total=r["test_total"],
        ))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge batch A/B experiment results")
    parser.add_argument(
        "--result-dir",
        type=Path,
        default=DEFAULT_RESULT_DIR,
        help=f"Directory containing ab_batch_*.json (default: {DEFAULT_RESULT_DIR})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Merged output JSON path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    result_dir: Path = args.result_dir
    output_path: Path = args.output

    print(f"Scanning {result_dir} for batch files...", file=sys.stderr)
    all_records = load_batch_files(result_dir)

    # Dedup by (case_id, config) - last write wins
    seen: dict[tuple[str, str], dict] = {}
    for r in all_records:
        key = (r["case_id"], r["config"])
        if key in seen:
            print(f"  WARNING: duplicate {key}, keeping latest", file=sys.stderr)
        seen[key] = r
    deduped = list(seen.values())

    results = records_to_results(deduped)

    # Count cases with both DTV and naive results
    dtv_ids = {r.case_id for r in results if r.config == "dtv"}
    naive_ids = {r.case_id for r in results if r.config == "naive"}
    paired = dtv_ids & naive_ids
    dtv_only = dtv_ids - naive_ids
    naive_only = naive_ids - dtv_ids

    print(
        f"\nMerged: {len(deduped)} records, "
        f"{len(paired)} paired cases, "
        f"{len(dtv_only)} DTV-only, "
        f"{len(naive_only)} naive-only",
        file=sys.stderr,
    )

    # Save merged results
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(deduped, indent=2), encoding="utf-8"
    )
    print(f"Saved: {output_path}\n", file=sys.stderr)

    # Print summary table
    print_summary(results)


if __name__ == "__main__":
    main()

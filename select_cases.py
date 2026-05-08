#!/usr/bin/env python3
"""Select reproducible case subsets for A/B experiments.

Scans the dataset directory, filters cases that have valid test inputs
(non-binary files in testcases/), shuffles with a fixed seed, and
outputs the selected case IDs.

Usage:
    .venv/bin/python select_cases.py [--count N] [--seed S] [--dataset-dir DIR]

Examples:
    # Select 100 cases (default)
    .venv/bin/python select_cases.py

    # Select 50 cases with custom seed
    .venv/bin/python select_cases.py --count 50 --seed 123
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from pathlib import Path

DEFAULT_SEED = 42
DEFAULT_COUNT = 100
DEFAULT_DATASET_DIR = Path(
    os.environ.get(
        "DTV_DATASET_DIR",
        "/home/qsdrqs/projects/agent_fuzz/selected_data_output",
    )
)


def find_valid_cases(dataset_dir: Path) -> list[str]:
    """Return sorted list of case IDs that have at least one valid test input."""
    valid: list[str] = []
    for entry in sorted(dataset_dir.iterdir()):
        if not entry.is_dir():
            continue
        source_c = entry / "source.c"
        testcases_dir = entry / "testcases"
        if not source_c.exists() or not testcases_dir.is_dir():
            continue
        # Check for at least one input file
        has_input = any(f.name.startswith("input_") for f in testcases_dir.iterdir())
        if has_input:
            valid.append(entry.name)
    return valid


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Select reproducible case subsets for A/B experiments"
    )
    parser.add_argument(
        "--count",
        type=int,
        default=DEFAULT_COUNT,
        help=f"Number of cases to select (default: {DEFAULT_COUNT})",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"Random seed for reproducibility (default: {DEFAULT_SEED})",
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=DEFAULT_DATASET_DIR,
        help="Dataset root directory (default: $DTV_DATASET_DIR)",
    )
    args = parser.parse_args()

    dataset_dir: Path = args.dataset_dir
    count: int = args.count
    seed: int = args.seed

    if not dataset_dir.is_dir():
        print(f"ERROR: dataset directory not found: {dataset_dir}", file=sys.stderr)
        sys.exit(1)

    all_dirs = [d for d in dataset_dir.iterdir() if d.is_dir()]
    valid_cases = find_valid_cases(dataset_dir)

    print(
        f"Dataset: {dataset_dir}\n"
        f"Total directories: {len(all_dirs)}\n"
        f"Valid cases (have testcases with decodable inputs): {len(valid_cases)}\n"
        f"Seed: {seed}",
        file=sys.stderr,
    )

    if count > len(valid_cases):
        print(
            f"WARNING: requested {count} cases but only {len(valid_cases)} available. "
            f"Using all {len(valid_cases)}.",
            file=sys.stderr,
        )
        count = len(valid_cases)

    rng = random.Random(seed)
    selected = valid_cases[:]  # copy before shuffle
    rng.shuffle(selected)
    selected = selected[:count]

    print(f"Selected: {count} cases\n", file=sys.stderr)

    # Output one case ID per line to stdout (pipe-friendly)
    for case_id in selected:
        print(case_id)


if __name__ == "__main__":
    main()

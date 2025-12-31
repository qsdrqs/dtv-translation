#!/usr/bin/env python3
"""
check_trailing.py

Recursively checks the current directory (or --root) for trailing spaces:
  1) Lines ending with whitespace (spaces or tabs)
  2) Lines containing only whitespace

Use --fix to automatically remove trailing whitespace and empty whitespace-only lines.

Exit codes:
  0: No trailing whitespace found
  1: Trailing whitespace found
  2: Unexpected error
"""

import argparse
import fnmatch
import os
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence


DEFAULT_EXCLUDE_DIRS = {
    ".git",
    "__pycache__",
    ".direnv",
    ".venv",
    "node_modules",
    "build",
    "dist",
}

DEFAULT_EXCLUDE_GLOBS = (
    "*.pyc",
    "*.so",
    "*.dll",
    "*.exe",
)

DEFAULT_BINARY_EXTS = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svgz",
    ".zip",
    ".gz",
    ".bz2",
    ".xz",
    ".7z",
    ".tar",
    ".tgz",
    ".ttf",
    ".otf",
    ".woff",
    ".woff2",
    ".pyc",
}


@dataclass(frozen=True)
class Finding:
    """Represents a trailing whitespace finding in a file."""

    kind: str  # "trailing" or "empty"
    path: Path
    line_no: int
    detail: str  # Excerpt of the line


def iter_paths(root: Path, exclude_dirs: set[str]) -> Iterator[Path]:
    # Walk the tree and skip excluded directories.
    for dirpath, dirnames, filenames in os.walk(root):
        # Mutate dirnames in-place to prune walk.
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
        base = Path(dirpath)
        for name in filenames:
            yield base / name


def looks_binary(path: Path, sample_size: int = 8192) -> bool:
    # Heuristic: if there is a NUL byte, or lots of non-text control bytes, treat as binary.
    try:
        with path.open("rb") as f:
            data = f.read(sample_size)
    except OSError:
        return False
    if b"\x00" in data:
        return True

    if not data:
        return False

    # Allow common whitespace and typical text controls; flag other controls.
    allowed = set(b"\t\n\r\f\b")
    control = 0
    for b in data:
        if b < 32 and b not in allowed:
            control += 1
    return (control / max(1, len(data))) > 0.05


def should_skip_file(
    path: Path, include_all: bool, exclude_globs: Sequence[str]
) -> bool:
    name = path.name
    for g in exclude_globs:
        if fnmatch.fnmatch(name, g) or fnmatch.fnmatch(str(path), g):
            return True

    if include_all:
        return False

    # Quick extension-based skip for common binaries.
    if path.suffix.lower() in DEFAULT_BINARY_EXTS:
        return True

    # Heuristic binary detection.
    return looks_binary(path)


def has_trailing_whitespace(line: str) -> bool:
    """Return True if line ends with spaces or tabs."""
    return len(line) > 0 and line[-1] in (" ", "\t")


def is_whitespace_only(line: str) -> bool:
    """Return True if line consists only of whitespace characters."""
    return len(line) > 0 and all(c in (" ", "\t") for c in line)


def clean_line(line: str) -> str:
    """Remove trailing whitespace. If line is whitespace-only, return empty string."""
    cleaned = line.rstrip(" \t")
    if all(c in (" ", "\t") for c in cleaned):
        return ""
    return cleaned


def process_file(path: Path, fix: bool) -> tuple[list[Finding], bool]:
    """
    Scan a file for trailing whitespace and whitespace-only lines.
    If fix is True, rewrite the file with cleaned lines.
    Returns (list of findings, whether file was modified).
    """
    findings = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except (OSError, UnicodeDecodeError):
        return [], False

    modified = False
    cleaned_lines = []

    for i, line in enumerate(lines, 1):
        original = line
        # Remove trailing newline for analysis
        if line.endswith("\n"):
            line = line[:-1]
        else:
            # Last line may not have newline
            pass

        trailing = has_trailing_whitespace(line)
        empty = is_whitespace_only(line)

        if trailing:
            findings.append(
                Finding(
                    kind="trailing",
                    path=path,
                    line_no=i,
                    detail=f"'{line[-20:]}...'" if len(line) > 20 else f"'{line}'",
                )
            )
        if empty:
            findings.append(
                Finding(kind="empty", path=path, line_no=i, detail="(whitespace only)")
            )

        if fix:
            cleaned = clean_line(line)
            # Preserve newline if original had one
            if original.endswith("\n"):
                cleaned_lines.append(cleaned + "\n")
            else:
                cleaned_lines.append(cleaned)
            if cleaned != line:
                modified = True
        else:
            cleaned_lines.append(original)

    if fix and modified:
        try:
            path.write_text("".join(cleaned_lines), encoding="utf-8", newline="")
        except OSError:
            # If write fails, return findings but not modified
            return findings, False
        return findings, True

    return findings, False


def scan_tree(
    root: Path,
    *,
    include_all: bool,
    exclude_dirs: set[str],
    exclude_globs: Sequence[str],
    fix: bool,
) -> tuple[list[Finding], list[Path]]:
    """
    Scan all files in the tree.
    Returns (list of findings, list of modified files).
    """
    findings = []
    modified_files = []

    for path in iter_paths(root, exclude_dirs=exclude_dirs):
        if not path.is_file():
            continue
        if should_skip_file(path, include_all=include_all, exclude_globs=exclude_globs):
            continue

        file_findings, modified = process_file(path, fix=fix)
        findings.extend(file_findings)
        if modified:
            modified_files.append(path)

    return findings, modified_files


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Check for trailing whitespace and whitespace-only lines."
    )
    p.add_argument(
        "--root",
        default=".",
        help="Root directory to scan (default: current directory).",
    )
    p.add_argument(
        "--all",
        action="store_true",
        help="Include likely-binary files (PDFs/images/etc). By default they are skipped.",
    )
    p.add_argument(
        "--fix",
        action="store_true",
        help="Automatically remove trailing whitespace and empty whitespace-only lines.",
    )
    p.add_argument(
        "--exclude-dir",
        action="append",
        default=[],
        help="Directory name to exclude (can be repeated).",
    )
    p.add_argument(
        "--exclude-glob",
        action="append",
        default=list(DEFAULT_EXCLUDE_GLOBS),
        help="Glob to exclude files (can be repeated), matched against name and relative path.",
    )
    p.add_argument(
        "--max-findings",
        type=int,
        default=100,
        help="Maximum number of findings to display (default: 100).",
    )
    return p.parse_args(list(argv))


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    root = Path(args.root).resolve()

    exclude_dirs = set(DEFAULT_EXCLUDE_DIRS)
    exclude_dirs.update(args.exclude_dir)

    findings, modified_files = scan_tree(
        root,
        include_all=bool(args.all),
        exclude_dirs=exclude_dirs,
        exclude_globs=tuple(args.exclude_glob),
        fix=bool(args.fix),
    )

    if modified_files:
        print(f"Fixed {len(modified_files)} files:")
        for f in modified_files:
            rel = f.relative_to(root)
            print(f"  - {rel}")

    if findings:
        print(f"Found {len(findings)} issues (showing up to {args.max_findings}):")
        for i, f in enumerate(findings[: args.max_findings]):
            rel = f.path.relative_to(root)
            print(f"  - [{f.kind}] {rel}:{f.line_no} {f.detail}")
        if len(findings) > args.max_findings:
            print(f"  ... and {len(findings) - args.max_findings} more findings")
        return 1
    else:
        if args.fix:
            print("OK: No trailing whitespace found (or all fixed).")
        else:
            print("OK: No trailing whitespace found.")
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(2)

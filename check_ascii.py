#!/usr/bin/env python3
"""
check_ascii.py

Recursively checks the current directory (or --root) for non-ASCII:
  1) Filenames / path components containing non-ASCII characters
  2) Text file contents containing non-ASCII characters

By default, likely-binary files are skipped to avoid flagging PDFs/images.
Use --all to include every file (including binaries).

Optionally, use --replace to automatically rewrite common non-ASCII characters
into ASCII equivalents (via a maintained default mapping).

Exit codes:
  0: No non-ASCII found
  1: Non-ASCII found
  2: Unexpected error
"""

from __future__ import annotations

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
    "latex.out",
    ".venv"
}

DEFAULT_EXCLUDE_GLOBS = (
    "*.bst",
    "*.sty",
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

# Common non-ASCII characters that frequently appear in papers.
# Values must be ASCII-only strings. These defaults are LaTeX-friendly.
DEFAULT_REPLACEMENTS: dict[str, str] = {
    "\u2010": "-",  # hyphen
    "\u2011": "-",  # non-breaking hyphen
    "\u2012": "-",  # figure dash
    "\u2013": "--",  # en dash
    "\u2014": "---",  # em dash
    "\u2018": "`",  # left single quote
    "\u2019": "'",  # right single quote / apostrophe
    "\u201A": ",",  # single low-9 quote
    "\u201C": "``",  # left double quote
    "\u201D": "''",  # right double quote
    "\u201E": ",,",  # double low-9 quote
    "\u2026": "...",  # ellipsis
    "\u00D7": "$\\times$",  # multiplication sign
    "\u00B1": "$\\pm$",  # plus-minus
    "\u00E9": "\\'e",  # e-acute
}


@dataclass(frozen=True)
class Finding:
    """Represents a non-ASCII finding in a path or file."""
    kind: str  # "path" or "content"
    path: Path
    detail: str  # Non-ASCII excerpt or filename component.


def is_ascii_str(value: str) -> bool:
    try:
        value.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def validate_replacements(replacements: dict[str, str]) -> None:
    for src, dst in replacements.items():
        if not isinstance(src, str) or len(src) != 1:
            raise ValueError(f"Replacement key must be a single character: {src!r}")
        if not isinstance(dst, str) or not is_ascii_str(dst):
            raise ValueError(f"Replacement value must be ASCII-only: {src!r} -> {dst!r}")


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


def should_skip_file(path: Path, include_all: bool, exclude_globs: Sequence[str]) -> bool:
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


def apply_replacements_to_text(text: str, replacements: dict[str, str]) -> tuple[str, Counter[str]]:
    counts: Counter[str] = Counter()
    if not replacements:
        return text, counts

    # Fast path: avoid allocating if nothing to change.
    if not any(ch in text for ch in replacements):
        return text, counts

    out: list[str] = []
    for ch in text:
        repl = replacements.get(ch)
        if repl is None:
            out.append(ch)
        else:
            out.append(repl)
            counts[ch] += 1
    return "".join(out), counts


def replace_in_file(path: Path, replacements: dict[str, str]) -> Counter[str]:
    """
    Applies replacements to a UTF-8 text file in-place.
    Returns a Counter of replaced characters (empty if no changes or not decodable).
    """
    try:
        raw = path.read_bytes()
    except OSError:
        return Counter()

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return Counter()

    new_text, counts = apply_replacements_to_text(text, replacements=replacements)
    if not counts:
        return Counter()

    try:
        path.write_text(new_text, encoding="utf-8", newline="")
    except OSError:
        return Counter()

    return counts


def replace_tree(
    root: Path,
    *,
    include_all: bool,
    exclude_dirs: set[str],
    exclude_globs: Sequence[str],
    replacements: dict[str, str],
) -> Counter[str]:
    validate_replacements(replacements)

    total: Counter[str] = Counter()
    for path in iter_paths(root, exclude_dirs=exclude_dirs):
        if not path.is_file():
            continue
        if should_skip_file(path, include_all=include_all, exclude_globs=exclude_globs):
            continue
        total.update(replace_in_file(path, replacements=replacements))
    return total


def find_non_ascii_in_text(path: Path, max_hits: int) -> list[str]:
    """
    Returns a list of human-readable descriptions of the first `max_hits`
    non-ASCII characters in the file (line/column + a short snippet).
    """
    hits: list[str] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
            for line_no, line in enumerate(f, start=1):
                for col_no, ch in enumerate(line, start=1):
                    if ord(ch) > 127:
                        codepoint = f"U+{ord(ch):04X}"
                        hits.append(f"line {line_no}, col {col_no}: {codepoint} ({ch!r})")
                        if len(hits) >= max_hits:
                            return hits
    except OSError as e:
        return [f"Could not read file: {e}"]
    return hits


def find_non_ascii_in_path(path: Path) -> list[str]:
    parts = list(path.parts)
    bad = [p for p in parts if not is_ascii_str(p)]
    if not bad:
        return []
    return [f"non-ASCII path component: {p!r}" for p in bad]


def scan(
    root: Path,
    *,
    include_all: bool,
    exclude_dirs: set[str],
    exclude_globs: Sequence[str],
    max_hits_per_file: int,
) -> list[Finding]:
    findings: list[Finding] = []
    for path in iter_paths(root, exclude_dirs=exclude_dirs):
        if not path.is_file():
            continue

        # Check path components first (even for skipped binaries).
        for detail in find_non_ascii_in_path(path.relative_to(root)):
            findings.append(Finding(kind="path", path=path, detail=detail))

        if should_skip_file(path, include_all=include_all, exclude_globs=exclude_globs):
            continue

        hits = find_non_ascii_in_text(path, max_hits=max_hits_per_file)
        if hits:
            for h in hits:
                findings.append(Finding(kind="content", path=path, detail=h))
    return findings


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Check for non-ASCII in paths and file contents.")
    p.add_argument("--root", default=".", help="Root directory to scan (default: current directory).")
    p.add_argument(
        "--all",
        action="store_true",
        help="Include likely-binary files (PDFs/images/etc). By default they are skipped.",
    )
    p.add_argument(
        "--replace",
        action="store_true",
        help="In-place replace common non-ASCII characters with ASCII equivalents.",
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
        "--max-hits-per-file",
        type=int,
        default=10,
        help="Max number of non-ASCII hits to report per file (default: 10).",
    )
    return p.parse_args(list(argv))


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    root = Path(args.root).resolve()

    exclude_dirs = set(DEFAULT_EXCLUDE_DIRS)
    exclude_dirs.update(args.exclude_dir)

    if args.replace:
        replaced = replace_tree(
            root,
            include_all=bool(args.all),
            exclude_dirs=exclude_dirs,
            exclude_globs=tuple(args.exclude_glob),
            replacements=DEFAULT_REPLACEMENTS,
        )
        if replaced:
            total = sum(replaced.values())
            print(f"APPLIED replacements: {total}")
            for ch, n in replaced.most_common():
                cp = f"U+{ord(ch):04X}"
                print(f"- {cp} ({ch!r}): {n}")

    findings = scan(
        root,
        include_all=bool(args.all),
        exclude_dirs=exclude_dirs,
        exclude_globs=tuple(args.exclude_glob),
        max_hits_per_file=int(args.max_hits_per_file),
    )

    if not findings:
        print("OK: no non-ASCII found.")
        return 0

    print("FOUND non-ASCII:")
    for f in findings:
        rel = f.path.relative_to(root)
        print(f"- [{f.kind}] {rel}: {f.detail}")
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(2)

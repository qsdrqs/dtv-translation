from __future__ import annotations

"""Filter TypeWeaver packages into a bundled JS dataset.

Usage:
    .venv/bin/python -m js_ts.dataset.filter_typeweaver \
        --input /path/to/TypeWeaver/data/full/original \
        --output dataset_js_ts/ \
        --min-loc 30 --max-loc 1000 \
        [--subsets top1k-typed-nodeps-es6,top1k-untyped-nodeps-es6]
"""

import argparse
from collections import Counter
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from js_ts.oracles.compiler_oracle.tsc_driver import _find_type_roots

DEFAULT_SUBSETS = ["top1k-typed-nodeps-es6", "top1k-untyped-nodeps-es6"]
DEFAULT_MIN_LOC = 30
DEFAULT_MAX_LOC = 1000
DEFAULT_TIMEOUT_S = 30
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_ROLLUP_FALLBACK = Path.home() / ".local" / "bin" / "rollup"
_DEFAULT_TSC_FALLBACK = _PROJECT_ROOT / "node_modules" / ".bin" / "tsc"
_TSC_ERROR_RE = re.compile(r"\berror TS\d+:")
_TSC_SUMMARY_RE = re.compile(r"Found\s+(\d+)\s+errors?", re.IGNORECASE)


@dataclass(frozen=True)
class PackageSpec:
    subset: str
    package_dir: Path
    package_name: str
    output_name: str


@dataclass(frozen=True)
class CommandResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False


@dataclass
class FilterStats:
    total_packages_scanned: int = 0
    no_entry_point_found: int = 0
    rollup_bundle_failed: int = 0
    loc_out_of_range: int = 0
    too_small: int = 0
    too_large: int = 0
    tsc_already_passes: int = 0
    valid_output: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Filter TypeWeaver packages into a bundled JS dataset"
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="TypeWeaver original data directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output dataset directory",
    )
    parser.add_argument(
        "--min-loc",
        type=int,
        default=DEFAULT_MIN_LOC,
        help=f"Minimum bundled LOC (default: {DEFAULT_MIN_LOC})",
    )
    parser.add_argument(
        "--max-loc",
        type=int,
        default=DEFAULT_MAX_LOC,
        help=f"Maximum bundled LOC (default: {DEFAULT_MAX_LOC})",
    )
    parser.add_argument(
        "--subsets",
        type=str,
        default=",".join(DEFAULT_SUBSETS),
        help=(
            "Comma-separated TypeWeaver subsets "
            f"(default: {','.join(DEFAULT_SUBSETS)})"
        ),
    )
    args = parser.parse_args()

    if args.min_loc < 0:
        parser.error("--min-loc must be non-negative")
    if args.min_loc > args.max_loc:
        parser.error("--min-loc must be <= --max-loc")

    args.subsets = parse_subsets(args.subsets)
    if not args.subsets:
        parser.error("--subsets must include at least one subset")

    return args


def parse_subsets(raw_value: str) -> list[str]:
    return [part.strip() for part in raw_value.split(",") if part.strip()]


def main() -> None:
    args = parse_args()
    input_dir: Path = args.input
    output_dir: Path = args.output
    min_loc: int = args.min_loc
    max_loc: int = args.max_loc
    subsets: list[str] = args.subsets

    if not input_dir.is_dir():
        raise SystemExit(f"input directory not found: {input_dir}")

    package_specs = discover_package_specs(input_dir, subsets)
    rollup_command = resolve_executable("rollup", (_DEFAULT_ROLLUP_FALLBACK,))
    tsc_command = resolve_executable("tsc", (_DEFAULT_TSC_FALLBACK,))
    type_roots = _find_type_roots()

    output_dir.mkdir(parents=True, exist_ok=True)
    stats = FilterStats(total_packages_scanned=len(package_specs))
    for package_spec in package_specs:
        process_package(
            package_spec=package_spec,
            output_dir=output_dir,
            min_loc=min_loc,
            max_loc=max_loc,
            rollup_command=rollup_command,
            tsc_command=tsc_command,
            type_roots=type_roots,
            stats=stats,
        )

    print(build_summary_report(input_dir, output_dir, subsets, min_loc, max_loc, stats), file=sys.stderr)


def discover_package_specs(input_dir: Path, subsets: list[str]) -> list[PackageSpec]:
    discovered_names: list[tuple[str, str, Path]] = []
    for subset in subsets:
        subset_dir = input_dir / subset
        if not subset_dir.is_dir():
            raise SystemExit(f"subset directory not found: {subset_dir}")
        for package_dir in sorted(subset_dir.iterdir()):
            if not package_dir.is_dir():
                continue
            package_name = read_package_name(package_dir)
            discovered_names.append((subset, package_name, package_dir))

    name_counts = Counter(package_name for _, package_name, _ in discovered_names)
    specs: list[PackageSpec] = []
    for subset, package_name, package_dir in discovered_names:
        output_name = build_output_name(
            package_name=package_name,
            subset=subset,
            has_collision=name_counts[package_name] > 1,
        )
        specs.append(
            PackageSpec(
                subset=subset,
                package_dir=package_dir,
                package_name=package_name,
                output_name=output_name,
            )
        )
    return specs


def read_package_name(package_dir: Path) -> str:
    manifest = read_package_manifest(package_dir)
    if manifest is None:
        return package_dir.name
    package_name = manifest.get("name")
    if isinstance(package_name, str) and package_name:
        return package_name
    return package_dir.name


def read_package_manifest(package_dir: Path) -> dict[str, object] | None:
    package_json = package_dir / "package.json"
    if not package_json.is_file():
        return None
    try:
        payload = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def build_output_name(package_name: str, subset: str, has_collision: bool) -> str:
    sanitized_name = package_name.replace("/", "_")
    if has_collision:
        return f"{subset}__{sanitized_name}"
    return sanitized_name


def process_package(
    package_spec: PackageSpec,
    output_dir: Path,
    min_loc: int,
    max_loc: int,
    rollup_command: str,
    tsc_command: str,
    type_roots: str | None,
    stats: FilterStats,
) -> None:
    entry_info = resolve_entry_point(package_spec.package_dir)
    if entry_info is None:
        stats.no_entry_point_found += 1
        return

    original_entry, entry_path = entry_info
    rollup_result = run_rollup(entry_path, package_spec.package_dir, rollup_command)
    if rollup_result.exit_code != 0:
        stats.rollup_bundle_failed += 1
        return

    bundled_source = rollup_result.stdout
    bundled_loc = count_loc(bundled_source)
    if bundled_loc < min_loc or bundled_loc > max_loc:
        stats.loc_out_of_range += 1
        if bundled_loc < min_loc:
            stats.too_small += 1
        else:
            stats.too_large += 1
        return

    tsc_result = run_tsc_rejection_check(bundled_source, tsc_command, type_roots)
    if tsc_result.exit_code == 0:
        stats.tsc_already_passes += 1
        return

    save_package(
        package_spec=package_spec,
        output_dir=output_dir,
        bundled_source=bundled_source,
        original_entry=original_entry,
        bundled_loc=bundled_loc,
        tsc_error_count=count_tsc_errors(tsc_result),
    )
    stats.valid_output += 1


def resolve_entry_point(package_dir: Path) -> tuple[str, Path] | None:
    manifest = read_package_manifest(package_dir)
    main_value = "index.js"
    if manifest is not None:
        manifest_main = manifest.get("main")
        if isinstance(manifest_main, str) and manifest_main:
            main_value = manifest_main

    candidate = package_dir / main_value
    if candidate.is_file():
        return candidate.relative_to(package_dir).as_posix(), candidate.resolve()

    if candidate.suffix == "":
        js_candidate = candidate.with_suffix(".js")
        if js_candidate.is_file():
            return js_candidate.relative_to(package_dir).as_posix(), js_candidate.resolve()

    return None


def run_rollup(entry_path: Path, package_dir: Path, rollup_command: str) -> CommandResult:
    cmd = [rollup_command, str(entry_path), "--format", "es"]
    try:
        completed = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            cwd=package_dir,
            timeout=DEFAULT_TIMEOUT_S,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"rollup not found: {rollup_command}") from exc
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            stdout=coerce_subprocess_output(exc.stdout),
            stderr=coerce_subprocess_output(exc.stderr),
            exit_code=124,
            timed_out=True,
        )
    except OSError as exc:
        raise RuntimeError(f"rollup invocation failed: {exc}") from exc

    return CommandResult(
        stdout=completed.stdout,
        stderr=completed.stderr,
        exit_code=completed.returncode,
        timed_out=False,
    )


def run_tsc_rejection_check(
    bundled_source: str,
    tsc_command: str,
    type_roots: str | None,
) -> CommandResult:
    with tempfile.TemporaryDirectory(prefix="typeweaver-tsc-") as tmpdir:
        source_path = Path(tmpdir) / "bundle.ts"
        source_path.write_text(bundled_source, encoding="utf-8")

        cmd = [
            tsc_command,
            "--strict",
            "--noEmit",
            "--target",
            "ES2020",
            "--lib",
            "ES2020,DOM",
            "--skipLibCheck",
            "--pretty",
            "false",
        ]
        if type_roots is not None:
            cmd.extend(["--typeRoots", type_roots])
        cmd.append(str(source_path))

        try:
            completed = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=DEFAULT_TIMEOUT_S,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(f"tsc not found: {tsc_command}") from exc
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                stdout=coerce_subprocess_output(exc.stdout),
                stderr=coerce_subprocess_output(exc.stderr),
                exit_code=124,
                timed_out=True,
            )
        except OSError as exc:
            raise RuntimeError(f"tsc invocation failed: {exc}") from exc

    return CommandResult(
        stdout=completed.stdout,
        stderr=completed.stderr,
        exit_code=completed.returncode,
        timed_out=False,
    )


def save_package(
    package_spec: PackageSpec,
    output_dir: Path,
    bundled_source: str,
    original_entry: str,
    bundled_loc: int,
    tsc_error_count: int,
) -> None:
    package_output_dir = output_dir / package_spec.output_name
    package_output_dir.mkdir(parents=True, exist_ok=True)
    (package_output_dir / "source.js").write_text(bundled_source, encoding="utf-8")

    metadata = {
        "package_name": package_spec.package_name,
        "subset": package_spec.subset,
        "original_entry": original_entry,
        "original_files": count_original_files(package_spec.package_dir),
        "bundled_loc": bundled_loc,
        "tsc_error_count": tsc_error_count,
        "source_dir": str(package_spec.package_dir.resolve()),
    }
    metadata_path = package_output_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")


def count_original_files(package_dir: Path) -> int:
    return sum(1 for path in package_dir.rglob("*.js") if path.is_file())


def count_loc(source_text: str) -> int:
    return len(source_text.splitlines())


def count_tsc_errors(result: CommandResult) -> int:
    combined_output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    summary_matches = _TSC_SUMMARY_RE.findall(combined_output)
    if summary_matches:
        return int(summary_matches[-1])
    error_count = len(_TSC_ERROR_RE.findall(combined_output))
    if error_count > 0:
        return error_count
    if result.exit_code != 0:
        return 1
    return 0


def build_summary_report(
    input_dir: Path,
    output_dir: Path,
    subsets: list[str],
    min_loc: int,
    max_loc: int,
    stats: FilterStats,
) -> str:
    return (
        "TypeWeaver Filter Report\n"
        "========================\n"
        f"Input: {input_dir}\n"
        f"Subsets: {', '.join(subsets)}\n"
        f"LOC range: {min_loc}-{max_loc}\n"
        "\n"
        f"Total packages scanned: {stats.total_packages_scanned:6d}\n"
        f"  No entry point found: {stats.no_entry_point_found:6d}\n"
        f"  Rollup bundle failed: {stats.rollup_bundle_failed:6d}\n"
        f"  LOC out of range: {stats.loc_out_of_range:6d}\n"
        f"    Too small (<{min_loc}): {stats.too_small:6d}\n"
        f"    Too large (>{max_loc}): {stats.too_large:6d}\n"
        f"  tsc already passes: {stats.tsc_already_passes:6d}\n"
        "  ------------------------\n"
        f"  Valid (output): {stats.valid_output:6d}\n"
        "\n"
        f"Output: {output_dir}"
    )


def resolve_executable(name: str, fallbacks: tuple[Path, ...]) -> str:
    resolved = shutil.which(name)
    if resolved is not None:
        return resolved
    for fallback in fallbacks:
        if fallback.is_file() and os.access(fallback, os.X_OK):
            return str(fallback)
    raise RuntimeError(f"executable not found: {name}")


def coerce_subprocess_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


if __name__ == "__main__":
    main()

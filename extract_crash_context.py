#!/usr/bin/env python3
"""Extract crash context from slurm worker logs.

Usage:
    .venv/bin/python extract_crash_context.py result_delta/slurm_worker_11.out
    .venv/bin/python extract_crash_context.py result_delta/slurm_worker_*.out
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


CONTEXT_LINES_BEFORE = 120


def extract_crash(log_path: Path) -> None:
    text = log_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    crash_line = None
    for i, line in enumerate(lines):
        if "invalid_write_region_payload" in line or "write-region state diverged" in line:
            crash_line = i
            break

    if crash_line is None:
        return

    # Find the Traceback start
    tb_start = crash_line
    for i in range(crash_line, max(crash_line - 30, 0), -1):
        if lines[i].startswith("Traceback"):
            tb_start = i
            break

    # Find crash case
    case_pattern = re.compile(r"\[\d+/\d+\]\s+(s\d+)\s+/\s+(\w+)")
    crash_case = "unknown"
    crash_config = "unknown"
    for i in range(tb_start, -1, -1):
        m = case_pattern.search(lines[i])
        if m:
            crash_case = m.group(1)
            crash_config = m.group(2)
            break

    error_type = (
        "invalid_write_region_payload"
        if "invalid_write_region_payload" in lines[crash_line]
        else "write_region_state_diverged"
    )

    print(f"\n{'='*80}")
    print(f"FILE: {log_path.name}")
    print(f"CASE: {crash_case} / {crash_config}")
    print(f"ERROR: {error_type}")
    print(f"{'='*80}")

    # Extract last stop_triggered tails (shows what code was being generated)
    tail_pattern = re.compile(r"stop triggered:.*tail=(.+)")
    stop_tails = []
    for i in range(max(tb_start - 3000, 0), tb_start):
        m = tail_pattern.search(lines[i])
        if m:
            stop_tails.append((i, m.group(1)))

    print(f"\n--- Last 5 boundary stops (code tail at each `;` or `}}`) ---")
    for lineno, tail in stop_tails[-5:]:
        print(f"  L{lineno}: {tail}")

    # Extract last generate_step complete entries
    gen_pattern = re.compile(
        r"generate_step complete: delta_tokens=(\d+) stop_reason=(\S+)"
        r"(?: extracted_chars=(\d+))?"
    )
    gen_entries = []
    for i in range(max(tb_start - 3000, 0), tb_start):
        m = gen_pattern.search(lines[i])
        if m:
            gen_entries.append((i, m.group(1), m.group(2), m.group(3) or "?"))

    print(f"\n--- Last 5 generate_step results ---")
    for lineno, tokens, reason, extracted in gen_entries[-5:]:
        print(f"  L{lineno}: tokens={tokens} stop={reason} extracted={extracted}")

    # Extract last generate log (shows prefix length)
    gen_log_pattern = re.compile(
        r"generate: step=(\d+) delta_tokens=(\d+) stop_reason=(\S+) prefix_len=(\d+)"
    )
    gen_logs = []
    for i in range(max(tb_start - 3000, 0), tb_start):
        m = gen_log_pattern.search(lines[i])
        if m:
            gen_logs.append((i, m.group(1), m.group(2), m.group(3), m.group(4)))

    print(f"\n--- Last 5 generate steps ---")
    for lineno, step, tokens, reason, plen in gen_logs[-5:]:
        print(f"  L{lineno}: step={step} tokens={tokens} stop={reason} prefix_len={plen}")

    # Extract recent actions (rollback, feedback, commit, verify with oracles)
    action_pattern = re.compile(
        r"(rollback|feedback|commit|apply_patch): step=(\d+)(.*)"
    )
    oracle_pattern = re.compile(r"oracle_result: oracle=(\S+) verdict=(\S+)")
    recent_actions = []
    for i in range(max(tb_start - 5000, 0), tb_start):
        m = action_pattern.search(lines[i])
        if m:
            recent_actions.append((i, m.group(1), m.group(2), m.group(3).strip()))
        m = oracle_pattern.search(lines[i])
        if m:
            recent_actions.append((i, "oracle", m.group(1), m.group(2)))

    print(f"\n--- Last 10 non-generate actions ---")
    for lineno, action, step_or_name, detail in recent_actions[-10:]:
        print(f"  L{lineno}: {action} {step_or_name} {detail}")

    # Feedback mechanism info
    fb_pattern = re.compile(r"feedback: step=(\d+) mechanism=(\S+) delta_tokens=(\d+)")
    fb_entries = []
    for i in range(max(tb_start - 5000, 0), tb_start):
        m = fb_pattern.search(lines[i])
        if m:
            fb_entries.append((i, m.group(1), m.group(2), m.group(3)))

    if fb_entries:
        print(f"\n--- Last 3 feedback rounds ---")
        for lineno, step, mechanism, tokens in fb_entries[-3:]:
            print(f"  L{lineno}: step={step} mechanism={mechanism} tokens={tokens}")

    # The actual crash traceback
    traceback_end = min(crash_line + 1, len(lines))
    print(f"\n--- Traceback (from L{tb_start}) ---")
    for i in range(tb_start, traceback_end):
        # Show crash function in the call stack
        if "in _handle_" in lines[i] or "in run_dtv_loop" in lines[i]:
            print(f"  {lines[i].strip()}")
    print(f"  {lines[crash_line].strip()}")

    # Raw context: CONTEXT_LINES_BEFORE lines before traceback
    ctx_start = max(tb_start - CONTEXT_LINES_BEFORE, 0)
    print(f"\n--- Raw log context (L{ctx_start} to L{tb_start}) ---")
    for i in range(ctx_start, tb_start):
        print(lines[i])


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    for path_str in sys.argv[1:]:
        extract_crash(Path(path_str))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from pathlib import Path

from feedback.output_parser import parse_feedback_output


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
CASE_LINE_RE = re.compile(r"^\[(?P<idx>\d+)/(?:\d+)\]\s+(?P<case_id>s\d+)\s+/\s+(?P<mode>dtv|naive)\s+\.\.\.$")
RESULT_LINE_RE = re.compile(r"^->\s+")
LOG_HEADER_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\s+"
    r"(?P<level>[A-Z_]+)\s+"
    r"(?P<logger>[^:]+):\s*(?P<msg>.*)$"
)
IM_START_RE = re.compile(r"<\|im_start\|>(user|assistant)\n")
RUST_FENCE_START_RE = re.compile(r"```(?:rust|rs)?\s*\n", re.IGNORECASE)
ANY_FENCE_START_RE = re.compile(r"```[^\n`]*\n")
REPAIR_FEEDBACK_RE = re.compile(r"/\* repair feedback:\n.*?\*/", re.DOTALL)
POLICY_RE = re.compile(
    r"^policy: step=(?P<step>\d+) action=Action\.(?P<action>[A-Z_]+).*"
    r"feedback_mechanism=(?P<feedback_mechanism>\S+)"
)
ROLLBACK_RE = re.compile(
    r"^rollback: step=(?P<step>\d+) scope=(?P<scope>\S+) prefix_len=(?P<prefix_len>\d+)$"
)
FEEDBACK_RE = re.compile(
    r"^feedback: step=(?P<step>\d+) mechanism=(?P<mechanism>\S+) delta_tokens=(?P<delta_tokens>-?\d+) "
    r"stop_reason=(?P<stop_reason>\S+) patch_len=(?P<patch_len>\d+) parse_error=(?P<parse_error>.*)$"
)
APPLY_PATCH_RE = re.compile(
    r"^apply_patch: step=(?P<step>\d+) patch_len=(?P<patch_len>\d+) prefix_len=(?P<prefix_len>\d+)$"
)
GENERATE_RE = re.compile(
    r"^generate: step=(?P<step>\d+) delta_tokens=(?P<delta_tokens>-?\d+) "
    r"stop_reason=(?P<stop_reason>\S+) prefix_len=(?P<prefix_len>\d+)$"
)


@dataclass
class LogRecord:
    line_no: int
    timestamp: str
    level: str
    logger: str
    message: str
    case_id: str | None
    mode: str | None


@dataclass
class InferenceCall:
    case_id: str | None
    mode: str | None
    step: int
    action: str
    feedback_mechanism: str | None
    policy_line: int
    model_input: str | None = None
    model_input_line: int | None = None
    model_output: str | None = None
    model_output_line: int | None = None


@dataclass
class PrefixSnapshot:
    line_no: int
    step: int
    action: str
    prefix_len_reported: int
    prefix: str | None


@dataclass
class FeedbackRetry:
    step: int
    line: int
    mechanism: str | None
    delta_tokens: int | None
    patch_len_reported: int
    parse_error: str | None


@dataclass
class RollbackEvent:
    index: int
    rollback_step: int
    rollback_line: int
    rollback_scope: str
    rollback_prefix_len: int
    rollback_prefix: str | None = None
    pre_rollback_source_action: str | None = None
    pre_rollback_source_step: int | None = None
    pre_rollback_prefix_len_reported: int | None = None
    pre_rollback_prefix: str | None = None
    dropped_len_reported: int | None = None
    dropped_content: str | None = None
    dropped_len: int | None = None
    feedback_step: int | None = None
    feedback_line: int | None = None
    feedback_mechanism: str | None = None
    feedback_text: str | None = None
    feedback_patch_len_reported: int | None = None
    feedback_parse_error: str | None = None
    feedback_delta_tokens: int | None = None
    feedback_model_input_line: int | None = None
    feedback_model_output_line: int | None = None
    feedback_patch_candidate: str | None = None
    apply_patch_step: int | None = None
    apply_patch_line: int | None = None
    apply_patch_patch_len_reported: int | None = None
    apply_patch_prefix_len: int | None = None
    apply_patch_content: str | None = None
    extracted_prefix_len: int | None = None
    extracted_patch_len: int | None = None
    warnings: list[str] = field(default_factory=list)
    feedback_retries: list[FeedbackRetry] = field(default_factory=list)


@dataclass
class ParsedChat:
    messages: list[tuple[str, str]]

    def last_content(self, role: str) -> str:
        for msg_role, content in reversed(self.messages):
            if msg_role == role:
                return content
        return ""

    def last_non_empty_assistant(self) -> str:
        for msg_role, content in reversed(self.messages):
            if msg_role == "assistant" and content.strip():
                return content
        return ""

    def previous_non_empty_assistant_before_last(self) -> str:
        seen_last_assistant = False
        for msg_role, content in reversed(self.messages):
            if msg_role != "assistant":
                continue
            if not seen_last_assistant:
                seen_last_assistant = True
                continue
            if content.strip():
                return content
        return ""


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def parse_records(log_path: Path) -> list[LogRecord]:
    records: list[LogRecord] = []
    current_case: str | None = None
    current_mode: str | None = None
    active_record: LogRecord | None = None

    with log_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, raw_line in enumerate(handle, 1):
            line = strip_ansi(raw_line.rstrip("\n"))
            stripped = line.strip()

            case_match = CASE_LINE_RE.match(stripped)
            if case_match is not None:
                if active_record is not None:
                    records.append(active_record)
                    active_record = None
                current_case = case_match.group("case_id")
                current_mode = case_match.group("mode")
                continue

            if RESULT_LINE_RE.match(stripped):
                if active_record is not None:
                    records.append(active_record)
                    active_record = None
                continue

            header_match = LOG_HEADER_RE.match(line)
            if header_match is not None:
                if active_record is not None:
                    records.append(active_record)
                active_record = LogRecord(
                    line_no=line_no,
                    timestamp=header_match.group("ts"),
                    level=header_match.group("level"),
                    logger=header_match.group("logger"),
                    message=header_match.group("msg"),
                    case_id=current_case,
                    mode=current_mode,
                )
                continue

            if active_record is not None:
                active_record.message = f"{active_record.message}\n{line}"

    if active_record is not None:
        records.append(active_record)

    return records


def parse_chat_dump(dump_text: str | None) -> ParsedChat:
    if not dump_text:
        return ParsedChat(messages=[])

    text = strip_ansi(dump_text)
    matches = list(IM_START_RE.finditer(text))
    messages: list[tuple[str, str]] = []

    for idx, match in enumerate(matches):
        role = match.group(1)
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        content = text[start:end]
        content = re.sub(r"<\|im_end\|>\s*$", "", content, flags=re.DOTALL)
        messages.append((role, content))

    return ParsedChat(messages=messages)


def extract_rust_code(text: str) -> str:
    if not text:
        return ""

    rust_match = RUST_FENCE_START_RE.search(text)
    if rust_match is not None:
        remainder = text[rust_match.end() :]
        end_index = remainder.find("```")
        if end_index >= 0:
            remainder = remainder[:end_index]
        return remainder

    any_match = ANY_FENCE_START_RE.search(text)
    if any_match is not None:
        remainder = text[any_match.end() :]
        end_index = remainder.find("```")
        if end_index >= 0:
            remainder = remainder[:end_index]
        return remainder

    return text


def split_inline_feedback(assistant_code: str) -> tuple[str, str]:
    matches = list(REPAIR_FEEDBACK_RE.finditer(assistant_code))
    if not matches:
        return assistant_code, ""
    block = matches[-1]
    rollback_prefix = assistant_code[: block.start()]
    if rollback_prefix.endswith("\n\n"):
        rollback_prefix = rollback_prefix[:-2]
    feedback_text = block.group(0)
    return rollback_prefix, feedback_text


def suffix_delta(before: str, after: str) -> str:
    if not after:
        return ""
    if not before:
        return after
    if after.startswith(before):
        return after[len(before) :]
    limit = min(len(before), len(after))
    index = 0
    while index < limit and before[index] == after[index]:
        index += 1
    return after[index:]


def parse_int(value: str | None, default: int | None = None) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def collect_inference_calls(records: list[LogRecord]) -> dict[tuple[str | None, str | None, int], InferenceCall]:
    calls: dict[tuple[str | None, str | None, int], InferenceCall] = {}
    pending_calls: deque[InferenceCall] = deque()
    active_call: InferenceCall | None = None

    for record in records:
        if record.logger == "controller.loop":
            policy_match = POLICY_RE.match(record.message)
            if policy_match is not None:
                action = policy_match.group("action")
                if action in {"GENERATE", "FEEDBACK"}:
                    step = int(policy_match.group("step"))
                    call = InferenceCall(
                        case_id=record.case_id,
                        mode=record.mode,
                        step=step,
                        action=action,
                        feedback_mechanism=policy_match.group("feedback_mechanism"),
                        policy_line=record.line_no,
                    )
                    pending_calls.append(call)
                    calls[(record.case_id, record.mode, step)] = call
                continue

        if record.level == "MODEL_INPUT" and record.logger == "core.qwen_generator_backend":
            if pending_calls:
                active_call = pending_calls.popleft()
                active_call.model_input = record.message
                active_call.model_input_line = record.line_no
            continue

        if record.level == "MODEL_OUTPUT" and record.logger == "core.qwen_generator_backend":
            if active_call is not None:
                active_call.model_output = record.message
                active_call.model_output_line = record.line_no
                active_call = None

    return calls


def collect_dtv_case_ids(records: list[LogRecord], target_cases: set[str] | None) -> list[str]:
    case_ids: list[str] = []
    seen: set[str] = set()

    for record in records:
        if record.mode != "dtv" or record.case_id is None:
            continue
        if target_cases is not None and record.case_id not in target_cases:
            continue
        if record.case_id in seen:
            continue
        seen.add(record.case_id)
        case_ids.append(record.case_id)

    if target_cases is not None:
        for case_id in sorted(target_cases):
            if case_id not in seen:
                case_ids.append(case_id)

    return case_ids


def enrich_with_feedback_and_patch(
    event: RollbackEvent,
    call: InferenceCall | None,
) -> None:
    if call is None:
        event.warnings.append("missing inference call for feedback step")
        return

    input_chat = parse_chat_dump(call.model_input)
    output_chat = parse_chat_dump(call.model_output)

    event.feedback_model_input_line = call.model_input_line
    event.feedback_model_output_line = call.model_output_line

    mechanism = event.feedback_mechanism or call.feedback_mechanism or ""

    if mechanism.endswith(".A"):
        input_assistant = input_chat.last_non_empty_assistant()
        output_assistant = output_chat.last_non_empty_assistant()
        input_code = extract_rust_code(input_assistant)
        output_code = extract_rust_code(output_assistant)

        rollback_prefix, feedback_text = split_inline_feedback(input_code)
        patch_text = suffix_delta(input_code, output_code)

        event.rollback_prefix = rollback_prefix
        event.feedback_text = feedback_text
        event.feedback_patch_candidate = patch_text
        event.apply_patch_content = patch_text
    elif mechanism.endswith(".B"):
        last_assistant_input = input_chat.last_content("assistant")
        output_assistant = output_chat.last_content("assistant")
        rollback_assistant = input_chat.previous_non_empty_assistant_before_last()
        if not rollback_assistant:
            rollback_assistant = input_chat.last_non_empty_assistant()

        delta = suffix_delta(last_assistant_input, output_assistant)
        parse_result = parse_feedback_output(delta)
        applied_patch = parse_result.patch if parse_result.patch is not None else None

        event.rollback_prefix = extract_rust_code(rollback_assistant)
        event.feedback_text = input_chat.last_content("user")
        event.feedback_patch_candidate = delta
        event.apply_patch_content = applied_patch
        if parse_result.error is not None:
            event.warnings.append(f"feedback output parser: {parse_result.error}")
    else:
        event.warnings.append(f"unknown feedback mechanism: {mechanism}")
        input_assistant = input_chat.last_non_empty_assistant()
        output_assistant = output_chat.last_non_empty_assistant()
        input_code = extract_rust_code(input_assistant)
        output_code = extract_rust_code(output_assistant)
        event.rollback_prefix = input_code
        event.feedback_text = ""
        event.feedback_patch_candidate = suffix_delta(input_code, output_code)
        event.apply_patch_content = event.feedback_patch_candidate

    if event.rollback_prefix is not None and len(event.rollback_prefix) > event.rollback_prefix_len:
        event.rollback_prefix = event.rollback_prefix[: event.rollback_prefix_len]

    if (
        event.apply_patch_content is not None
        and event.feedback_patch_len_reported is not None
        and len(event.apply_patch_content) > event.feedback_patch_len_reported
    ):
        event.apply_patch_content = event.apply_patch_content[: event.feedback_patch_len_reported]

    event.extracted_prefix_len = len(event.rollback_prefix) if event.rollback_prefix is not None else None
    event.extracted_patch_len = len(event.apply_patch_content) if event.apply_patch_content is not None else None

    if event.rollback_prefix is not None and event.rollback_prefix_len != len(event.rollback_prefix):
        event.warnings.append(
            f"rollback prefix length mismatch: reported={event.rollback_prefix_len}, extracted={len(event.rollback_prefix)}"
        )

    if (
        event.apply_patch_content is not None
        and event.feedback_patch_len_reported is not None
        and len(event.apply_patch_content) != event.feedback_patch_len_reported
    ):
        event.warnings.append(
            "feedback patch length mismatch: "
            f"reported={event.feedback_patch_len_reported}, extracted={len(event.apply_patch_content)}"
        )


def collect_rollback_events(
    records: list[LogRecord],
    calls: dict[tuple[str | None, str | None, int], InferenceCall],
    target_cases: set[str] | None,
    case_ids: list[str],
) -> dict[str, list[RollbackEvent]]:
    events_by_case: dict[str, list[RollbackEvent]] = {case_id: [] for case_id in case_ids}
    open_events: dict[str, list[RollbackEvent]] = defaultdict(list)

    for record in records:
        if record.mode != "dtv" or record.case_id is None:
            continue
        if target_cases is not None and record.case_id not in target_cases:
            continue
        if record.case_id not in events_by_case:
            continue
        if record.logger != "controller.loop":
            continue

        rollback_match = ROLLBACK_RE.match(record.message)
        if rollback_match is not None:
            case_events = events_by_case[record.case_id]
            event = RollbackEvent(
                index=len(case_events) + 1,
                rollback_step=int(rollback_match.group("step")),
                rollback_line=record.line_no,
                rollback_scope=rollback_match.group("scope"),
                rollback_prefix_len=int(rollback_match.group("prefix_len")),
            )
            case_events.append(event)
            open_events[record.case_id].append(event)
            continue

        feedback_match = FEEDBACK_RE.match(record.message)
        if feedback_match is not None:
            candidates = open_events[record.case_id]
            step = int(feedback_match.group("step"))
            mechanism = feedback_match.group("mechanism")
            delta_tokens = parse_int(feedback_match.group("delta_tokens"))
            patch_len = int(feedback_match.group("patch_len"))
            parse_error_raw = feedback_match.group("parse_error").strip()
            parse_error = None if parse_error_raw == "None" else parse_error_raw

            # Find the most recent rollback event for this case.
            event = candidates[-1] if candidates else None
            if event is None:
                continue

            if event.feedback_step is None:
                # First feedback after this rollback.
                event.feedback_step = step
                event.feedback_line = record.line_no
                event.feedback_mechanism = mechanism
                event.feedback_delta_tokens = delta_tokens
                event.feedback_patch_len_reported = patch_len
                event.feedback_parse_error = parse_error

                call_key = (record.case_id, record.mode, step)
                enrich_with_feedback_and_patch(event, calls.get(call_key))
            else:
                # Subsequent feedback retry on the same rollback.
                event.feedback_retries.append(FeedbackRetry(
                    step=step,
                    line=record.line_no,
                    mechanism=mechanism,
                    delta_tokens=delta_tokens,
                    patch_len_reported=patch_len,
                    parse_error=parse_error,
                ))
            continue

        apply_patch_match = APPLY_PATCH_RE.match(record.message)
        if apply_patch_match is not None:
            candidates = open_events[record.case_id]
            event = next((item for item in reversed(candidates) if item.apply_patch_step is None), None)
            if event is None:
                continue

            event.apply_patch_step = int(apply_patch_match.group("step"))
            event.apply_patch_line = record.line_no
            event.apply_patch_patch_len_reported = int(apply_patch_match.group("patch_len"))
            event.apply_patch_prefix_len = int(apply_patch_match.group("prefix_len"))

    return events_by_case


def _extract_generate_prefix(call: InferenceCall | None, prefix_len_reported: int) -> str | None:
    if call is None or call.model_output is None:
        return None

    output_chat = parse_chat_dump(call.model_output)
    assistant = output_chat.last_non_empty_assistant()
    if not assistant:
        return None

    prefix = extract_rust_code(assistant)
    if len(prefix) > prefix_len_reported:
        prefix = prefix[:prefix_len_reported]
    return prefix


def _build_prefix_snapshots(
    records: list[LogRecord],
    calls: dict[tuple[str | None, str | None, int], InferenceCall],
    events_by_case: dict[str, list[RollbackEvent]],
) -> dict[str, list[PrefixSnapshot]]:
    snapshots_by_case: dict[str, list[PrefixSnapshot]] = defaultdict(list)
    apply_event_by_step: dict[str, dict[int, RollbackEvent]] = defaultdict(dict)

    for case_id, events in events_by_case.items():
        for event in events:
            if event.apply_patch_step is not None:
                apply_event_by_step[case_id][event.apply_patch_step] = event

    for record in records:
        if record.mode != "dtv" or record.case_id is None:
            continue
        case_id = record.case_id
        if case_id not in events_by_case:
            continue
        if record.logger != "controller.loop":
            continue

        generate_match = GENERATE_RE.match(record.message)
        if generate_match is not None:
            step = int(generate_match.group("step"))
            prefix_len_reported = int(generate_match.group("prefix_len"))
            call = calls.get((case_id, "dtv", step))
            prefix = _extract_generate_prefix(call, prefix_len_reported)
            snapshots_by_case[case_id].append(
                PrefixSnapshot(
                    line_no=record.line_no,
                    step=step,
                    action="GENERATE",
                    prefix_len_reported=prefix_len_reported,
                    prefix=prefix,
                )
            )
            continue

        apply_patch_match = APPLY_PATCH_RE.match(record.message)
        if apply_patch_match is not None:
            step = int(apply_patch_match.group("step"))
            prefix_len_reported = int(apply_patch_match.group("prefix_len"))
            prefix: str | None = None

            apply_event = apply_event_by_step.get(case_id, {}).get(step)
            if (
                apply_event is not None
                and apply_event.rollback_prefix is not None
                and apply_event.apply_patch_content is not None
            ):
                prefix = f"{apply_event.rollback_prefix}{apply_event.apply_patch_content}"
                if len(prefix) > prefix_len_reported:
                    prefix = prefix[:prefix_len_reported]

            snapshots_by_case[case_id].append(
                PrefixSnapshot(
                    line_no=record.line_no,
                    step=step,
                    action="APPLY_PATCH",
                    prefix_len_reported=prefix_len_reported,
                    prefix=prefix,
                )
            )

    return dict(snapshots_by_case)


def infer_pre_rollback_context(
    records: list[LogRecord],
    calls: dict[tuple[str | None, str | None, int], InferenceCall],
    events_by_case: dict[str, list[RollbackEvent]],
) -> None:
    snapshots_by_case = _build_prefix_snapshots(records, calls, events_by_case)

    for case_id, events in events_by_case.items():
        snapshots = snapshots_by_case.get(case_id, [])

        for event in events:
            snapshot = next(
                (item for item in reversed(snapshots) if item.line_no < event.rollback_line),
                None,
            )

            if snapshot is None:
                event.warnings.append("missing pre-rollback prefix snapshot")
                continue

            event.pre_rollback_source_action = snapshot.action
            event.pre_rollback_source_step = snapshot.step
            event.pre_rollback_prefix_len_reported = snapshot.prefix_len_reported
            event.dropped_len_reported = snapshot.prefix_len_reported - event.rollback_prefix_len

            if snapshot.prefix is None:
                event.warnings.append(
                    f"missing {snapshot.action.lower()} prefix body for step {snapshot.step}"
                )
                continue

            pre_prefix = snapshot.prefix
            if len(pre_prefix) > snapshot.prefix_len_reported:
                pre_prefix = pre_prefix[: snapshot.prefix_len_reported]
            event.pre_rollback_prefix = pre_prefix

            if event.rollback_prefix is None:
                if len(pre_prefix) >= event.rollback_prefix_len:
                    event.rollback_prefix = pre_prefix[: event.rollback_prefix_len]
                    event.extracted_prefix_len = len(event.rollback_prefix)
                    event.warnings.append(
                        "rollback prefix inferred from pre-rollback snapshot; no feedback/call payload available"
                    )
                else:
                    event.warnings.append(
                        "missing rollback prefix body and pre-rollback snapshot shorter than rollback prefix"
                    )
                    continue

            if pre_prefix.startswith(event.rollback_prefix):
                dropped_content = pre_prefix[len(event.rollback_prefix) :]
            else:
                limit = min(len(pre_prefix), len(event.rollback_prefix))
                divergence = 0
                while (
                    divergence < limit
                    and pre_prefix[divergence] == event.rollback_prefix[divergence]
                ):
                    divergence += 1
                dropped_content = pre_prefix[divergence:]
                event.warnings.append(
                    "pre/rollback prefix mismatch; dropped segment extracted from first divergence"
                )

            event.dropped_content = dropped_content
            event.dropped_len = len(dropped_content)

            if (
                event.dropped_len_reported is not None
                and event.dropped_len != event.dropped_len_reported
            ):
                event.warnings.append(
                    f"dropped length mismatch: reported={event.dropped_len_reported}, extracted={event.dropped_len}"
                )


def render_event_markdown(event: RollbackEvent) -> str:
    feedback_text = event.feedback_text or ""
    rollback_prefix = event.rollback_prefix or ""
    pre_rollback_prefix = event.pre_rollback_prefix or ""
    dropped_content = event.dropped_content or ""
    apply_patch_content = event.apply_patch_content or ""
    patch_candidate = event.feedback_patch_candidate or ""
    warnings = "\n".join(f"- {warning}" for warning in event.warnings) or "- none"
    parse_error = event.feedback_parse_error if event.feedback_parse_error is not None else "None"
    apply_patch_section = (
        "```rust\n" + apply_patch_content + "\n```"
        if apply_patch_content
        else "(no apply_patch content; patch was not applied)"
    )
    patch_candidate_section = (
        "```rust\n" + patch_candidate + "\n```"
        if patch_candidate
        else "(none)"
    )
    if event.feedback_retries:
        retry_total_tokens = sum(r.delta_tokens or 0 for r in event.feedback_retries)
        retry_lines = [
            "### Feedback Retries",
            "",
            f"- total retries: {len(event.feedback_retries)}",
            f"- total retry tokens: {retry_total_tokens}",
            "",
            "| # | step | mechanism | delta_tokens | patch_len | parse_error |",
            "|---|------|-----------|--------------|-----------|-------------|",
        ]
        for idx, retry in enumerate(event.feedback_retries, 1):
            pe = retry.parse_error if retry.parse_error is not None else "None"
            retry_lines.append(
                f"| {idx} | {retry.step} | {retry.mechanism} "
                f"| {retry.delta_tokens} | {retry.patch_len_reported} | {pe} |"
            )
        retries_section = "\n".join(retry_lines)
    else:
        retries_section = ""

    return f"""## Rollback {event.index}

- rollback step: {event.rollback_step} (log line {event.rollback_line})
- rollback scope: {event.rollback_scope}
- rollback prefix len: {event.rollback_prefix_len}
- pre-rollback source: {event.pre_rollback_source_action} step={event.pre_rollback_source_step}
- pre-rollback prefix len (reported): {event.pre_rollback_prefix_len_reported}
- dropped len (reported): {event.dropped_len_reported}
- feedback step: {event.feedback_step}
- feedback mechanism: {event.feedback_mechanism}
- feedback delta_tokens: {event.feedback_delta_tokens}
- feedback patch len (reported): {event.feedback_patch_len_reported}
- feedback parse_error: {parse_error}
- feedback retries: {len(event.feedback_retries)}
- apply_patch step: {event.apply_patch_step}
- apply_patch prefix len (reported): {event.apply_patch_prefix_len}
- extracted pre-rollback prefix len: {len(pre_rollback_prefix) if pre_rollback_prefix else None}
- extracted rollback prefix len: {event.extracted_prefix_len}
- extracted dropped len: {event.dropped_len}
- extracted apply_patch len: {event.extracted_patch_len}

### Pre-Rollback Prefix

```rust
{pre_rollback_prefix}
```

### Dropped Segment

```rust
{dropped_content}
```

### Rollback Prefix

```rust
{rollback_prefix}
```

### Feedback

```text
{feedback_text}
```

### Apply Patch Content

{apply_patch_section}

### Feedback Patch Candidate

{patch_candidate_section}

### Notes

{warnings}

{retries_section}"""


def write_outputs(
    out_dir: Path,
    log_path: Path,
    events_by_case: dict[str, list[RollbackEvent]],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    summary: list[dict[str, object]] = []
    for case_id in sorted(events_by_case):
        case_events = events_by_case[case_id]
        case_dir = out_dir / case_id
        case_dir.mkdir(parents=True, exist_ok=True)

        payload = {
            "case_id": case_id,
            "log_file": str(log_path),
            "rollback_count": len(case_events),
            "events": [asdict(event) for event in case_events],
        }
        (case_dir / "rollback_events.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )

        md_parts = [
            f"# {case_id} DTV Rollback Analysis",
            "",
            f"- source log: `{log_path}`",
            f"- rollback events: {len(case_events)}",
            f"- feedback retries: {sum(len(e.feedback_retries) for e in case_events)}",
            "",
        ]
        for event in case_events:
            md_parts.append(render_event_markdown(event))
            md_parts.append("")

        (case_dir / "rollback_events.md").write_text("\n".join(md_parts).rstrip() + "\n", encoding="utf-8")

        parse_error_count = sum(1 for event in case_events if event.feedback_parse_error is not None)
        retry_count = sum(len(event.feedback_retries) for event in case_events)
        retry_tokens = sum(
            sum(r.delta_tokens or 0 for r in event.feedback_retries)
            for event in case_events
        )
        warning_count = sum(len(event.warnings) for event in case_events)
        summary.append(
            {
                "case_id": case_id,
                "rollback_count": len(case_events),
                "feedback_parse_error_count": parse_error_count,
                "feedback_retry_count": retry_count,
                "feedback_retry_tokens": retry_tokens,
                "warning_count": warning_count,
                "output_json": str(case_dir / "rollback_events.json"),
                "output_markdown": str(case_dir / "rollback_events.md"),
            }
        )

    summary_payload = {
        "log_file": str(log_path),
        "case_count": len(summary),
        "cases": summary,
    }
    (out_dir / "index.json").write_text(
        json.dumps(summary_payload, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )


def default_out_dir(log_path: Path) -> Path:
    return log_path.parent / f"{log_path.stem}_dtv_rollback_analysis"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract per-sample DTV rollback/feedback/apply_patch timelines from experiment logs.")
    parser.add_argument("--log", required=True, type=Path, help="Path to experiment log file.")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory for per-sample analysis files. Defaults to <log_stem>_dtv_rollback_analysis beside the log.",
    )
    parser.add_argument(
        "--case-id",
        action="append",
        default=None,
        help="Optional case ID filter. Repeat to include multiple cases.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    log_path = args.log
    if not log_path.exists():
        raise FileNotFoundError(f"log file not found: {log_path}")

    out_dir = args.out_dir if args.out_dir is not None else default_out_dir(log_path)
    target_cases = set(args.case_id) if args.case_id else None

    records = parse_records(log_path)
    calls = collect_inference_calls(records)
    case_ids = collect_dtv_case_ids(records, target_cases)
    events_by_case = collect_rollback_events(records, calls, target_cases, case_ids)
    infer_pre_rollback_context(records, calls, events_by_case)
    write_outputs(out_dir, log_path, events_by_case)

    total_events = sum(len(events) for events in events_by_case.values())
    total_retries = sum(
        len(event.feedback_retries)
        for events in events_by_case.values()
        for event in events
    )
    cases_with_rollbacks = sum(1 for events in events_by_case.values() if events)
    print(f"parsed records: {len(records)}")
    print(f"dtv cases discovered: {len(events_by_case)}")
    print(f"cases with rollback events: {cases_with_rollbacks}")
    print(f"rollback events extracted: {total_events}")
    print(f"feedback retries tracked: {total_retries}")
    print(f"output directory: {out_dir}")


if __name__ == "__main__":
    main()

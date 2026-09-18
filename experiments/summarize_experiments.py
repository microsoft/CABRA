"""Summarize Copilot usage, outcomes, and tool-call labeling by experiment."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from tqdm import tqdm


VALID_TOOL_LABELS = {
    "read",
    "search",
    "understand",
    "edit",
    "test",
    "summary",
    "plan",
    "other",
}


def _experiment_names(experiments_root: Path) -> list[str]:
    names = []
    for config_path in experiments_root.glob("*/config.yaml"):
        for line in config_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("experiment_name:"):
                names.append(line.split(":", 1)[1].strip())
                break
    return sorted(names, key=len, reverse=True)


def _experiment_for_run(run_name: str, experiment_names: list[str]) -> str:
    return next(
        (name for name in experiment_names if run_name == name or run_name.startswith(f"{name}_")),
        "unknown",
    )


def _response_model(parts: tuple[str, ...], copilot_index: int) -> str:
    model_parts = list(parts[copilot_index + 1:])
    model_parts[-1] = Path(model_parts[-1]).stem
    return "/".join(model_parts)


def _response_outcome(record: dict[str, Any]) -> str | None:
    if record.get("output"):
        return "successful"
    metadata = record.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    status = record.get("status") or metadata.get("status")
    if record.get("error") or status in {"error", "failed", "invalid_json", "invalid_record"}:
        return "errors"
    return None


def _response_mappings(
    responses_root: Path,
    experiment_names: list[str],
) -> tuple[
    dict[str, str],
    dict[tuple[str, str], set[str]],
    dict[str, dict[str, int]],
]:
    by_session: dict[str, str] = {}
    by_task: dict[tuple[str, str], set[str]] = defaultdict(set)
    outcomes: dict[str, dict[str, int]] = defaultdict(
        lambda: {"successful": 0, "errors": 0}
    )
    if not responses_root.is_dir():
        print(f"[warn] response directory not found: {responses_root}")
        return by_session, by_task, outcomes

    response_paths = sorted(responses_root.rglob("copilot/*.jsonl"))
    for path in tqdm(response_paths, desc="Indexing responses", unit="file"):
        parts = path.relative_to(responses_root).parts
        copilot_index = parts.index("copilot")
        experiment = _experiment_for_run(parts[0], experiment_names)
        model = _response_model(parts, copilot_index)
        task_type = parts[copilot_index - 1] if copilot_index >= 3 else None
        latest_records: dict[tuple[str, str], dict[str, Any]] = {}
        with path.open(encoding="utf-8") as response_file:
            for line in response_file:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict):
                    continue
                metadata = record.get("metadata")
                metadata = metadata if isinstance(metadata, dict) else {}
                session_id = record.get("session_id") or metadata.get("session_id")
                if session_id:
                    by_session[str(session_id)] = experiment
                if task_type and record.get("dag_id"):
                    task_id = f"{record['dag_id']}/{task_type}"
                else:
                    task_id = record.get("name")
                if task_id:
                    by_task[(model, str(task_id))].add(experiment)
                name = record.get("name")
                dag_id = record.get("dag_id")
                if name and dag_id:
                    latest_records[(str(name), str(dag_id))] = record
        for record in latest_records.values():
            outcome = _response_outcome(record)
            if outcome is not None:
                outcomes[experiment][outcome] += 1
    return by_session, by_task, outcomes


def _trace_tool_call_count(path: Path) -> int:
    count = 0
    with path.open(encoding="utf-8") as trace_file:
        for line in trace_file:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict) or event.get("type") != "assistant.message":
                continue
            data = event.get("data")
            data = data if isinstance(data, dict) else {}
            count += sum(
                isinstance(request, dict)
                for request in data.get("toolRequests") or []
            )
    return count


def _classified_trace_counts(
    labels_path: Path,
    traces_root: Path,
    by_session: dict[str, str],
) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {"classified": 0, "incomplete": 0}
    )
    successful_indexes: dict[str, set[int]] = defaultdict(set)
    valid_label_count = 0

    if not labels_path.is_file():
        print(f"[warn] tool-call labels not found: {labels_path}")
        return counts
    if not traces_root.is_dir():
        print(f"[warn] Copilot trace directory not found: {traces_root}")
        return counts

    with labels_path.open(encoding="utf-8") as labels_file:
        for line in tqdm(
            labels_file,
            desc="Indexing tool-call labels",
            unit="label",
        ):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            session_id = str(record.get("session_id") or "")
            tool_call_index = record.get("tool_call_index")
            if (
                session_id
                and isinstance(tool_call_index, int)
                and record.get("label") in VALID_TOOL_LABELS
                and not record.get("error")
            ):
                successful_indexes[session_id].add(tool_call_index)
                valid_label_count += 1

    response_sessions = set(by_session)
    labeled_sessions = set(successful_indexes)
    trace_sessions = {
        path.parent.name
        for path in traces_root.glob("*/events.jsonl")
    }
    matched_sessions = response_sessions & labeled_sessions
    print(
        f"[info] indexed {valid_label_count} valid labels across "
        f"{len(labeled_sessions)} sessions; {len(matched_sessions)} sessions "
        f"match the current responses"
    )
    print(
        f"[info] session overlap: responses={len(response_sessions)}, "
        f"labels={len(labeled_sessions)}, traces={len(trace_sessions)}, "
        f"responses/labels={len(response_sessions & labeled_sessions)}, "
        f"responses/traces={len(response_sessions & trace_sessions)}, "
        f"labels/traces={len(labeled_sessions & trace_sessions)}"
    )
    if labeled_sessions and not matched_sessions:
        print(
            "[warn] no labeled session IDs match the current responses; "
            "check --tool-call-labels, --responses-root, and --traces-root"
        )
        print(
            f"[debug] response session examples: "
            f"{', '.join(sorted(response_sessions)[:3]) or '<none>'}"
        )
        print(
            f"[debug] label session examples: "
            f"{', '.join(sorted(labeled_sessions)[:3]) or '<none>'}"
        )
        print(
            f"[debug] trace session examples: "
            f"{', '.join(sorted(trace_sessions)[:3]) or '<none>'}"
        )

    for session_id, experiment in tqdm(
        by_session.items(),
        total=len(by_session),
        desc="Checking classified traces",
        unit="trace",
    ):
        trace_path = traces_root / session_id / "events.jsonl"
        if not trace_path.is_file():
            continue
        tool_call_count = _trace_tool_call_count(trace_path)
        if tool_call_count == 0:
            continue
        if len(successful_indexes[session_id]) == tool_call_count:
            counts[experiment]["classified"] += 1
        else:
            counts[experiment]["incomplete"] += 1
    return counts


def _number(record: dict[str, Any], field: str) -> int | float:
    value = record.get(field)
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cost-log", type=Path, default=Path("copilot_cost_log.jsonl")
    )
    parser.add_argument(
        "--responses-root", type=Path, default=Path("local_data/responses")
    )
    parser.add_argument(
        "--traces-root", type=Path, default=Path("local_data/copilot_traces")
    )
    parser.add_argument(
        "--tool-call-labels",
        type=Path,
        default=Path("local_data/tool-call-labels.jsonl"),
    )
    parser.add_argument(
        "--show-unknown",
        action="store_true",
        help="Print cost-log records that could not be mapped to an experiment.",
    )
    args = parser.parse_args()

    if not args.cost_log.is_file():
        parser.error(f"cost log not found: {args.cost_log}")

    experiment_names = _experiment_names(Path("experiments"))
    by_session, by_task, response_outcomes = _response_mappings(
        args.responses_root, experiment_names
    )
    classified_traces = _classified_trace_counts(
        args.tool_call_labels, args.traces_root, by_session
    )
    cost_lines = args.cost_log.read_text(encoding="utf-8").splitlines()
    summaries: dict[str, dict[str, int | float]] = defaultdict(
        lambda: {
            "attempts": 0,
            "successful": 0,
            "total_nano_aiu": 0,
            "total_premium_requests": 0,
            "missing_usage": 0,
        }
    )
    unknown_records: list[dict[str, Any]] = []

    for line_number, line in enumerate(
        tqdm(cost_lines, desc="Reading cost log", unit="attempt"), start=1
    ):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        session_id = str(record.get("session_id") or "")
        model = str(record.get("model") or "")
        task_id = str(record.get("task_id") or "")
        experiment = by_session.get(session_id)
        if experiment is None:
            candidates = by_task.get((model, task_id), set())
            experiment = next(iter(candidates)) if len(candidates) == 1 else "unknown"
        else:
            candidates = set()

        if experiment == "unknown" and args.show_unknown:
            unknown_records.append({
                "cost_log_line": line_number,
                "candidate_experiments": sorted(candidates),
                **record,
            })

        summary = summaries[experiment]
        summary["attempts"] += 1
        summary["successful"] += int(record.get("success") is True)
        summary["total_nano_aiu"] += _number(record, "total_nano_aiu")
        summary["total_premium_requests"] += _number(record, "total_premium_requests")
        summary["missing_usage"] += int(record.get("total_nano_aiu") is None)

    print("\nAI CREDIT USAGE BY EXPERIMENT")
    print(
        f"{'experiment':<24} {'attempts':>9} {'success':>9} "
        f"{'AIU':>14} {'premium':>12} {'missing':>9}"
    )
    print("-" * 82)
    for experiment in sorted(summaries):
        summary = summaries[experiment]
        aiu = summary["total_nano_aiu"] / 1_000_000_000
        print(
            f"{experiment:<24} {summary['attempts']:>9} {summary['successful']:>9} "
            f"{aiu:>14.6f} {summary['total_premium_requests']:>12g} "
            f"{summary['missing_usage']:>9}"
        )

    attempts = sum(summary["attempts"] for summary in summaries.values())
    successful = sum(summary["successful"] for summary in summaries.values())
    nano_aiu = sum(summary["total_nano_aiu"] for summary in summaries.values())
    premium = sum(summary["total_premium_requests"] for summary in summaries.values())
    missing = sum(summary["missing_usage"] for summary in summaries.values())
    print("-" * 82)
    print(
        f"{'TOTAL':<24} {attempts:>9} {successful:>9} "
        f"{nano_aiu / 1_000_000_000:>14.6f} {premium:>12g} {missing:>9}"
    )

    if args.show_unknown:
        print(f"\nUNKNOWN RECORDS ({len(unknown_records)})")
        for record in unknown_records:
            print(json.dumps(record, indent=2, sort_keys=True))

    print("\nLOGICAL OUTCOMES FROM RESPONSES")
    print(f"{'experiment':<24} {'successful':>12} {'errors':>9} {'total':>9}")
    print("-" * 57)
    for experiment in sorted(response_outcomes):
        successful = response_outcomes[experiment]["successful"]
        errors = response_outcomes[experiment]["errors"]
        print(f"{experiment:<24} {successful:>12} {errors:>9} {successful + errors:>9}")

    print("\nTOOL-CALL TRACE CLASSIFICATION")
    print(f"{'experiment':<24} {'classified':>12} {'incomplete':>12} {'total':>9}")
    print("-" * 60)
    for experiment in sorted(classified_traces):
        classified = classified_traces[experiment]["classified"]
        incomplete = classified_traces[experiment]["incomplete"]
        print(f"{experiment:<24} {classified:>12} {incomplete:>12} {classified + incomplete:>9}")


if __name__ == "__main__":
    main()
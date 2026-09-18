"""Build the minimal tool-call token summary used by the analysis notebook."""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
from typing import Any, TextIO

from tqdm import tqdm


EXPERIMENT_KEYS = (
    "add_instructions",
    "function_search",
    "function_traversal",
    "merge_codebases",
    "runtime_resolution",
)
LEGACY_RUN_PREFIXES = {
    "add_instructions": "add_instructions_fixed_",
    "function_search": "distractor_code_",
    "function_traversal": "main_sweep_fair_",
    "merge_codebases": "testing_",
    "runtime_resolution": "testing_runtime_",
}
RUN_KEYS = ("run_name", "task_set_name", "task_type", "model", "dag_id")


def open_jsonl(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open(encoding="utf-8")


def canonical_run_name(run_name: str, experiment_key: str) -> str:
    legacy_prefix = LEGACY_RUN_PREFIXES[experiment_key]
    if run_name.startswith(legacy_prefix):
        return f"{experiment_key}_{run_name.removeprefix(legacy_prefix)}"
    return run_name


def experiment_key_from_path(path: Path) -> str | None:
    return next(
        (key for key in EXPERIMENT_KEYS if path.name.startswith(f"{key}_")),
        None,
    )


def trace_tool_call_token_map(trace_directory: Path) -> dict[int, float | None]:
    events_path = trace_directory / "events.jsonl"
    if not events_path.exists():
        events_path = Path(f"{events_path}.gz")
    if not events_path.exists():
        return {}

    token_map: dict[int, float | None] = {}
    tool_call_index = 0
    with open_jsonl(events_path) as trace_file:
        for line in trace_file:
            if not line.strip():
                continue
            event = json.loads(line)
            if event.get("type") != "assistant.message":
                continue
            data = event.get("data") or {}
            tool_requests = [
                request
                for request in data.get("toolRequests") or []
                if isinstance(request, dict)
            ]
            output_tokens = data.get("outputTokens")
            tokens_per_tool_call = (
                float(output_tokens) / len(tool_requests)
                if tool_requests and isinstance(output_tokens, (int, float))
                else None
            )
            for _tool_request in tool_requests:
                token_map[tool_call_index] = tokens_per_tool_call
                tool_call_index += 1
    return token_map


def classification_paths(tool_call_root: Path, output_path: Path) -> list[Path]:
    paths = list(tool_call_root.glob("*.jsonl"))
    paths.extend(tool_call_root.glob("*.jsonl.gz"))
    return sorted(path for path in paths if path.resolve() != output_path.resolve())


def build_summary(
    tool_call_root: Path,
    traces_root: Path,
    output_path: Path,
) -> int:
    if not tool_call_root.is_dir():
        raise FileNotFoundError(f"tool-call results directory not found: {tool_call_root}")
    if not traces_root.is_dir():
        raise FileNotFoundError(f"trace directory not found: {traces_root}")

    rows: list[dict[str, Any]] = []
    trace_token_maps: dict[Path, dict[int, float | None]] = {}
    run_trace_paths: dict[tuple[str, ...], Path | None] = {}
    paths = classification_paths(tool_call_root, output_path)

    for path in tqdm(paths, desc="Summarizing tool calls", unit="file"):
        experiment_key = experiment_key_from_path(path)
        if experiment_key is None:
            continue

        with open_jsonl(path) as classification_file:
            for line in classification_file:
                if not line.strip():
                    continue
                record = json.loads(line)
                raw_run_name = record.get("run_name") or record.get("experiment") or ""
                run_name = canonical_run_name(raw_run_name, experiment_key)
                task_type = record.get("task_type") or ""
                task_set_name = record.get("task_set_name") or ""
                if experiment_key == "merge_codebases":
                    task_type = task_type or "merge_codebases"
                    task_set_name = task_set_name or run_name

                run_metadata = {
                    "run_name": run_name,
                    "task_set_name": task_set_name,
                    "task_type": task_type,
                    "model": record.get("model") or "",
                    "dag_id": str(record.get("dag_id") or ""),
                }
                if not all(run_metadata.values()):
                    raise ValueError(
                        f"incomplete tool-call run identifiers in {path}: {run_metadata}"
                    )

                run_key = tuple(run_metadata[key] for key in RUN_KEYS)
                trace_name = record.get("session_id") or ""
                trace_directory = traces_root / trace_name if trace_name else None
                previous_trace = run_trace_paths.setdefault(run_key, trace_directory)
                if previous_trace != trace_directory:
                    raise ValueError(
                        f"multiple traces for the same run identifiers: {run_key}"
                    )

                if trace_directory is not None and trace_directory not in trace_token_maps:
                    trace_token_maps[trace_directory] = trace_tool_call_token_map(trace_directory)

                tool_call_index = record.get("tool_call_index")
                if not isinstance(tool_call_index, int):
                    raise ValueError(
                        f"invalid tool_call_index in {path}: {tool_call_index!r}"
                    )
                rows.append(
                    {
                        **run_metadata,
                        "tool_call_index": tool_call_index,
                        "label": record.get("label"),
                        "tool_call_tokens": trace_token_maps.get(trace_directory, {}).get(
                            tool_call_index
                        ),
                    }
                )

    if not rows:
        raise ValueError(f"no tool-call rows found under {tool_call_root}")

    rows.sort(key=lambda row: tuple(row[key] for key in (*RUN_KEYS, "tool_call_index")))
    previous_key: tuple[Any, ...] | None = None
    for row in rows:
        row_key = tuple(row[key] for key in (*RUN_KEYS, "tool_call_index"))
        if row_key == previous_key:
            raise ValueError(
                "duplicate tool-call indices for the same run identifiers: "
                f"{row_key}"
            )
        previous_key = row_key

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(f"{output_path.name}.tmp")
    try:
        with temporary_path.open("w", encoding="utf-8") as output_file:
            for row in tqdm(rows, desc="Writing summary", unit="call"):
                output_file.write(json.dumps(row, ensure_ascii=False) + "\n")
        temporary_path.replace(output_path)
    finally:
        temporary_path.unlink(missing_ok=True)

    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tool-call-root",
        type=Path,
        default=Path("local_data/tool_call_results"),
        help="Directory containing classified tool-call JSONL files.",
    )
    parser.add_argument(
        "--traces-root",
        type=Path,
        required=True,
        help="Directory containing one events.jsonl or events.jsonl.gz per session.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSONL path (default: <tool-call-root>/tool_call_token_counts.jsonl).",
    )
    args = parser.parse_args()

    output_path = args.output or args.tool_call_root / "tool_call_token_counts.jsonl"
    try:
        row_count = build_summary(args.tool_call_root, args.traces_root, output_path)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(f"Wrote {row_count:,} tool-call summaries to {output_path}")


if __name__ == "__main__":
    main()

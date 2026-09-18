"""Dataset-specific loading for tool-call classification."""

from __future__ import annotations

import json
from collections.abc import Hashable
from pathlib import Path
from typing import Any

from .labeling_core import ClassificationItem, iter_jsonl


def _parse_tool_arguments(arguments: Any) -> dict[str, Any]:
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return {"raw": arguments}
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    return {}


def _columnar_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a column-oriented JSON object")

    def as_list(column: Any) -> list[Any]:
        if isinstance(column, dict):
            try:
                keys = sorted(column, key=lambda key: int(key))
            except (TypeError, ValueError):
                keys = list(column)
            return [column[key] for key in keys]
        if isinstance(column, list):
            return column
        raise ValueError(f"{path} contains a non-list column")

    columns = {name: as_list(values) for name, values in data.items()}
    lengths = {len(values) for values in columns.values()}
    if len(lengths) > 1:
        raise ValueError(f"{path} contains columns with different lengths")
    row_count = lengths.pop() if lengths else 0
    return [
        {name: values[index] for name, values in columns.items()}
        for index in range(row_count)
    ]


def load_swebench_items(
    input_path: Path,
    selected_models: set[str] | None,
    limit: int | None,
) -> list[ClassificationItem]:
    if not input_path.is_file():
        raise ValueError("SWE-bench input must be a tool-call JSON file")

    items: list[ClassificationItem] = []
    for row in _columnar_rows(input_path):
        model = str(row.get("model") or "")
        if selected_models is not None and model not in selected_models:
            continue
        for entry_index, entry in enumerate(row.get("tool_calls") or []):
            if not isinstance(entry, dict):
                continue
            reasoning = entry.get("reasoning_content") or ""
            for tool_index, tool in enumerate(entry.get("tools") or []):
                if not isinstance(tool, dict):
                    continue
                function = tool.get("function") or {}
                key = (row.get("id"), entry_index, tool_index)
                items.append(ClassificationItem(
                    key=key,
                    tool_call_info={
                        "assistant_reasoning_text": reasoning,
                        "assistant_content": "",
                        "tool_intention_summary": "",
                        "tool_name": function.get("name") or "",
                        "tool_arguments": _parse_tool_arguments(
                            function.get("arguments")
                        ),
                    },
                    metadata={
                        "id": row.get("id"),
                        "model": model,
                        "task": row.get("task"),
                        "score": row.get("score"),
                        "entry_index": entry_index,
                        "tool_index": tool_index,
                    },
                ))
                if limit is not None and len(items) >= limit:
                    return items
    return items


def swebench_record_key(record: dict[str, Any]) -> Hashable | None:
    entry_index = record.get("entry_index")
    tool_index = record.get("tool_index")
    if not isinstance(entry_index, int) or not isinstance(tool_index, int):
        return None
    return (record.get("id"), entry_index, tool_index)


def _resolve_cabra_layout(input_path: Path) -> tuple[Path, Path, Path]:
    input_path = input_path.resolve()
    if (input_path / "responses").is_dir():
        data_root = input_path
    else:
        cursor = input_path.parent if input_path.is_file() else input_path
        while cursor.name != "responses" and cursor != cursor.parent:
            cursor = cursor.parent
        if cursor.name != "responses":
            raise ValueError(
                "CABRA input must be local_data, its responses folder, "
                "or a response JSONL file"
            )
        data_root = cursor.parent
    return (
        data_root / "responses",
        data_root / "results",
        data_root / "copilot_traces",
    )


def cabra_output_stem(input_path: Path) -> str:
    """Derive a stable output-name stem from a CABRA input path."""
    responses_root, _, _ = _resolve_cabra_layout(input_path)
    resolved_input = input_path.resolve()
    if resolved_input in {responses_root.parent, responses_root}:
        return "cabra_tool_call_labels"
    if resolved_input.is_file():
        relative = resolved_input.relative_to(responses_root).with_suffix("")
        return "__".join(relative.parts)

    relative = resolved_input.relative_to(responses_root)
    return "__".join(relative.parts)


def _response_files(input_path: Path, responses_root: Path) -> list[Path]:
    if input_path.is_file():
        response_path = input_path.resolve()
        try:
            response_path.relative_to(responses_root)
        except ValueError as exc:
            raise ValueError(
                f"CABRA response file must be inside {responses_root}: {response_path}"
            ) from exc
        return [response_path]
    search_root = input_path.resolve()
    if search_root == responses_root.parent:
        search_root = responses_root
    if search_root.name == "copilot":
        return sorted(search_root.glob("*.jsonl"))
    return sorted(search_root.glob("**/copilot/*.jsonl"))


def _trace_tool_calls(trace_path: Path) -> list[dict[str, Any]]:
    tool_calls: list[dict[str, Any]] = []
    for event in iter_jsonl(trace_path):
        if event.get("type") != "assistant.message":
            continue
        data = event.get("data") or {}
        for request_index, request in enumerate(data.get("toolRequests") or []):
            if not isinstance(request, dict):
                continue
            tool_calls.append({
                "assistant_reasoning_text": data.get("reasoningText") or "",
                "assistant_content": data.get("content") or "",
                "tool_request_index": request_index,
                "tool_name": request.get("name") or "",
                "tool_arguments": request.get("arguments") or {},
                "tool_intention_summary": request.get("intentionSummary") or "",
            })
    return tool_calls


def _result_records(
    response_path: Path,
    responses_root: Path,
    results_root: Path,
) -> dict[str, dict[str, Any]]:
    try:
        relative_path = response_path.relative_to(responses_root)
    except ValueError:
        return {}
    result_path = results_root / relative_path
    if not result_path.is_file():
        return {}
    return {
        str(record.get("dag_id") or ""): record
        for record in iter_jsonl(result_path)
    }


def _cabra_path_metadata(
    response_path: Path,
    responses_root: Path,
) -> dict[str, str]:
    relative_path = response_path.relative_to(responses_root)
    parts = relative_path.parts
    if len(parts) < 3 or parts[-2] != "copilot":
        raise ValueError(f"unrecognized CABRA response path: {response_path}")
    hierarchy = parts[:-2]
    experiment = hierarchy[0]
    if len(hierarchy) >= 3:
        task_set_name = hierarchy[-2]
        task_type = hierarchy[-1]
    else:
        task_set_name = experiment
        task_type = hierarchy[-1] if len(hierarchy) == 2 else ""
    return {
        "experiment": experiment,
        "task_set_name": task_set_name,
        "task_type": task_type,
        "model": f"copilot/{response_path.stem}",
    }


def load_cabra_items(
    input_path: Path,
    selected_models: set[str] | None,
    limit: int | None,
) -> list[ClassificationItem]:
    from tqdm import tqdm

    responses_root, results_root, traces_root = _resolve_cabra_layout(input_path)
    print(f"[info] CABRA responses: {responses_root}")
    print(f"[info] CABRA results:   {results_root}")
    print(f"[info] CABRA traces:    {traces_root}")
    if not traces_root.is_dir():
        raise ValueError(f"Copilot trace directory does not exist: {traces_root}")

    items: list[ClassificationItem] = []
    missing_traces: list[str] = []
    response_files = _response_files(input_path, responses_root)
    progress = tqdm(
        total=len(response_files),
        desc="loading CABRA data",
        unit="file",
    )
    try:
        for response_path in response_files:
            progress.update(1)
            path_metadata = _cabra_path_metadata(response_path, responses_root)
            model = path_metadata["model"]
            if selected_models is not None and model not in selected_models:
                continue
            results_by_dag = _result_records(
                response_path, responses_root, results_root
            )
            latest_responses = {
                str(record.get("dag_id") or ""): record
                for record in iter_jsonl(response_path)
            }
            for dag_id, response in latest_responses.items():
                metadata = response.get("metadata")
                if not isinstance(metadata, dict):
                    metadata = {}
                session_id = str(metadata.get("session_id") or "")
                trace_path = traces_root / session_id / "events.jsonl"
                if not session_id or not trace_path.is_file():
                    missing_traces.append(session_id or f"<missing for {dag_id}>")
                    continue
                result = results_by_dag.get(dag_id) or {}
                for tool_call_index, tool_call_info in enumerate(
                    _trace_tool_calls(trace_path)
                ):
                    items.append(ClassificationItem(
                        key=(session_id, tool_call_index),
                        tool_call_info=tool_call_info,
                        metadata={
                            **path_metadata,
                            "run_name": metadata.get("run_name")
                            or path_metadata["experiment"],
                            "task_name": response.get("name"),
                            "dag_id": dag_id,
                            "session_id": session_id,
                            "tool_call_index": tool_call_index,
                            "result_parsed_ok": result.get("parsed_ok"),
                            "result_summary": result.get("summary"),
                        },
                    ))
                    if limit is not None and len(items) >= limit:
                        return items
    finally:
        progress.close()
    if missing_traces:
        examples = ", ".join(missing_traces[:3])
        print(
            f"[warn] skipped {len(missing_traces)} CABRA responses with no "
            f"copied Copilot trace (examples: {examples})"
        )
    return items


def cabra_record_key(record: dict[str, Any]) -> Hashable | None:
    session_id = record.get("session_id")
    tool_call_index = record.get("tool_call_index")
    if not session_id or not isinstance(tool_call_index, int):
        return None
    return (str(session_id), tool_call_index)

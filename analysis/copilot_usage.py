"""Extract and summarize usage from historical Copilot CLI traces."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any, TextIO

from tqdm import tqdm


def _open_text(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open(encoding="utf-8")


def _iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with _open_text(path) as trace_file:
        for line_number, line in enumerate(trace_file, start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"[warn] skipping invalid JSON in {path}:{line_number}: {exc}")
                continue
            if isinstance(event, dict):
                yield event


def _normalize_model(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("id") or value.get("name")
    if not isinstance(value, str) or not value.strip():
        return None
    model = value.strip()
    return model if model.startswith("copilot/") else f"copilot/{model}"


def _model_from_event(event: dict[str, Any]) -> str | None:
    data = event.get("data")
    if not isinstance(data, dict):
        return None
    for key in ("model", "modelName", "selectedModel"):
        model = _normalize_model(data.get(key))
        if model:
            return model
    return None


def _session_models(responses_root: Path) -> dict[str, str]:
    models: dict[str, str] = {}
    if not responses_root.is_dir():
        print(f"[warn] response directory not found: {responses_root}")
        return models

    response_paths = list(responses_root.rglob("copilot/*.jsonl"))
    for response_path in tqdm(
        response_paths, desc="Indexing responses", unit="file"
    ):
        model = f"copilot/{response_path.stem}"
        for record in _iter_jsonl(response_path):
            metadata = record.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            session_id = record.get("session_id") or metadata.get("session_id")
            if session_id:
                models[str(session_id)] = model
    return models


def _number(data: dict[str, Any], *keys: str) -> int | float | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
    return None


def _token_count(token_details: dict[str, Any], category: str) -> int | float | None:
    detail = token_details.get(category)
    if not isinstance(detail, dict):
        return None
    return _number(detail, "tokenCount")


def _trace_usage(path: Path, mapped_model: str | None) -> dict[str, Any]:
    checkpoint: dict[str, Any] | None = None
    shutdown: dict[str, Any] | None = None
    message_input_tokens = 0
    message_output_tokens = 0
    saw_input_tokens = False
    saw_output_tokens = False
    trace_model = None

    for event in _iter_jsonl(path):
        trace_model = trace_model or _model_from_event(event)
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        event_type = event.get("type")
        if event_type == "assistant.message":
            usage = data.get("usage")
            usage = usage if isinstance(usage, dict) else {}
            input_value = _number(data, "inputTokens")
            output_value = _number(data, "outputTokens")
            input_value = input_value if input_value is not None else _number(
                usage, "inputTokens", "input_tokens", "prompt_tokens"
            )
            output_value = output_value if output_value is not None else _number(
                usage, "outputTokens", "output_tokens", "completion_tokens"
            )
            if input_value is not None:
                message_input_tokens += input_value
                saw_input_tokens = True
            if output_value is not None:
                message_output_tokens += output_value
                saw_output_tokens = True
        elif event_type in {"session.usage_checkpoint", "session.shutdown"}:
            if event_type == "session.shutdown":
                shutdown = data
            else:
                checkpoint = data

    usage_data = shutdown or checkpoint or {}
    usage_source = (
        "session.shutdown" if shutdown else
        "session.usage_checkpoint" if checkpoint else None
    )
    token_details = usage_data.get("tokenDetails")
    token_details = token_details if isinstance(token_details, dict) else {}
    has_token_details = bool(token_details)
    input_tokens = (
        _token_count(token_details, "input")
        if has_token_details else
        message_input_tokens if saw_input_tokens else None
    )
    output_tokens = (
        _token_count(token_details, "output")
        if has_token_details else
        message_output_tokens if saw_output_tokens else None
    )
    cache_read_tokens = _token_count(token_details, "cache_read")
    cache_write_tokens = _token_count(token_details, "cache_write")
    token_counts = (
        input_tokens, cache_read_tokens, cache_write_tokens, output_tokens
    )
    total_tokens = (
        sum(value for value in token_counts if value is not None)
        if any(value is not None for value in token_counts) else None
    )
    total_nano_aiu = _number(usage_data, "totalNanoAiu")
    return {
        "session_id": path.parent.name,
        "model": mapped_model or trace_model or "unknown",
        "total_nano_aiu": total_nano_aiu,
        "total_aiu": total_nano_aiu / 1_000_000_000 if total_nano_aiu is not None else None,
        "total_premium_requests": _number(usage_data, "totalPremiumRequests"),
        "input_tokens": input_tokens,
        "cache_read_tokens": cache_read_tokens,
        "cache_write_tokens": cache_write_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "usage_source": usage_source,
        "token_usage_source": usage_source if has_token_details else "assistant.message",
        "trace_path": path.as_posix(),
    }


def _trace_paths(traces_root: Path) -> list[Path]:
    paths = list(traces_root.glob("*/events.jsonl"))
    paths.extend(traces_root.glob("*/events.jsonl.gz"))
    return sorted(paths)


def _sum(rows: Iterable[dict[str, Any]], field: str) -> int | float:
    return sum(row[field] for row in rows if row[field] is not None)


def _print_totals(label: str, rows: list[dict[str, Any]]) -> None:
    print(
        f"{label}: sessions={len(rows)}, "
        f"AIU={_sum(rows, 'total_aiu'):.6f}, "
        f"premium_requests={_sum(rows, 'total_premium_requests'):g}, "
        f"input_tokens={_sum(rows, 'input_tokens'):g}, "
        f"cache_read_tokens={_sum(rows, 'cache_read_tokens'):g}, "
        f"cache_write_tokens={_sum(rows, 'cache_write_tokens'):g}, "
        f"output_tokens={_sum(rows, 'output_tokens'):g}, "
        f"total_tokens={_sum(rows, 'total_tokens'):g}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract AI credits and token usage from Copilot traces."
    )
    parser.add_argument(
        "--traces-root", type=Path, default=Path("local_data/copilot_traces")
    )
    parser.add_argument(
        "--responses-root",
        type=Path,
        default=Path("local_data/responses"),
        help="Response tree used to map session IDs to model names.",
    )
    parser.add_argument(
        "--output", type=Path, default=Path("local_data/copilot_usage.csv")
    )
    args = parser.parse_args()

    if not args.traces_root.is_dir():
        parser.error(f"trace directory not found: {args.traces_root}")

    session_models = _session_models(args.responses_root)
    trace_paths = _trace_paths(args.traces_root)
    rows = [
        _trace_usage(path, session_models.get(path.parent.name))
        for path in tqdm(trace_paths, desc="Processing traces", unit="trace")
    ]
    if not rows:
        parser.error(f"no events.jsonl or events.jsonl.gz files found in {args.traces_root}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    _print_totals("TOTAL", rows)
    by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_model[row["model"]].append(row)
    print("\nPER MODEL")
    for model in sorted(by_model):
        _print_totals(model, by_model[model])
    print(f"\nSaved {len(rows)} session rows to {args.output}")


if __name__ == "__main__":
    main()
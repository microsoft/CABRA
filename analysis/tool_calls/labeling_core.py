"""Shared classification and output logic for tool-call labeling."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable, Hashable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .prompts import PROMPTS

# tool call taxonomy (understand -> analyze)
VALID_LABELS = (
    "read",
    "search",
    "understand",
    "edit",
    "test",
    "summary",
    "plan",
    "other",
)
DEFAULT_CLASSIFIER_MODEL = "Qwen/Qwen3-4B-Instruct-2507" # the sglang model
DEFAULT_FALLBACK_MODEL = "openrouter/openai/gpt-4.1" # backup model if sglang model fails
DEFAULT_SGLANG_URL = "http://127.0.0.1:30000/v1"
MAX_REASONING_CHARS = 8_000
MAX_CONTENT_CHARS = 4_000
MAX_INTENTION_CHARS = 2_000
MAX_ARGUMENT_CHARS = 12_000


class ClassificationError(RuntimeError):
    """Raised when a classifier backend cannot produce a valid label."""


@dataclass(frozen=True)
class ClassificationItem:
    key: Hashable
    tool_call_info: dict[str, Any]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class ClassifierConfig:
    dataset: str
    classifier_model: str
    fallback_model: str | None
    backend: str = "sglang"
    sglang_url: str = DEFAULT_SGLANG_URL
    max_retries: int = 5

    def __post_init__(self) -> None:
        if self.dataset not in PROMPTS:
            raise ValueError(f"unsupported dataset: {self.dataset}")
        if self.backend not in {"sglang", "litellm"}:
            raise ValueError(f"unsupported classifier backend: {self.backend}")
        if self.max_retries < 1:
            raise ValueError("max_retries must be at least 1")


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return
    with path.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"[warn] skipping invalid JSON in {path}:{line_number}: {exc}")
                continue
            if isinstance(record, dict):
                yield record
            else:
                print(f"[warn] skipping non-object JSON in {path}:{line_number}")


def parse_classification_output(text: str) -> dict[str, str]:
    normalized = re.sub(r"[^a-z]+", " ", text.lower()).strip()
    words = normalized.split()
    matches = [label for label in (*VALID_LABELS, "verify") if label in words]
    if len(matches) != 1:
        raise ClassificationError(f"expected exactly one label, received {text!r}")
    label = "test" if matches[0] == "verify" else matches[0]
    return {"label": label, "reason": ""}


def _automatic_classification(tool_call_info: dict[str, Any]) -> dict[str, str] | None:
    tool_name = tool_call_info.get("tool_name")
    if tool_name == "task_complete":
        return {"label": "summary", "reason": ""}
    if tool_name == "sql":
        return {"label": "plan", "reason": ""}
    return None


def _truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    marker = "\n... [truncated for classifier context] ...\n"
    retained_chars = max_chars - len(marker)
    head_chars = retained_chars // 2
    tail_chars = retained_chars - head_chars
    return f"{text[:head_chars]}{marker}{text[-tail_chars:]}"


def _format_tool_call(tool_call_info: dict[str, Any]) -> str:
    reasoning = _truncate_text(
        str(tool_call_info.get("assistant_reasoning_text") or ""),
        MAX_REASONING_CHARS,
    )
    assistant_content = _truncate_text(
        str(tool_call_info.get("assistant_content") or ""),
        MAX_CONTENT_CHARS,
    )
    intention = _truncate_text(
        str(tool_call_info.get("tool_intention_summary") or ""),
        MAX_INTENTION_CHARS,
    )
    arguments = _truncate_text(json.dumps(
        tool_call_info.get("tool_arguments") or {},
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    ), MAX_ARGUMENT_CHARS)
    return (
        f"<reasoning>\n{reasoning}\n</reasoning>\n"
        f"<assistant_content>\n{assistant_content}\n"
        "</assistant_content>\n"
        f"<tool_intention>\n{intention}\n"
        "</tool_intention>\n"
        f"<tool_name>\n{tool_call_info.get('tool_name') or ''}\n</tool_name>\n"
        f"<tool_arguments>\n{arguments}\n</tool_arguments>"
    )


async def _retry(
    operation: Callable[[], Any],
    *,
    backend: str,
    model: str,
    max_retries: int,
) -> dict[str, str]:
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            result = await operation()
            return parse_classification_output(result)
        except Exception as exc:
            last_error = exc
            print(
                f"[warn] {backend} model {model} attempt {attempt}/{max_retries} "
                f"failed: {type(exc).__name__}: {exc}"
            )
            if attempt < max_retries:
                await asyncio.sleep(min(2 ** (attempt - 1), 30))
    raise ClassificationError(
        f"{backend} model {model} failed after {max_retries} attempts"
    ) from last_error


async def _classify_sglang(
    content: str,
    model: str,
    base_url: str,
    max_retries: int,
) -> dict[str, str]:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(base_url=base_url, api_key="EMPTY")

    async def request() -> str:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": content}],
            temperature=0,
            max_tokens=16,
        )
        return response.choices[0].message.content or ""

    return await _retry(
        request,
        backend="SGLang",
        model=model,
        max_retries=max_retries,
    )


async def _classify_litellm(
    content: str,
    model: str,
    max_retries: int,
) -> dict[str, str]:
    import litellm

    litellm.suppress_debug_info = True

    async def request() -> str:
        response = await litellm.acompletion(
            model=model,
            messages=[{"role": "user", "content": content}],
            temperature=0,
            max_tokens=16,
        )
        return response.choices[0].message.content or ""

    return await _retry(
        request,
        backend="LiteLLM",
        model=model,
        max_retries=max_retries,
    )


async def classify_tool_call(
    tool_call_info: dict[str, Any],
    config: ClassifierConfig,
) -> dict[str, str]:
    automatic = _automatic_classification(tool_call_info)
    if automatic is not None:
        return automatic

    content = PROMPTS[config.dataset].format(
        tool_call=_format_tool_call(tool_call_info)
    )
    try:
        if config.backend == "litellm":
            return await _classify_litellm(
                content, config.classifier_model, config.max_retries
            )
        return await _classify_sglang(
            content,
            config.classifier_model,
            config.sglang_url,
            config.max_retries,
        )
    except ClassificationError as primary_error:
        if config.fallback_model is None:
            raise
        if (
            config.backend == "litellm"
            and config.fallback_model == config.classifier_model
        ):
            raise
        print(
            f"[fallback] primary classifier failed; trying "
            f"{config.fallback_model} through LiteLLM"
        )
        try:
            return await _classify_litellm(
                content, config.fallback_model, config.max_retries
            )
        except ClassificationError as fallback_error:
            raise ClassificationError(
                f"primary and fallback classifiers failed: {primary_error}; "
                f"{fallback_error}"
            ) from fallback_error


def _successful(record: dict[str, Any]) -> bool:
    return record.get("label") in VALID_LABELS and not record.get("error")


def _rewrite_successful_records(path: Path) -> list[dict[str, Any]]:
    records = list(iter_jsonl(path))
    successful = [record for record in records if _successful(record)]
    if len(successful) != len(records):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(path.suffix + ".tmp")
        with temporary_path.open("w", encoding="utf-8") as file:
            for record in successful:
                file.write(json.dumps(record, ensure_ascii=False) + "\n")
        temporary_path.replace(path)
        print(f"[resume] removed {len(records) - len(successful)} failed records")
    return successful


async def run_labeling(
    *,
    items: list[ClassificationItem],
    output_path: Path,
    key_from_record: Callable[[dict[str, Any]], Hashable | None],
    classifier_config: ClassifierConfig,
    n_parallel: int,
    overwrite: bool,
    dry_run: bool,
) -> None:
    if overwrite:
        output_path.unlink(missing_ok=True)

    existing_records = _rewrite_successful_records(output_path)
    completed_keys = {
        key
        for record in existing_records
        if (key := key_from_record(record)) is not None
    }
    pending_items = [item for item in items if item.key not in completed_keys]

    if dry_run:
        print(
            f"[dry-run] {len(items)} tool calls "
            f"({len(items) - len(pending_items)} labeled, "
            f"{len(pending_items)} pending) -> {output_path}"
        )
        for item in pending_items[:5]:
            print(
                f"  {item.key!r}: "
                f"{item.tool_call_info.get('tool_name') or '<unnamed>'}"
            )
        return
    if not pending_items:
        print("[done] nothing to classify")
        return

    from tqdm import tqdm

    output_path.parent.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(n_parallel)
    output_lock = asyncio.Lock()
    progress = tqdm(total=len(pending_items), desc="classifying tool calls")
    written_records: list[dict[str, Any]] = []
    failures: list[tuple[ClassificationItem, Exception]] = []

    async def worker(item: ClassificationItem) -> None:
        try:
            async with semaphore:
                model_output = await classify_tool_call(
                    item.tool_call_info, classifier_config
                )
            record = {
                **item.metadata,
                "tool_call_information": item.tool_call_info,
                **model_output,
            }
            async with output_lock:
                with output_path.open("a", encoding="utf-8") as file:
                    file.write(json.dumps(record, ensure_ascii=False) + "\n")
                written_records.append(record)
        except Exception as exc:
            failures.append((item, exc))
            record = {
                **item.metadata,
                "tool_call_information": item.tool_call_info,
                "error": f"{type(exc).__name__}: {exc}",
            }
            async with output_lock:
                with output_path.open("a", encoding="utf-8") as file:
                    file.write(json.dumps(record, ensure_ascii=False) + "\n")
        finally:
            progress.update(1)

    await asyncio.gather(*(worker(item) for item in pending_items))
    progress.close()
    print(f"[done] wrote {len(written_records)} classifications to {output_path}")
    if failures:
        first_item, first_error = failures[0]
        print(
            f"[warn] recorded {len(failures)} failed tool calls for retry on "
            f"the next run; first failure was {first_item.key!r}: {first_error}"
        )

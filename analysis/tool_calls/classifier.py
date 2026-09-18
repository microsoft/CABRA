"""Classify CABRA or SWE-bench coding-agent tool calls."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
from pathlib import Path

from .data_sources import (
    cabra_output_stem,
    cabra_record_key,
    load_cabra_items,
    load_swebench_items,
    swebench_record_key,
)
from .labeling_core import (
    DEFAULT_CLASSIFIER_MODEL,
    DEFAULT_FALLBACK_MODEL,
    DEFAULT_SGLANG_URL,
    ClassifierConfig,
    run_labeling,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_ROOT = REPOSITORY_ROOT / "local_data"
DEFAULT_OUTPUT_NAMES = {
    "cabra": "cabra_tool_call_labels",
    "swebench": "swe_bench_tool_call_labels",
}


def parse_args(
    default_dataset: str | None = None,
    argv: list[str] | None = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        choices=["cabra", "swebench"],
        default=default_dataset,
        required=default_dataset is None,
        help="input schema and classification prompt to use",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help=(
            "CABRA local_data/response path, or a "
            "SWE-bench tool-call JSON file"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_DATA_ROOT / "tool_call_results",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        default=None,
        help="exact output JSONL path (overrides --output-dir)",
    )
    parser.add_argument(
        "--output-name",
        default=None,
        help="output filename stem inside --output-dir (without .jsonl)",
    )
    parser.add_argument("--models", nargs="+", default=None)
    parser.add_argument("--classifier-model", default=DEFAULT_CLASSIFIER_MODEL)
    parser.add_argument("--fallback-model", default=DEFAULT_FALLBACK_MODEL)
    parser.add_argument(
        "--no-fallback",
        action="store_true",
        help="fail if the primary classifier fails instead of calling LiteLLM",
    )
    parser.add_argument(
        "--backend",
        choices=["sglang", "litellm"],
        default="sglang",
        help="Backend for the primary classifier. Fallback always uses LiteLLM",
    )
    parser.add_argument("--sglang-url", default=DEFAULT_SGLANG_URL)
    parser.add_argument("--n-parallel", type=int, default=4)
    parser.add_argument("--max-retries", type=int, default=5)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.n_parallel < 1:
        parser.error("--n-parallel must be at least 1")
    if args.max_retries < 1:
        parser.error("--max-retries must be at least 1")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    return args


def _default_input(dataset: str) -> Path:
    if dataset == "cabra":
        return DEFAULT_DATA_ROOT
    return DEFAULT_DATA_ROOT / "tool_call_results" / "swe_bench_tool_calls.json"


def _model_slug(model: str) -> str:
    return model.replace("/", "__")


def _safe_stem(stem: str, max_length: int = 180) -> str:
    stem = stem.replace("/", "__")
    if len(stem) <= max_length:
        return stem
    digest = hashlib.sha1(stem.encode("utf-8")).hexdigest()[:12]
    return f"{stem[:max_length - len(digest) - 2]}__{digest}"


def _default_output_stem(
    dataset: str,
    input_path: Path,
    explicit_input: bool,
) -> str:
    if dataset == "cabra" and explicit_input:
        return cabra_output_stem(input_path)
    if dataset == "swebench" and explicit_input and input_path.is_file():
        return input_path.stem
    return DEFAULT_OUTPUT_NAMES[dataset]


def _output_path(args: argparse.Namespace, input_path: Path) -> Path:
    if args.output_file is not None:
        return args.output_file
    name = args.output_name or _default_output_stem(
        args.dataset,
        input_path,
        args.input is not None,
    )
    name = _safe_stem(f"{name}__{_model_slug(args.classifier_model)}")
    return args.output_dir / f"{name}.jsonl"


def main(
    default_dataset: str | None = None,
    argv: list[str] | None = None,
) -> None:
    args = parse_args(default_dataset, argv)
    input_path = args.input or _default_input(args.dataset)
    selected_models = set(args.models) if args.models else None
    if args.dataset == "cabra":
        items = load_cabra_items(input_path, selected_models, args.limit)
        key_from_record = cabra_record_key
    else:
        items = load_swebench_items(input_path, selected_models, args.limit)
        key_from_record = swebench_record_key

    output_path = _output_path(args, input_path)
    asyncio.run(run_labeling(
        items=items,
        output_path=output_path,
        key_from_record=key_from_record,
        classifier_config=ClassifierConfig(
            dataset=args.dataset,
            classifier_model=args.classifier_model,
            fallback_model=None if args.no_fallback else args.fallback_model,
            backend=args.backend,
            sglang_url=args.sglang_url,
            max_retries=args.max_retries,
        ),
        n_parallel=args.n_parallel,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
    ))


if __name__ == "__main__":
    main()

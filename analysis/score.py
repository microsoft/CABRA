"""Score model responses against test cases for one or more runs. It parallelizes scoring for multiple runs to speed up eval."""

import argparse
import itertools
import json
import re
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from tqdm import tqdm

from data.tasks.task import TaskType
from data.tasks.task_loader import TaskLoader
from data.tasks.test_cases import BehavioralTestCase
from model.response_cache import ResponseCache

SOLUTION_FILENAME = "solution.py"

def _parse_codebase(output: str) -> dict[str, str]:
    """Reverse of agents._serialize_codebase: split `# === filename ===` blocks."""
    parts = re.split(r"^\s*#\s*===\s*(.+?)\s*===\s*$", output, flags=re.MULTILINE)
    if len(parts) < 3:
        return {}
    return {parts[i].strip(): parts[i + 1].strip("\n") for i in range(1, len(parts), 2)}


def _result_record(name: str, dag_id: str, parsed_ok: bool, results, test_cases, summary) -> dict:
    return {
        "name": name,
        "dag_id": dag_id,
        "parsed_ok": parsed_ok,
        "summary": summary,
        "results": [
            {
                "kind": tc.KIND.value,
                "type": r.test_case_type.value,
                "metadata": r.metadata,
            }
            for tc, r in zip(test_cases, results)
        ],
    }


def _score_combo(
    model: str,
    task_type: TaskType,
    tasks_dir: Path,
    test_cases_dir: Path,
    task_set_name: str,
    responses_dir: Path,
    output_dir: Path,
    run_name: str,
    limit: int | None = None,
    memoize: bool = False,
) -> tuple[tuple[str, TaskType], dict | None, bool, bool]:
    """Score one (model, task_type) combo. Returns (key, summary, is_missing, is_already_scored)."""
    task_set = TaskLoader.load_tasks_with_test_cases(
        str(tasks_dir / task_set_name),
        str(test_cases_dir / task_set_name),
        task_set_name,
        task_types=[task_type],
    )

    jsonl = responses_dir / run_name / task_set_name / task_type.value / f"{model}.jsonl"
    if not jsonl.exists():
        return (model, task_type), None, True, False

    cache = ResponseCache(jsonl)

    out_path = output_dir / run_name / task_set_name / task_type.value / f"{model}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if out_path.exists():
        meta_path = out_path.with_suffix(".meta.json")
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                summary = {
                    "n_records": meta.get("n_records", 0),
                    "n_ran": meta.get("n_ran", 0),
                    "n_skipped": meta.get("n_skipped", 0),
                    "by_kind": meta.get("by_kind", {}),
                }
                return (model, task_type), summary, False, True
            except Exception as exc:
                print(f"[warn] invalid meta file, rescoring: {meta_path} ({exc})")
                out_path.unlink(missing_ok=True)
                meta_path.unlink(missing_ok=True)
        else:
            print(f"[warn] missing meta file, rescoring: {out_path}")
            out_path.unlink(missing_ok=True)

    kind_totals: dict[str, dict] = defaultdict(lambda: {"pass": 0, "fail": 0, "error": 0})
    n_records = 0
    n_skipped = 0
    n_ran = 0

    with out_path.open("a") as out_f:
        for rec in cache.iter_records():
            if limit is not None and n_records >= limit:
                break
            task = task_set.tasks.get((rec["dag_id"], task_type))
            assert task is not None, (
                f"response references unknown task: dag_id={rec['dag_id']} "
                f"task_type={task_type.value} model={model} jsonl={jsonl}"
            )
            assert task.test_cases is not None, (
                f"task has no test_cases: dag_id={rec['dag_id']} "
                f"task_type={task_type.value} model={model}"
            )
            files = _parse_codebase(rec.get("output") or "")
            if isinstance(task.starter_code, dict):
                code = files
                parsed_ok = bool(code)
            else:
                code = files.get(SOLUTION_FILENAME, "")
                parsed_ok = bool(code)
            n_records += 1
            if not parsed_ok:
                n_skipped += 1
                record = {
                    "name": rec["name"],
                    "dag_id": rec["dag_id"],
                    "parsed_ok": False,
                    "skipped": True,
                    "summary": {},
                    "results": [],
                }
                out_f.write(json.dumps(record, separators=(",", ":"), default=str) + "\n")
                out_f.flush()
                continue
            if memoize:
                for tc in task.test_cases.test_cases:
                    if isinstance(tc, BehavioralTestCase):
                        tc.memoize = True
            results = task.test_cases.run_all(code, task.starter_code, task.solution_code)
            summary = task.test_cases.summary(results)
            for kind, counts in summary.items():
                for k in ("pass", "fail", "error"):
                    kind_totals[kind][k] += counts[k]
            n_ran += 1
            record = _result_record(
                rec["name"], rec["dag_id"], parsed_ok, results,
                task.test_cases.test_cases, summary,
            )
            out_f.write(json.dumps(record, separators=(",", ":"), default=str) + "\n")
            out_f.flush()

    for counts in kind_totals.values():
        total = counts["pass"] + counts["fail"] + counts["error"]
        counts["pass_rate"] = counts["pass"] / total if total else 0.0

    run_summary = {
        "n_records": n_records,
        "n_ran": n_ran,
        "n_skipped": n_skipped,
        "by_kind": dict(kind_totals),
    }

    meta_path = out_path.with_suffix(".meta.json")
    meta = {
        "run_name": run_name,
        "task_set": task_set_name,
        "task_type": task_type.value,
        "model": model,
        "responses_path": str(jsonl),
        **run_summary,
    }
    meta_path.write_text(json.dumps(meta, separators=(",", ":"), default=str))

    return (model, task_type), run_summary, False, False


def score_run(
    tasks_dir: Path,
    test_cases_dir: Path,
    task_set_name: str,
    task_types: list[TaskType],
    responses_dir: Path,
    output_dir: Path,
    run_name: str,
    models: list[str],
    overwrite: bool = False,
    yes: bool = False,
    n_workers: int = 1,
    limit: int | None = None,
    memoize: bool = False,
) -> dict[tuple[str, TaskType], dict]:
    """Return {(model, task_type): summary} where summary aggregates pass rates by test-case kind.

    Also writes per-record results to {output_dir}/{run_name}/{task_set}/{task_type}/{model}.jsonl.
    """
    out: dict[tuple[str, TaskType], dict] = {}

    existing = [
        output_dir / run_name / task_set_name / tt.value / f"{model}.jsonl"
        for model in models
        for tt in task_types
        if (output_dir / run_name / task_set_name / tt.value / f"{model}.jsonl").exists()
    ]
    if existing:
        if overwrite:
            print(f"Overwrite will delete {len(existing)} existing result file(s).")
            if not yes:
                response = input("Proceed? [y/N]: ")
                if response.lower() != "y":
                    print("Aborting.")
                    return out
            for p in existing:
                p.unlink()
        else:
            print(f"[skip] {len(existing)} already-scored file(s) (use --overwrite to rescore)")

    combos = list(itertools.product(models, task_types))

    n_missing_responses = 0
    n_already_scored = 0

    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        futures = {
            pool.submit(
                _score_combo,
                model, task_type,
                tasks_dir, test_cases_dir, task_set_name,
                responses_dir, output_dir, run_name,
                limit, memoize,
            ): (model, task_type)
            for model, task_type in combos
        }
        for fut in tqdm(as_completed(futures), total=len(futures), desc=f"scoring {task_set_name}"):
            key, summary, is_missing, is_already_scored = fut.result()
            if is_missing:
                n_missing_responses += 1
            elif is_already_scored:
                n_already_scored += 1
                out[key] = summary
            elif summary is not None:
                out[key] = summary

    if n_missing_responses or n_already_scored:
        print(f"[skip] {n_already_scored} already-scored, {n_missing_responses} missing responses")

    return out


def print_table(
    scores: dict[tuple[str, TaskType], dict],
    task_types: list[TaskType],
    models: list[str],
) -> None:
    kinds = sorted({k for s in scores.values() for k in s["by_kind"]})

    for kind in kinds:
        print(f"\n=== Pass rate by test-case kind: {kind} (cell: rate (n=...)) ===")
        header = ["model"] + [t.value for t in task_types] + ["avg"]
        rows = [header]
        for model in models:
            row = [model]
            rates = []
            for tt in task_types:
                summary = scores.get((model, tt))
                if summary is None or kind not in summary["by_kind"]:
                    row.append("-")
                    continue
                rate = summary["by_kind"][kind]["pass_rate"]
                rates.append(rate)
                ran = summary.get("n_ran", 0)
                row.append(f"{rate:.3f} (n={ran})")
            row.append(f"{sum(rates) / len(rates):.3f}" if rates else "-")
            rows.append(row)

        widths = [max(len(r[i]) for r in rows) for i in range(len(header))]
        for i, r in enumerate(rows):
            print("| " + " | ".join(c.ljust(widths[j]) for j, c in enumerate(r)) + " |")
            if i == 0:
                print("| " + " | ".join("-" * widths[j] for j in range(len(header))) + " |")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--task-dir", type=Path, required=True, help="Root tasks dir; expects {task-dir}/{task-set-name}/{task_type}.json")
    p.add_argument("--test-cases-dir", type=Path, required=True, help="Root test cases dir; expects {test-cases-dir}/{task-set-name}/{task_type}.json")
    p.add_argument("--task-set-name", nargs="+", required=True, help="One or more task set names to score.")
    p.add_argument("--task-types", nargs="+", required=True)
    p.add_argument("--responses-dir", type=Path, required=True, help="Root responses dir; reads {responses-dir}/{run}/{task-set}/{task_type}/{model}.jsonl")
    p.add_argument("--output-dir", type=Path, default=Path("local_data/results"), help="Root output dir; writes {output-dir}/{run}/{task-set}/{task_type}/{model}.jsonl")
    p.add_argument("--run-name", required=True)
    p.add_argument("--models", nargs="+", required=True, help="Model file stems under {responses}/{run}/{task-set}/{task_type}/ (e.g. code/openai/gpt-4.1_2025-04-14)")
    p.add_argument("--overwrite", action="store_true", help="Delete existing result files before scoring (prompts for confirmation).")
    p.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompts.")
    p.add_argument("--limit", type=int, default=None, help="Max number of records to score per (model, task_type) combo.")
    p.add_argument("--n-parallel-tests", type=int, default=16, help="Number of (model, task_type) combos to score in parallel (default: 16).")
    p.add_argument("--memoize", action="store_true", help="Memoize behavioral-test function execution.")
    args = p.parse_args()

    task_types = [TaskType(t) for t in args.task_types]

    for task_set_name in args.task_set_name:
        print(f"\n========== task_set: {task_set_name} ==========")
        scores = score_run(
            tasks_dir=args.task_dir,
            test_cases_dir=args.test_cases_dir,
            task_set_name=task_set_name,
            task_types=task_types,
            responses_dir=args.responses_dir,
            output_dir=args.output_dir,
            run_name=args.run_name,
            models=args.models,
            overwrite=args.overwrite,
            yes=args.yes,
            n_workers=args.n_parallel_tests,
            limit=args.limit,
            memoize=args.memoize,
        )
        print_table(scores, task_types, args.models)


if __name__ == "__main__":
    main()

"""
Score model responses for the merge codebase task. We evaluate by checking:
1. Does the output code preserve behavior?
2. Does the output code have the correct number of difference blocks? (each with one line maximum)
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import io
import json
import random
import re
import signal
import traceback
from collections.abc import Generator
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import Any

from tqdm import tqdm

from model.response_cache import ResponseCache


CALCULATE_CLASSES = ("CalculateA", "CalculateB")

Result = dict[str, Any]
Counts = dict[str, int]


@dataclass(frozen=True)
class MergeCodeTask:
	run_name: str
	index: int
	record: dict[str, Any]

	@property
	def name(self) -> str:
		"""Return the display name for this task."""
		return f"{self.run_name}/{self.index:05d}"

	@property
	def dag_id(self) -> str:
		"""Return the response-cache identifier for this task."""
		return f"task_{self.index:05d}"


def _parse_codebase(output: str) -> dict[str, str]:
	"""Reverse of agents._serialize_codebase: split `# === filename ===` blocks."""
	parts = re.split(r"^\s*#\s*===\s*(.+?)\s*===\s*$", output or "", flags=re.MULTILINE)
	if len(parts) < 3:
		return {}
	return {parts[i].strip(): parts[i + 1].strip("\n") for i in range(1, len(parts), 2)}


def _load_run(tasks_root: Path, run_name: str) -> list[MergeCodeTask]:
	"""Load and validate the tasks for a run."""
	path = tasks_root / f"{run_name}.json"
	if not path.exists():
		raise FileNotFoundError(f"run {run_name!r} does not exist at {path}")
	records = json.loads(path.read_text())
	if not isinstance(records, list):
		raise ValueError(f"{path} must contain a JSON list")
	return [MergeCodeTask(run_name, i, rec) for i, rec in enumerate(records)]


def _pass(metadata: dict[str, Any] | None = None) -> Result:
	"""Create a passing scoring result."""
	return {"type": "pass", "metadata": metadata or {}}


def _fail(metadata: dict[str, Any] | None = None) -> Result:
	"""Create a failing scoring result."""
	return {"type": "fail", "metadata": metadata or {}}


def _error(metadata: dict[str, Any] | None = None) -> Result:
	"""Create an error scoring result."""
	return {"type": "error", "metadata": metadata or {}}


def _exception_metadata(exc: Exception) -> dict[str, str]:
	"""Convert an exception into result metadata."""
	return {
		"error": str(exc),
		"error_type": type(exc).__name__,
		"traceback": traceback.format_exc(),
	}


def _compile_check(source: str) -> Result:
	"""Check whether candidate source compiles."""
	try:
		compile(source, "<candidate>", "exec")
	except Exception as exc:
		return _error(_exception_metadata(exc))
	return _pass()


@contextlib.contextmanager
def _timeout(seconds: int) -> Generator[None]:
	"""Raise TimeoutError when a block exceeds its time limit."""
	def handle_timeout(signum: int, frame: FrameType | None) -> None:
		_ = signum, frame
		raise TimeoutError(f"Execution exceeded {seconds}s")

	previous = signal.signal(signal.SIGALRM, handle_timeout)
	signal.alarm(seconds)
	try:
		yield
	finally:
		signal.alarm(0)
		signal.signal(signal.SIGALRM, previous)


def _exec_namespace(source: str, label: str, timeout_seconds: int) -> dict[str, Any]:
	"""Execute source in an isolated namespace with captured output."""
	namespace = {"__name__": f"__score_{label}__"}
	with _timeout(timeout_seconds):
		with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
			exec(compile(source, f"<{label}>", "exec"), namespace)
	return namespace


def _class_defs(tree: ast.AST) -> dict[str, ast.ClassDef]:
	"""Index top-level class definitions by name."""
	return {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}


def _method_def(cls: ast.ClassDef, name: str) -> ast.FunctionDef | None:
	"""Find a directly defined method on a class."""
	for node in cls.body:
		if isinstance(node, ast.FunctionDef) and node.name == name:
			return node
	return None


def _num_positional_compute_args(source: str) -> int:
	"""Infer the positional argument count of a compute method."""
	tree = ast.parse(source)
	classes = _class_defs(tree)
	for cls_name in ("Calculate", "CalculateA", "CalculateB"):
		cls = classes.get(cls_name)
		if cls is None:
			continue
		method = _method_def(cls, "compute")
		if method is None or method.args.vararg is not None:
			continue
		return len([arg for arg in method.args.args if arg.arg != "self"])
	raise ValueError("could not infer compute() positional argument count")


def _behavioral_check(
	candidate: str,
	reference: str,
	num_tests: int,
	seed: int,
	timeout_seconds: int,
	max_failures: int,
) -> Result:
	"""Compare candidate and reference behavior on generated inputs."""
	try:
		num_args = _num_positional_compute_args(reference)
		candidate_ns = _exec_namespace(candidate, "candidate", timeout_seconds)
		reference_ns = _exec_namespace(reference, "reference", timeout_seconds)
		rng = random.Random(seed)
		vectors = [tuple(range(1, num_args + 1))]
		vectors.extend(
			tuple(rng.randint(-5, 5) for _ in range(num_args))
			for _ in range(max(0, num_tests - 1))
		)

		failures: list[dict[str, Any]] = []
		passed = 0
		total = 0
		for trial_idx, inputs in enumerate(vectors):
			for class_name in CALCULATE_CLASSES:
				total += 1
				with _timeout(timeout_seconds):
					with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
						expected = reference_ns[class_name]().compute(*inputs)
						actual = candidate_ns[class_name]().compute(*inputs)
				if actual == expected:
					passed += 1
					continue
				failures.append({
					"trial": trial_idx,
					"class_name": class_name,
					"inputs": inputs,
					"expected": expected,
					"actual": actual,
				})
				if len(failures) >= max_failures:
					return _fail({
						"total": total,
						"passed": passed,
						"failed": len(failures),
						"pass_rate": passed / total if total else 0.0,
						"failures": failures,
						"stopped_early": True,
					})

		metadata = {
			"total": total,
			"passed": passed,
			"failed": len(failures),
			"pass_rate": passed / total if total else 0.0,
			"failures": failures,
			"stopped_early": False,
		}
		return _pass(metadata) if not failures else _fail(metadata)
	except Exception as exc:
		return _error(_exception_metadata(exc))


def _custom_methods(cls: ast.ClassDef) -> dict[int, ast.FunctionDef]:
	"""Index numbered custom compute methods on a class."""
	methods: dict[int, ast.FunctionDef] = {}
	for node in cls.body:
		if not isinstance(node, ast.FunctionDef):
			continue
		match = re.fullmatch(r"custom_compute_(\d+)", node.name)
		if match:
			methods[int(match.group(1))] = node
	return methods


def _custom_call_indices(method: ast.FunctionDef | None) -> list[int]:
	"""Collect custom compute indices called by a method."""
	if method is None:
		return []
	indices: list[int] = []
	for node in ast.walk(method):
		if not isinstance(node, ast.Call):
			continue
		func = node.func
		if not isinstance(func, ast.Attribute):
			continue
		if not isinstance(func.value, ast.Name) or func.value.id != "self":
			continue
		match = re.fullmatch(r"custom_compute_(\d+)", func.attr)
		if match:
			indices.append(int(match.group(1)))
	return indices


def _significant_statement_count(method: ast.FunctionDef) -> int:
	"""Count method statements excluding placeholders and docstrings."""
	count = 0
	for index, stmt in enumerate(method.body):
		if (
			index == 0
			and isinstance(stmt, ast.Expr)
			and isinstance(stmt.value, ast.Constant)
			and isinstance(stmt.value.value, str)
		):
			continue
		if isinstance(stmt, ast.Pass):
			continue
		if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and stmt.value.value is Ellipsis:
			continue
		count += 1
	return count


def _parent_names(cls: ast.ClassDef) -> set[str]:
	"""Return the simple names of a class's direct parents."""
	names = set()
	for base in cls.bases:
		if isinstance(base, ast.Name):
			names.add(base.id)
		elif isinstance(base, ast.Attribute):
			names.add(base.attr)
	return names


def _structure_summary(source: str) -> dict[str, Any]:
	"""Summarize merge-specific structure in source code."""
	tree = ast.parse(source)
	classes = _class_defs(tree)
	calculate = classes.get("Calculate")
	calculate_a = classes.get("CalculateA")
	calculate_b = classes.get("CalculateB")
	if calculate is None or calculate_a is None or calculate_b is None:
		raise ValueError("expected classes Calculate, CalculateA, and CalculateB")

	child_methods = {
		"CalculateA": _custom_methods(calculate_a),
		"CalculateB": _custom_methods(calculate_b),
	}
	child_indices = {
		cls_name: sorted(methods)
		for cls_name, methods in child_methods.items()
	}
	all_child_indices = sorted(set(child_indices["CalculateA"]) | set(child_indices["CalculateB"]))
	line_counts = {
		cls_name: {
			str(idx): _significant_statement_count(method)
			for idx, method in methods.items()
		}
		for cls_name, methods in child_methods.items()
	}

	calculate_methods = _custom_methods(calculate)
	calculate_compute = _method_def(calculate, "compute")
	child_compute_methods = {
		cls_name: _method_def(classes[cls_name], "compute") is not None
		for cls_name in CALCULATE_CLASSES
	}

	return {
		"num_difference_blocks": len(all_child_indices),
		"difference_indices": all_child_indices,
		"child_difference_indices": child_indices,
		"difference_block_line_counts": line_counts,
		"calculate_custom_indices": sorted(calculate_methods),
		"calculate_compute_call_indices": sorted(_custom_call_indices(calculate_compute)),
		"has_calculate_compute": calculate_compute is not None,
		"child_compute_methods": child_compute_methods,
		"subclasses": {
			"CalculateA": "Calculate" in _parent_names(calculate_a),
			"CalculateB": "Calculate" in _parent_names(calculate_b),
		},
	}


def _add_mismatch(
	issues: list[dict[str, Any]],
	check: str,
	expected: Any,
	actual: Any,
	class_name: str | None = None,
) -> None:
	"""Append a structural mismatch when values differ."""
	if actual == expected:
		return
	issue = {"check": check, "expected": expected, "actual": actual}
	if class_name is not None:
		issue["class_name"] = class_name
	issues.append(issue)


def _structure_check(candidate: str, reference: str) -> Result:
	"""Compare candidate structure with the reference solution."""
	try:
		actual = _structure_summary(candidate)
		expected = _structure_summary(reference)
	except Exception as exc:
		return _error(_exception_metadata(exc))

	issues: list[dict[str, Any]] = []
	for check in (
		"num_difference_blocks",
		"difference_indices",
		"calculate_compute_call_indices",
	):
		_add_mismatch(issues, check, expected[check], actual[check])

	for cls_name in CALCULATE_CLASSES:
		for check in ("child_difference_indices", "difference_block_line_counts"):
			_add_mismatch(
				issues,
				check,
				expected[check][cls_name],
				actual[check][cls_name],
				cls_name,
			)
	if not actual["has_calculate_compute"]:
		issues.append({"check": "has_calculate_compute", "expected": True, "actual": False})
	for cls_name, is_subclass in actual["subclasses"].items():
		if not is_subclass:
			issues.append({"check": "subclass", "class_name": cls_name, "expected": True, "actual": False})
	for cls_name, has_compute in actual["child_compute_methods"].items():
		if has_compute:
			issues.append({"check": "child_compute_removed", "class_name": cls_name, "expected": False, "actual": True})

	metadata = {"expected": expected, "actual": actual, "issues": issues}
	return _pass(metadata) if not issues else _fail(metadata)


def _empty_counts() -> Counts:
	"""Create zeroed scoring-result counts."""
	return {"pass": 0, "fail": 0, "error": 0}


def _with_pass_rate(counts: Counts) -> dict[str, int | float]:
	"""Add a pass rate to scoring-result counts."""
	total = sum(counts.values())
	return {**counts, "pass_rate": counts["pass"] / total if total else 0.0}


def _summarize_results(results: dict[str, Result]) -> dict[str, dict[str, int | float]]:
	"""Summarize each scoring check by result type."""
	summary: dict[str, dict[str, int | float]] = {}
	for kind, result in results.items():
		counts = _empty_counts()
		counts[result["type"]] += 1
		summary[kind] = _with_pass_rate(counts)
	return summary


def _score_source(
	candidate: str,
	reference: str,
	num_tests: int,
	seed: int,
	timeout_seconds: int,
	max_failures: int,
) -> tuple[dict[str, Result], dict[str, dict[str, int | float]]]:
	"""Run all scoring checks against candidate source."""
	results = {
		"compilation": _compile_check(candidate),
	}
	if results["compilation"]["type"] == "pass":
		results["behavioral"] = _behavioral_check(
			candidate, reference, num_tests, seed, timeout_seconds, max_failures,
		)
		results["difference_blocks"] = _structure_check(candidate, reference)
	else:
		for kind in ("behavioral", "difference_blocks"):
			results[kind] = _error({"error": "skipped because compilation failed"})
	return results, _summarize_results(results)


def score_run(
	tasks_root: Path,
	responses_dir: Path,
	output_dir: Path,
	run_name: str,
	models: list[str],
	overwrite: bool = False,
	yes: bool = False,
	limit: int | None = None,
	num_tests: int = 20,
	seed: int = 42,
	timeout_seconds: int = 5,
	max_failures: int = 5,
) -> dict[str, dict[str, Any]]:
	"""Score cached model responses for a task run."""
	tasks = {task.dag_id: task for task in _load_run(tasks_root, run_name)}
	out: dict[str, dict[str, Any]] = {}

	result_paths = {
	model: output_dir / run_name / f"{model}.jsonl"
		for model in models
	}
	existing = [path for path in result_paths.values() if path.exists()]
	if existing:
		if overwrite:
			print(f"Overwrite will delete {len(existing)} existing result file(s).")
			if not yes:
				response = input("Proceed? [y/N]: ")
				if response.lower() != "y":
					print("Aborting.")
					return out
			for path in existing:
				path.unlink()
				path.with_suffix(".meta.json").unlink(missing_ok=True)
		else:
			print(f"[skip] {len(existing)} already-scored file(s) (use --overwrite to rescore)")

	for model in models:
		response_path = responses_dir / run_name / f"{model}.jsonl"
		if not response_path.exists():
			print(f"[skip] missing responses: {response_path}")
			continue

		output_path = result_paths[model]
		if output_path.exists() and not overwrite:
			meta_path = output_path.with_suffix(".meta.json")
			if meta_path.exists():
				out[model] = json.loads(meta_path.read_text())
			continue

		output_path.parent.mkdir(parents=True, exist_ok=True)
		cache = ResponseCache(response_path)
		totals: dict[str, Counts] = defaultdict(_empty_counts)
		n_records = 0
		n_scored = 0
		n_skipped = 0

		with output_path.open("w") as handle:
			for rec in tqdm(cache.iter_records(), desc=f"scoring {run_name}/{model}"):
				if limit is not None and n_records >= limit:
					break
				n_records += 1
				task = tasks.get(rec.get("dag_id"))
				files = _parse_codebase(rec.get("output") or "")
				candidate = files.get("solution.py", "")
				if task is None or not candidate:
					n_skipped += 1
					record = {
						"name": rec.get("name"),
						"dag_id": rec.get("dag_id"),
						"parsed_ok": bool(candidate),
						"skipped": True,
						"summary": {},
						"results": {},
					}
					handle.write(json.dumps(record, separators=(",", ":"), default=str) + "\n")
					continue

				reference = task.record["solution"]
				results, summary = _score_source(
					candidate, reference, num_tests, seed + task.index, timeout_seconds, max_failures,
				)
				for kind, result in results.items():
					totals[kind][result["type"]] += 1
				n_scored += 1
				record = {
					"name": task.name,
					"dag_id": task.dag_id,
					"parsed_ok": True,
					"summary": summary,
					"results": results,
				}
				handle.write(json.dumps(record, separators=(",", ":"), default=str) + "\n")

		by_kind: dict[str, dict[str, int | float]] = {}
		for kind, counts in totals.items():
			by_kind[kind] = _with_pass_rate(counts)
		meta = {
			"run_name": run_name,
			"model": model,
			"responses_path": response_path.as_posix(),
			"n_records": n_records,
			"n_scored": n_scored,
			"n_skipped": n_skipped,
			"by_kind": by_kind,
		}
		output_path.with_suffix(".meta.json").write_text(json.dumps(meta, separators=(",", ":"), default=str))
		out[model] = meta

	return out


def print_table(scores: dict[str, dict[str, Any]], models: list[str]) -> None:
	"""Print pass rates for each model and scoring check."""
	kinds = sorted({kind for summary in scores.values() for kind in summary.get("by_kind", {})})
	for kind in kinds:
		print(f"\n=== Pass rate: {kind} ===")
		for model in models:
			summary = scores.get(model)
			if not summary or kind not in summary.get("by_kind", {}):
				print(f"{model}: -")
				continue
			counts = summary["by_kind"][kind]
			print(f"{model}: {counts['pass_rate']:.3f} (n={summary.get('n_scored', 0)})")


def main() -> None:
	"""Parse command-line arguments and score the requested run."""
	data_root = Path(__file__).resolve().parents[3] / "local_data"
	parser = argparse.ArgumentParser(description="Score Merge Code responses.")
	parser.add_argument("--tasks-root", type=Path, default=data_root / "tasks")
	parser.add_argument("--responses-dir", type=Path, default=data_root / "responses")
	parser.add_argument("--output-dir", type=Path, default=data_root / "results")
	parser.add_argument("--run-name", required=True)
	parser.add_argument("--models", nargs="+", required=True, help="Model path stems under responses/run, e.g. copilot/claude-opus-4.7")
	parser.add_argument("--overwrite", action="store_true")
	parser.add_argument("-y", "--yes", action="store_true")
	parser.add_argument("--limit", type=int, default=None)
	parser.add_argument("--num-tests", type=int, default=20)
	parser.add_argument("--seed", type=int, default=42)
	parser.add_argument("--timeout-seconds", type=int, default=5)
	parser.add_argument("--max-failures", type=int, default=5)
	args = parser.parse_args()

	scores = score_run(
		tasks_root=args.tasks_root,
		responses_dir=args.responses_dir,
		output_dir=args.output_dir,
		run_name=args.run_name,
		models=args.models,
		overwrite=args.overwrite,
		yes=args.yes,
		limit=args.limit,
		num_tests=args.num_tests,
		seed=args.seed,
		timeout_seconds=args.timeout_seconds,
		max_failures=args.max_failures,
	)
	print_table(scores, args.models)


if __name__ == "__main__":
	main()

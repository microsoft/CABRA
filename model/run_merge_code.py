from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tqdm import tqdm

from model.agents import AgentFactory, AgentKind, Codebase
from model.response_cache import ResponseCache


_HERE = Path(__file__).resolve().parent
DEFAULT_TASKS_ROOT = _HERE / "local_data" / "tasks"
DEFAULT_RESPONSE_DIR = _HERE / "local_data" / "responses"
DEFAULT_PROMPT_FILE = _HERE / "prompt.txt"
SOLUTION_FILENAME = "solution.py"
MAX_CONSECUTIVE_FAILURES = 5


@dataclass(frozen=True)
class MergeCodeTask:
	run_name: str
	index: int
	record: dict[str, Any]

	@property
	def name(self) -> str:
		return f"{self.run_name}/{self.index:05d}"

	@property
	def dag_id(self) -> str:
		return f"task_{self.index:05d}"


def _parse_kwargs(pairs: list[str]) -> dict[str, str]:
	out = {}
	for pair in pairs or []:
		if "=" not in pair:
			raise ValueError(f"--agent-kwargs entries must be key=value, got: {pair}")
		key, value = pair.split("=", 1)
		out[key] = value
	return out


def _task_codebase(task: MergeCodeTask, input_field: str) -> Codebase:
	try:
		source = task.record[input_field]
	except KeyError as exc:
		raise KeyError(f"task {task.name} has no input field {input_field!r}") from exc
	return {SOLUTION_FILENAME: source}


def _load_run(tasks_root: Path, run_name: str) -> list[MergeCodeTask]:
	path = tasks_root / f"{run_name}.json"
	if not path.exists():
		raise FileNotFoundError(f"run {run_name!r} does not exist at {path}")

	with path.open("r") as handle:
		records = json.load(handle)
	if not isinstance(records, list):
		raise ValueError(f"{path} must contain a JSON list of task records")

	tasks = []
	for index, record in enumerate(records):
		if not isinstance(record, dict):
			raise ValueError(f"{path} record {index} is not a JSON object")
		tasks.append(MergeCodeTask(run_name=run_name, index=index, record=record))
	return tasks


def _response_path(response_dir: Path, run_name: str, agent_name: str) -> Path:
	return response_dir / run_name / f"{agent_name}.jsonl"


async def run_eval(
	tasks_root: Path,
	run_names: list[str],
	agent_kind: AgentKind,
	agent_kwargs: dict[str, Any],
	response_dir: Path,
	prompt_file: Path,
	input_field: str = "input",
	limit: int | None = None,
	n_parallel: int = 1,
	overwrite: bool = False,
	yes: bool = False,
	retry_errors: bool = False,
	dry_run: bool = False,
) -> None:
	prompt = prompt_file.read_text()
	agent = AgentFactory.create(agent_kind, **agent_kwargs)

	if overwrite:
		existing = [
			_response_path(response_dir, run_name, agent.name)
			for run_name in run_names
		]
		existing = [path for path in existing if path.exists()]
		if existing:
			print(f"Overwrite will delete {len(existing)} existing result file(s):")
			for path in existing:
				print(f"  {path}")
			if not yes:
				response = input("Proceed? [y/N]: ")
				if response.lower() != "y":
					print("Aborting.")
					return
			for path in existing:
				path.unlink()

	pending: list[tuple[MergeCodeTask, ResponseCache]] = []
	loaded = 0
	for run_name in run_names:
		cache = ResponseCache(_response_path(response_dir, run_name, agent.name))
		cache.load(retry_errors=retry_errors)
		count = 0
		for task in _load_run(tasks_root, run_name):
			if limit is not None and count >= limit:
				break
			count += 1
			loaded += 1
			if cache.should_skip(task.name, task.dag_id):
				continue
			pending.append((task, cache))

	if dry_run:
		print(
			f"[dry-run] loaded {loaded} task(s), {len(pending)} pending, "
			f"prompt={prompt_file}, input_field={input_field}, agent={agent.name}"
		)
		return

	if not pending:
		print("[done] nothing to run")
		return

	semaphore = asyncio.Semaphore(n_parallel)
	write_lock = asyncio.Lock()
	failures = 0
	consecutive_failures = 0
	abort = False
	pbar = tqdm(total=len(pending), desc=f"running ({len(pending)} tasks)")

	async def run_task(task: MergeCodeTask, cache: ResponseCache) -> None:
		nonlocal failures, consecutive_failures, abort
		if abort:
			return
		async with semaphore:
			if abort:
				return
			await asyncio.sleep(random.uniform(0, 5))
			task_id = task.name
			started_at = time.monotonic()
			latest_status_metadata: dict[str, Any] = {}

			async def on_agent_status(metadata: dict[str, Any]) -> None:
				nonlocal latest_status_metadata
				status_metadata = {
					**metadata,
					"time_seconds": round(time.monotonic() - started_at, 3),
					"run_name": task.run_name,
					"task_index": task.index,
					"input_field": input_field,
				}
				latest_status_metadata = status_metadata
				async with write_lock:
					cache.append({
						"name": task.name,
						"dag_id": task.dag_id,
						"status": status_metadata.get("status", "running"),
						"output": None,
						"metadata": status_metadata,
					})

			try:
				result = await agent.run(
					prompt=prompt,
					codebase=_task_codebase(task, input_field),
					task_id=task_id,
					status_callback=on_agent_status,
				)
				elapsed = round(time.monotonic() - started_at, 3)
				result.metadata["time_seconds"] = elapsed
				result.metadata["run_name"] = task.run_name
				result.metadata["task_index"] = task.index
				result.metadata["input_field"] = input_field
				result.metadata["status"] = "completed"
				async with write_lock:
					cache.append({
						"name": task.name,
						"dag_id": task.dag_id,
						"status": "completed",
						"output": result.output,
						"metadata": result.metadata,
					})
				consecutive_failures = 0
			except Exception as exc:
				elapsed = round(time.monotonic() - started_at, 3)
				print(f"\n[error] {task_id}: {exc}")
				error_metadata = {
					**latest_status_metadata,
					"status": "error",
					"time_seconds": elapsed,
					"run_name": task.run_name,
					"task_index": task.index,
					"input_field": input_field,
				}
				async with write_lock:
					cache.append({
						"name": task.name,
						"dag_id": task.dag_id,
						"status": "error",
						"output": None,
						"error": str(exc),
						"metadata": error_metadata,
					})
				failures += 1
				consecutive_failures += 1
				if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
					print(f"\n[abort] {MAX_CONSECUTIVE_FAILURES} consecutive failures; stopping")
					abort = True
			pbar.update(1)

	await asyncio.gather(*[run_task(task, cache) for task, cache in pending])
	pbar.close()

	status = f"{pbar.n}/{len(pending)} tasks completed"
	if failures:
		raise RuntimeError(f"{status}, {failures} failed")
	print(f"[done] {status}")


def main() -> None:
	parser = argparse.ArgumentParser(
		description="Run agents on Merge Code task JSON files."
	)
	parser.add_argument(
		"--tasks-root",
		type=Path,
		default=DEFAULT_TASKS_ROOT,
		help="Directory containing per-run JSON files, e.g. testing.json.",
	)
	parser.add_argument(
		"--run-names",
		nargs="+",
		required=True,
		help="One or more run names; each maps to tasks_root/<run_name>.json.",
	)
	parser.add_argument("--agent", type=AgentKind, default=AgentKind.LLM)
	parser.add_argument("--model-name", help="LiteLLM provider/model ID or Copilot model name; defaults to the backend's model.")
	parser.add_argument(
		"--agent-kwargs",
		nargs="*",
		default=[],
		help="Extra agent kwargs as key=value (strings only).",
	)
	parser.add_argument("--response-dir", type=Path, default=DEFAULT_RESPONSE_DIR)
	parser.add_argument(
		"--prompt-file",
		type=Path,
		default=DEFAULT_PROMPT_FILE,
		help="Prompt text to use for every task.",
	)
	parser.add_argument(
		"--input-field",
		default="input",
		choices=("input", "input_with_space"),
		help="Task JSON source field to present as solution.py.",
	)
	parser.add_argument("--limit", type=int, default=None)
	parser.add_argument(
		"--n-parallel",
		type=int,
		default=1,
		help="Number of tasks to run concurrently across all run names.",
	)
	parser.add_argument(
		"--overwrite",
		action="store_true",
		help="Delete existing result files before running (prompts for confirmation).",
	)
	parser.add_argument(
		"-y",
		"--yes",
		action="store_true",
		help="Skip confirmation prompts.",
	)
	parser.add_argument(
		"--retry-errors",
		action="store_true",
		help="Re-run tasks that previously failed (output=null in cache).",
	)
	parser.add_argument(
		"--dry-run",
		action="store_true",
		help="Load tasks and report pending work without calling the agent.",
	)
	args = parser.parse_args()

	agent_kwargs = _parse_kwargs(args.agent_kwargs)
	if args.model_name is not None:
		agent_kwargs.setdefault("model_name", args.model_name)
	asyncio.run(run_eval(
		tasks_root=args.tasks_root,
		run_names=args.run_names,
		agent_kind=args.agent,
		agent_kwargs=agent_kwargs,
		response_dir=args.response_dir,
		prompt_file=args.prompt_file,
		input_field=args.input_field,
		limit=args.limit,
		n_parallel=args.n_parallel,
		overwrite=args.overwrite,
		yes=args.yes,
		retry_errors=args.retry_errors,
		dry_run=args.dry_run,
	))


if __name__ == "__main__":
	main()

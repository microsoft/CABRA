import argparse
import json
import os

from tqdm import tqdm

from data.tasks.task_loader import TaskLoader
from data.tasks.task import TaskType
from data.utils.program_params import ProgramParams


def _find_dag_files(input_path: str) -> list[tuple[str, str]]:
	"""Return list of (dag_id, dag_json_path) pairs."""
	dag_files: list[tuple[str, str]] = []

	direct_dag = os.path.join(input_path, "dag.json")
	if os.path.isfile(direct_dag):
		dag_id = os.path.basename(os.path.normpath(input_path))
		dag_files.append((dag_id, direct_dag))
		return dag_files

	if not os.path.isdir(input_path):
		raise FileNotFoundError(f"Input path does not exist or is not a directory: {input_path}")

	for entry in sorted(os.listdir(input_path)):
		dag_dir = os.path.join(input_path, entry)
		dag_file = os.path.join(dag_dir, "dag.json")
		if os.path.isdir(dag_dir) and os.path.isfile(dag_file):
			dag_files.append((entry, dag_file))

	return dag_files


def tasks_from_dag(input_path: str, output_dir: str, run_name: str, task_set_names: list[str], seed: int, program_params: ProgramParams = None, skip_task_types: list[str] | None = None, yes: bool = False, input_run_name: str | None = None) -> list[str]:
	"""Generate tasks from DAG JSON files; save one JSON per task type per task set.

	``input_run_name`` (defaults to ``run_name``) selects which DAG subdirectory
	to read; this lets a single DAG bucket feed many output runs with different
	``program_params`` (e.g. for constraint sweeps).

	Returns:
		List of absolute paths to the directories that received task JSON files.
	"""
	if program_params is None:
		program_params = ProgramParams()

	skip = {TaskType(t) for t in (skip_task_types or [])}

	dag_input_name = input_run_name or run_name
	dag_files = _find_dag_files(input_path + "/" + dag_input_name)
	if not dag_files:
		raise ValueError(f"No dag.json files found under: {input_path}/{dag_input_name}")

	run_save_path = os.path.join(output_dir, run_name)
	if os.path.exists(run_save_path):
		if not yes:
			response = input(f"Run '{run_name}' already exists at {run_save_path}. Overwrite? [y/N]: ")
			if response.lower() != "y":
				print("Aborting.")
				return []
		for set_name in task_set_names:
			set_dir = os.path.join(run_save_path, set_name)
			if not os.path.isdir(set_dir):
				continue
			for fname in os.listdir(set_dir):
				if not fname.endswith(".json"):
					continue
				try:
					tt = TaskType(fname[: -len(".json")])
				except ValueError:
					continue
				if tt not in skip:
					os.remove(os.path.join(set_dir, fname))

	output_dirs: list[str] = []
	for set_name in task_set_names:
		task_set_cls = TaskLoader.load_task_set(set_name)
		merged_tasks: dict = {}
		for dag_id, dag_file in tqdm(dag_files, desc=f"generating tasks [{run_name}/{set_name}]"):
			with open(dag_file, "r") as f:
				dag_data = json.load(f)
			sub_set = task_set_cls.from_dag(dag_id=dag_id, dag_data=dag_data, seed=seed, program_params=program_params)
			for task_type, task in sub_set.tasks.items():
				if task_type not in skip:
					merged_tasks[(dag_id, task_type)] = task

		task_set = task_set_cls(tasks=merged_tasks)
		save_subdir = os.path.join(output_dir, run_name, set_name)
		task_set.save(save_subdir, skip_task_types=skip)
		output_dirs.append(os.path.abspath(save_subdir))

	return output_dirs


def _task_set_names(constraints: bool, program_params: ProgramParams) -> list[str]:
	if constraints:
		if program_params.max_num_constraints > 0:
			return ["math_mult_constraints", "string_constraints", "array_constraints"]
		return ["math_function", "string_function", "array_function"]
	return [
		"math_function",
		"string_function",
		"array_function",
	]


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Create tasks from generated DAGs.")
	parser.add_argument(
		"--input_path",
		type=str,
		required=True,
		help="Path containing DAG folders with dag.json, or a single DAG folder.",
	)
	parser.add_argument(
		"--output_dir",
		type=str,
		required=True,
		help="Directory where output JSON will be written.",
	)
	parser.add_argument(
		"--run_name",
		type=str,
		required=True,
		help="Output filename prefix (writes {run_name}.json).",
	)
	parser.add_argument(
		"--seed",
		type=int,
		required=False,
		help="Random seed for reproducibility.",
	)
	parser.add_argument(
		"--skip-task-types", nargs="*", default=[],
		help="Task types to skip (preserve existing files, e.g. cache_function extract_helper).")
	parser.add_argument(
		"--program-args", nargs="*", default=[],
		help="Program generation args as key=value (e.g. multi_line=true)")
	parser.add_argument(
		"--constraints",
		action="store_true",
		help="Generate mult-constraints tasks instead of function tasks.",
	)
	parser.add_argument(
		"--input_run_name",
		type=str,
		default=None,
		help="Run name to read DAGs from (defaults to --run_name). Use this to "
			"share one DAG bucket across many task runs that vary only in "
			"--program-args (e.g. constraint sweeps).",
	)
	parser.add_argument(
		"-y", "--yes",
		action="store_true",
		help="Skip confirmation prompts.",
	)
	return parser.parse_args()


def main() -> None:
	args = parse_args()
	program_params = ProgramParams.from_kwargs(args.program_args)
	task_set_names = _task_set_names(args.constraints, program_params)
	output_dirs = tasks_from_dag(
		input_path=args.input_path,
		output_dir=args.output_dir,
		run_name=args.run_name,
		task_set_names=task_set_names,
		seed=args.seed,
		skip_task_types=args.skip_task_types,
		program_params=program_params,
		yes=args.yes,
		input_run_name=args.input_run_name,
	)
	for d in output_dirs:
		print(f"Wrote tasks to: {d}")


if __name__ == "__main__":
	main()

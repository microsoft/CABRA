"""Generate test cases for tasks previously produced by dag_to_tasks.py."""

import argparse
import os

from tqdm import tqdm

from data.tasks.task_loader import TaskLoader
from data.tasks.task import TaskType
from data.tasks.task_test_cases import TaskTestCases, TaskTestCaseSet
from data.utils.program_params import ProgramParams


def generate_test_cases(
	tasks_dir: str,
	output_dir: str,
	run_name: str,
	task_set_names: list[str],
	skip_task_types: list[str] | None = None,
	yes: bool = False,
) -> list[str]:
	"""For each task set, load tasks and generate a fresh TaskTestCaseSet.

	Returns list of absolute output directory paths written.
	"""
	skip = {TaskType(t) for t in (skip_task_types or [])}

	output_dirs: list[str] = []
	for set_name in task_set_names:
		task_set_cls = TaskLoader.load_task_set(set_name)
		load_subdir = os.path.join(tasks_dir, run_name, set_name)
		if not os.path.isdir(load_subdir):
			raise FileNotFoundError(f"Tasks dir not found: {load_subdir}")

		task_set = task_set_cls.load_dir(load_subdir)

		save_subdir = os.path.join(output_dir, run_name, set_name)
		if os.path.exists(save_subdir):
			if not yes:
				response = input(
					f"Test cases for run '{run_name}' already exist at {save_subdir}. Overwrite? [y/N]: "
				)
				if response.lower() != "y":
					print(f"Skipping {set_name}.")
					continue
			for fname in os.listdir(save_subdir):
				if not fname.endswith(".json"):
					continue
				try:
					tt = TaskType(fname[: -len(".json")])
				except ValueError:
					continue
				if tt not in skip:
					os.remove(os.path.join(save_subdir, fname))

		os.makedirs(save_subdir, exist_ok=True)
		items: dict = {}
		for (dag_id, task_type), task in tqdm(task_set.tasks.items(), desc=f"generating test cases [{run_name}/{set_name}]"):
			if task_type in skip:
				continue
			suite = task.generate_test_cases()
			items[(dag_id, task_type)] = TaskTestCases(
				dag_id=dag_id,
				task_type=task_type,
				suite=suite,
			)

		ttc_set = TaskTestCaseSet(items=items)
		ttc_set.save(save_subdir)
		output_dirs.append(os.path.abspath(save_subdir))

	return output_dirs


def _task_set_names(repository: bool, constraints: bool, program_params: ProgramParams) -> list[str]:
	if repository:
		return ["repository"]
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
	parser = argparse.ArgumentParser(description="Generate test cases for previously generated tasks.")
	parser.add_argument(
		"--tasks_dir",
		type=str,
		required=True,
		help="Root containing <run_name>/<set_name>/{task_type}.json (output of dag_to_tasks.py).",
	)
	parser.add_argument(
		"--output_dir",
		type=str,
		required=True,
		help="Root where parallel test case files will be written.",
	)
	parser.add_argument(
		"--run_name",
		type=str,
		required=True,
		help="Run name (subdirectory under tasks_dir and output_dir).",
	)
	parser.add_argument(
		"--skip-task-types", nargs="*", default=[],
		help="Task types to skip (preserve existing files, e.g. cache_function extract_helper).")
	parser.add_argument(
		"--program-args", nargs="*", default=[],
		help="Program generation args as key=value; used to match task-set selection.")
	parser.add_argument(
		"--repository",
		action="store_true",
		help="Generate test cases for repository tasks instead of function tasks.",
	)
	parser.add_argument(
		"--constraints",
		action="store_true",
		help="Generate test cases for mult-constraints tasks instead of function tasks.",
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
	task_set_names = _task_set_names(args.repository, args.constraints, program_params)
	output_dirs = generate_test_cases(
		tasks_dir=args.tasks_dir,
		output_dir=args.output_dir,
		run_name=args.run_name,
		task_set_names=task_set_names,
		skip_task_types=args.skip_task_types,
		yes=args.yes,
	)
	for d in output_dirs:
		print(f"Wrote test cases to: {d}")


if __name__ == "__main__":
	main()

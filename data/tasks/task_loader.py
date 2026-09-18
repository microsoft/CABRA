"""Loads tasks for evaluation, optionally joining with test cases."""

from typing import Iterable, Iterator
from tqdm import tqdm

from data.tasks import TaskSet
from data.tasks.function import (
    MathFunctionTaskSet,
    StringFunctionTaskSet,
    ArrayFunctionTaskSet,
)
from data.tasks.constraints.array_function import ArrayConstraintsTaskSet
from data.tasks.constraints.math_function import MathMultConstraintsTaskSet
from data.tasks.constraints.string_function import StringConstraintsTaskSet
from data.tasks.task import Task, TaskType
from data.tasks.task_test_cases import TaskTestCaseSet

TASK_SETS = [
    MathFunctionTaskSet,
    StringFunctionTaskSet,
    ArrayFunctionTaskSet,
    MathMultConstraintsTaskSet,
    StringConstraintsTaskSet,
    ArrayConstraintsTaskSet,
]
TASK_SET_REGISTRY = {
    ts.TASK_SET_NAME: ts for ts in TASK_SETS
}

class TaskLoader:
    @staticmethod
    def load_task_set(task_set_name: str) -> type[TaskSet]:
        try:
            return TASK_SET_REGISTRY[task_set_name]
        except KeyError as exc:
            supported = ", ".join(sorted(TASK_SET_REGISTRY))
            raise ValueError(
                f"Unknown task_set_name '{task_set_name}'. Supported: {supported}"
            ) from exc

    @staticmethod
    def load_tasks_with_test_cases(
        tasks_dir: str,
        test_cases_dir: str,
        task_set_name: str,
        task_types: Iterable[TaskType] | None = None,
    ) -> TaskSet:
        """Load a TaskSet and attach test cases by joining on (dag_id, task_type)."""
        task_set_cls = TaskLoader.load_task_set(task_set_name)
        task_set = task_set_cls.load_dir(tasks_dir)
        ttc_set = TaskTestCaseSet.load_dir(test_cases_dir)
        wanted = set(task_types) if task_types is not None else None
        for key in list(task_set.tasks):
            if wanted is not None and key[1] not in wanted:
                del task_set.tasks[key]
                continue
            ttc = ttc_set.items.get(key)
            if ttc is not None:
                task_set.tasks[key].test_cases = ttc.suite
        return task_set

    @staticmethod
    def eval_task_inputs(
        task_json_path: str,
        task_set_name: str,
        task_types: Iterable[TaskType] | None = None,
        task_type_index: int | None = None,
        total_task_types: int | None = None,
        show_progress: bool = True,
    ) -> Iterator[tuple[TaskType, Task]]:
        import json
        from pathlib import Path

        task_set_cls = TaskLoader.load_task_set(task_set_name)
        task_type = TaskType(Path(task_json_path).stem)
        wanted = set(task_types) if task_types is not None else None
        if wanted is not None and task_type not in wanted:
            return
        task_cls = task_set_cls.TASK_CLASSES[task_type]
        with open(task_json_path, "r") as f:
            records = json.load(f)
        desc = (
            f"[{task_type_index}/{total_task_types}] {task_type.value}"
            if task_type_index is not None and total_task_types is not None
            else task_type.value
        )
        iterator = tqdm(records, desc=desc) if show_progress else records
        for rec in iterator:
            yield task_type, task_cls.from_json(rec)

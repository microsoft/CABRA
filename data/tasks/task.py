"""Base class for our five Fowler's tasks"""

from abc import ABC, abstractmethod
import enum
from typing import List, Any, Callable, Optional

from data.utils.program_params import ProgramParams

class TaskType(enum.Enum):
    DEAD_CODE = 'dead_code'
    ADD_PARAMETER = 'add_parameter'
    ADD_RETURN_VALUE = 'add_return_value'
    CACHE_FUNCTION = 'cache_function'
    EXTRACT_HELPER = 'extract_helper'


class Task(ABC):
    """Abstract base class for tasks."""

    def __init__(
        self,
        dag_id: str,
        prompt: str,
        starter_code: str,
        solution_code: str,
        test_cases: Optional[Any] = None,
        metadata: Any = None,
        name: str = None,
    ):
        self._name = name if name is not None else self.TASK_TYPE
        self._dag_id = dag_id
        self._prompt = prompt
        self._starter_code = starter_code
        self._solution_code = solution_code
        self._test_cases = test_cases
        self._metadata = metadata if metadata is not None else {}

    @property
    def name(self) -> str:
        return self._name

    @property
    def dag_id(self) -> str:
        return self._dag_id

    @property
    def prompt(self) -> str:
        return self._prompt

    @property
    def starter_code(self) -> str:
        return self._starter_code

    @property
    def solution_code(self) -> str:
        return self._solution_code

    @property
    def test_cases(self) -> Optional[Any]:
        return self._test_cases

    @test_cases.setter
    def test_cases(self, value: Any) -> None:
        self._test_cases = value

    @property
    def metadata(self) -> Any:
        return self._metadata


    def validate(self) -> None:
        try:
            compile(self.starter_code, f"<{self.name}.starter>", "exec")
            compile(self.solution_code, f"<{self.name}.solution>", "exec")
        except SyntaxError as e:
            raise AssertionError(f"Invalid code for {self.name}: {e}") from e

    def _to_json(self) -> dict:
        return {
            "name": self.name,
            "dag_id": self.dag_id,
            "prompt": self.prompt,
            "starter_code": self.starter_code,
            "solution_code": self.solution_code,
            "metadata": self.metadata,
        }

    @classmethod
    def from_json(cls, data: dict) -> "Task":
        return cls(
            dag_id=data["dag_id"],
            prompt=data["prompt"],
            starter_code=data.get("starter_code", ""),
            solution_code=data.get("solution_code", ""),
            metadata=data.get("metadata", {}),
            name=data.get("name", ""),
        )

    @classmethod
    @abstractmethod
    def _from_dag(cls, dag_id: str, dag_data: dict, seed: int = None, program_params: ProgramParams = None) -> "Task":
        """Construct a task from a DAG payload."""
        pass

    @abstractmethod
    def generate_test_cases(self) -> Any:
        """Generate the TestCaseSuite for this task. Called by generate_test_cases.py, not at task construction time."""
        pass


class TaskSet:
    """A collection of tasks keyed by their TaskType, serializable to JSON."""

    TASK_SET_NAME: str = ""
    TASK_CLASSES: dict[TaskType, type[Task]] = {}

    def __init__(self, tasks: dict = None):
        """Initialize TaskSet with an optional dict of {task_type: Task}."""
        self.tasks = tasks if tasks is not None else {}

    @classmethod
    def from_dag(cls, dag_id: str, dag_data: dict, seed: int, program_params: ProgramParams = None) -> "TaskSet":
        """Build every task in TASK_CLASSES from a single DAG payload."""
        if program_params is None:
            program_params = ProgramParams()
        tasks = {}
        for task_type, task_cls in cls.TASK_CLASSES.items():
            task = task_cls._from_dag(dag_id=dag_id, dag_data=dag_data, seed=seed, program_params=program_params)
            if not task._name:
                task._name = f"{cls.TASK_SET_NAME}_{task_type.value}_{dag_id}"
            tasks[task_type] = task
        return cls(tasks=tasks)

    @classmethod
    def from_json(cls, data: List[dict], task_from_json: Callable[[dict], Task]) -> "TaskSet":
        """Deserialize task set from a list of dictionaries.

        Args:
            data: Serialized task records.
            task_from_json: Callable that converts one task dict into a Task.
        """
        return cls(tasks={item["task_type"]: task_from_json(item) for item in data})

    def save(self, save_dir: str, skip_task_types: set["TaskType"] | None = None) -> None:
        """Save one JSON file per TASK_CLASSES key under save_dir.

        Each file is named `{task_type.value}.json` and contains the JSON
        records of every task in `self.tasks` that is an instance of the
        corresponding task class.
        """
        import os
        import json

        os.makedirs(save_dir, exist_ok=True)
        for task_type, task_cls in self.TASK_CLASSES.items():
            if skip_task_types and task_type in skip_task_types:
                continue
            matching = []
            for task in self.tasks.values():
                if not isinstance(task, task_cls):
                    continue
                task.validate()
                matching.append(task._to_json())
            filepath = os.path.join(save_dir, f"{task_type.value}.json")
            with open(filepath, "w") as f:
                json.dump(matching, f, indent=2)

    @classmethod
    def load(cls, filepath: str, task_from_json: Callable[[dict], Task]) -> "TaskSet":
        """Load task set from a JSON file."""
        import json

        with open(filepath, "r") as f:
            data = json.load(f)

        return cls.from_json(data, task_from_json=task_from_json)

    @classmethod
    def load_dir(cls, load_dir: str) -> "TaskSet":
        """Load all {task_type}.json files in load_dir into a TaskSet keyed by (dag_id, task_type).

        Tasks are loaded without test cases. Use `attach_test_cases` to populate them.
        """
        import os
        import json

        tasks: dict = {}
        for task_type, task_cls in cls.TASK_CLASSES.items():
            filepath = os.path.join(load_dir, f"{task_type.value}.json")
            if not os.path.isfile(filepath):
                continue
            with open(filepath, "r") as f:
                records = json.load(f)
            for rec in records:
                task = task_cls.from_json(rec)
                tasks[(rec["dag_id"], task_type)] = task
        return cls(tasks=tasks)

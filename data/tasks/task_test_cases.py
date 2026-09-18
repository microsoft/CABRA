"""TaskTestCases: a regeneratable layer of test cases joined to tasks by dag_id."""

import json
import os
import uuid
from typing import Optional

from data.tasks.task import TaskType
from data.tasks.test_cases import TestCase, TestCaseSuite


class TaskTestCases:
    """Test cases for a single task, identified by (dag_id, task_type) and a fresh UUID per generation."""

    def __init__(
        self,
        dag_id: str,
        task_type: TaskType,
        suite: TestCaseSuite,
        test_case_uuid: Optional[str] = None,
        metadata: Optional[dict] = None,
    ):
        self.dag_id = dag_id
        self.task_type = task_type
        self.suite = suite
        self.test_case_uuid = test_case_uuid if test_case_uuid is not None else str(uuid.uuid4())
        self.metadata = metadata if metadata is not None else {}

    def to_dict(self) -> dict:
        return {
            "dag_id": self.dag_id,
            "task_type": self.task_type.value,
            "test_case_uuid": self.test_case_uuid,
            "test_cases": self.suite.to_dict(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TaskTestCases":
        suite = TestCaseSuite([TestCase.from_dict(tc) for tc in d["test_cases"]])
        return cls(
            dag_id=d["dag_id"],
            task_type=TaskType(d["task_type"]),
            suite=suite,
            test_case_uuid=d.get("test_case_uuid"),
            metadata=d.get("metadata", {}),
        )


class TaskTestCaseSet:
    """A collection of TaskTestCases, saved as one JSON file per task type."""

    def __init__(self, items: Optional[dict] = None):
        """items: dict keyed by (dag_id, TaskType) -> TaskTestCases."""
        self.items = items if items is not None else {}

    def save(self, save_dir: str) -> None:
        os.makedirs(save_dir, exist_ok=True)
        by_type: dict[TaskType, list] = {}
        for (_, task_type), ttc in self.items.items():
            by_type.setdefault(task_type, []).append(ttc.to_dict())
        for task_type, records in by_type.items():
            filepath = os.path.join(save_dir, f"{task_type.value}.json")
            with open(filepath, "w") as f:
                json.dump(records, f, indent=2)

    @classmethod
    def load_dir(cls, load_dir: str) -> "TaskTestCaseSet":
        items: dict = {}
        if not os.path.isdir(load_dir):
            return cls(items=items)
        for fname in os.listdir(load_dir):
            if not fname.endswith(".json"):
                continue
            filepath = os.path.join(load_dir, fname)
            with open(filepath, "r") as f:
                records = json.load(f)
            for rec in records:
                ttc = TaskTestCases.from_dict(rec)
                items[(ttc.dag_id, ttc.task_type)] = ttc
        return cls(items=items)

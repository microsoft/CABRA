"""Array-domain constraints task: concrete subclasses + TaskSet."""

from data.tasks.task import TaskType
from data.tasks import TaskSet
from data.tasks.constraints.base_function import (
    BaseCacheFunctionConstraintsTask,
    BaseExtractHelperConstraintsTask,
    BaseMultConstraintsTask,
    BaseReturnValueConstraintsTask,
)
from data.tasks.problem_statements.constraint_prompts import (
    PROMPT_ARRAY_CACHE_FUNCTION_CONSTRAINTS,
    PROMPT_ARRAY_EXTRACT_HELPER_CONSTRAINTS,
    PROMPT_ARRAY_MULT_CONSTRAINTS,
    PROMPT_ARRAY_RETURN_VALUE_CONSTRAINTS,
)

external_returns = ["'100'", "'200'", "'300'", "'400'", "'500'"]
default_returns = [0.21, -0.42, 0.63, -0.84, 1.02]
multiplier_returns = [
    '1.0 if float(np.sum(x)) > 0 else -1.0',
    '0.5',
    'float(np.std(x))',
    'float(min(np.min(x), 0.21))',
    'float(np.mean(x)) + 0.01',
]
slow_returns = default_returns

PREFIX_BLOCKS = []
for ext in external_returns:
    for def_ret in default_returns:
        for mult in multiplier_returns:
            for slow in slow_returns:
                PREFIX_BLOCKS.append(f"""
import math
import numpy as np
import operator

def external(num_keys: int) -> tuple[str, ...]:
    return tuple([{ext} + str(i) for i in range(num_keys)])

def default(idx: int = 0) -> float:
    return {def_ret} + 0.024 * idx

def get_multiplier(x: np.ndarray, idx: int = 0) -> float:
    return ({mult}) + 0.031 * idx

def slow(idx: int = 0) -> float:
    return ({slow}) + 0.017 * idx
""".strip())


class ArrayConstraintsAddParameter(BaseMultConstraintsTask):
    PREFIX_BLOCKS = PREFIX_BLOCKS
    TASK_TYPE_NAME = "array"
    PROMPT_TEMPLATE = PROMPT_ARRAY_MULT_CONSTRAINTS


class ArrayConstraintsAddReturnValue(BaseReturnValueConstraintsTask):
    PREFIX_BLOCKS = PREFIX_BLOCKS
    TASK_TYPE_NAME = "array"
    PROMPT_TEMPLATE = PROMPT_ARRAY_RETURN_VALUE_CONSTRAINTS


class ArrayConstraintsCacheFunction(BaseCacheFunctionConstraintsTask):
    PREFIX_BLOCKS = PREFIX_BLOCKS
    TASK_TYPE_NAME = "array"
    PROMPT_TEMPLATE = PROMPT_ARRAY_CACHE_FUNCTION_CONSTRAINTS


class ArrayConstraintsExtractHelper(BaseExtractHelperConstraintsTask):
    PREFIX_BLOCKS = PREFIX_BLOCKS
    TASK_TYPE_NAME = "array"
    PROMPT_TEMPLATE = PROMPT_ARRAY_EXTRACT_HELPER_CONSTRAINTS


class ArrayConstraintsTaskSet(TaskSet):
    """Builds the array constraints task from a single DAG."""

    TASK_CLASSES: dict[TaskType, type] = {
        TaskType.ADD_PARAMETER: ArrayConstraintsAddParameter,
        TaskType.ADD_RETURN_VALUE: ArrayConstraintsAddReturnValue,
        TaskType.CACHE_FUNCTION: ArrayConstraintsCacheFunction,
        TaskType.EXTRACT_HELPER: ArrayConstraintsExtractHelper,
    }
    TASK_SET_NAME = "array_constraints"

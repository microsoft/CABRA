from data.tasks.task import TaskType
from data.tasks import TaskSet
from data.tasks.function.base_function import (
    FunctionTaskType,
    BaseFunctionTaskDeadCode,
    BaseFunctionTaskAddParameter,
    BaseFunctionTaskAddReturnValue,
    BaseFunctionTaskCacheFunction,
    BaseFunctionTaskExtractHelper,
)
from data.tasks.problem_statements import base_prompts as prompts
from data.tasks.problem_statements import runtime_prompts as prompts_runtime_simple


DEAD_CODE_PROMPTS = {
    "none": prompts.PROMPT_DEAD_CODE_ARRAY,
    "runtime_simple": prompts_runtime_simple.PROMPT_DEAD_CODE_ARRAY,
}
ADD_PARAMETER_PROMPTS = {
    "none": prompts.PROMPT_ADD_PARAMETER_ARRAY,
    "runtime_simple": prompts_runtime_simple.PROMPT_ADD_PARAMETER_ARRAY,
}
ADD_RETURN_VALUE_PROMPTS = {
    "none": prompts.PROMPT_ADD_RETURN_VALUE_ARRAY,
    "runtime_simple": prompts_runtime_simple.PROMPT_ADD_RETURN_VALUE_ARRAY,
}
CACHE_FUNCTION_PROMPTS = {
    "none": prompts.PROMPT_CACHE_FUNCTION_DIAMOND_ARRAY,
    "runtime_simple": prompts_runtime_simple.PROMPT_CACHE_FUNCTION_DIAMOND_ARRAY,
}
EXTRACT_HELPER_PROMPTS = {
    "none": prompts.PROMPT_EXTRACT_HELPER_DIAMOND_ARRAY,
    "runtime_simple": prompts_runtime_simple.PROMPT_EXTRACT_HELPER_DIAMOND_ARRAY,
}

external_returns = ["(x, 'cabra')", "(x, 'goat')", "(x, 'chevre')", "(x, 'capra')", "(x, 'geit')"]
default_returns = [0.21, -0.42, 0.63, -0.84, 1.02]
multiplier_returns = ['1.0 if float(np.sum(x)) > 0 else -1.0', '0.5', 'float(np.std(x))', 'float(min(np.min(x), 0.21))', 'float(np.mean(x)) + 0.01']
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

def external(x: np.ndarray) -> tuple[np.ndarray, str]:
    return {ext}

def default() -> float:
    return {def_ret}

def get_multiplier(x: np.ndarray) -> float:
    return {mult}

def slow() -> float:
    return {slow}
""".strip())

class ArrayFunctionTaskDeadCode(BaseFunctionTaskDeadCode):
    FUNCTION_TASK_TYPE = FunctionTaskType.ARRAY
    PREFIX_BLOCKS = PREFIX_BLOCKS
    PROMPTS = DEAD_CODE_PROMPTS


class ArrayFunctionTaskAddParameter(BaseFunctionTaskAddParameter):
    FUNCTION_TASK_TYPE = FunctionTaskType.ARRAY
    PREFIX_BLOCKS = PREFIX_BLOCKS
    PROMPTS = ADD_PARAMETER_PROMPTS


class ArrayFunctionTaskAddReturnValue(BaseFunctionTaskAddReturnValue):
    FUNCTION_TASK_TYPE = FunctionTaskType.ARRAY
    PREFIX_BLOCKS = PREFIX_BLOCKS
    PROMPTS = ADD_RETURN_VALUE_PROMPTS


class ArrayFunctionTaskCacheFunction(BaseFunctionTaskCacheFunction):
    FUNCTION_TASK_TYPE = FunctionTaskType.ARRAY
    PREFIX_BLOCKS = PREFIX_BLOCKS
    PROMPTS = CACHE_FUNCTION_PROMPTS


class ArrayFunctionTaskExtractHelper(BaseFunctionTaskExtractHelper):
    FUNCTION_TASK_TYPE = FunctionTaskType.ARRAY
    PREFIX_BLOCKS = PREFIX_BLOCKS
    PROMPTS = EXTRACT_HELPER_PROMPTS


class ArrayFunctionTaskSet(TaskSet):
    """A TaskSet that builds all five array-function task variants from a single DAG."""

    TASK_CLASSES: dict[TaskType, type] = {
        TaskType.DEAD_CODE: ArrayFunctionTaskDeadCode,
        TaskType.ADD_PARAMETER: ArrayFunctionTaskAddParameter,
        TaskType.ADD_RETURN_VALUE: ArrayFunctionTaskAddReturnValue,
        TaskType.CACHE_FUNCTION: ArrayFunctionTaskCacheFunction,
        TaskType.EXTRACT_HELPER: ArrayFunctionTaskExtractHelper,
    }
    TASK_SET_NAME = "array_function"

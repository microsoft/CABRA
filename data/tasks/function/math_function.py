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
    "none": prompts.PROMPT_DEAD_CODE,
    "runtime_simple": prompts_runtime_simple.PROMPT_DEAD_CODE,
}
ADD_PARAMETER_PROMPTS = {
    "none": prompts.PROMPT_ADD_PARAMETER,
    "runtime_simple": prompts_runtime_simple.PROMPT_ADD_PARAMETER,
}
ADD_RETURN_VALUE_PROMPTS = {
    "none": prompts.PROMPT_ADD_RETURN_VALUE,
    "runtime_simple": prompts_runtime_simple.PROMPT_ADD_RETURN_VALUE,
}
CACHE_FUNCTION_PROMPTS = {
    "none": prompts.PROMPT_CACHE_FUNCTION_DIAMOND,
    "runtime_simple": prompts_runtime_simple.PROMPT_CACHE_FUNCTION_DIAMOND,
}
EXTRACT_HELPER_PROMPTS = {
    "none": prompts.PROMPT_EXTRACT_HELPER_DIAMOND,
    "runtime_simple": prompts_runtime_simple.PROMPT_EXTRACT_HELPER_DIAMOND,
}

external_returns = ["(x, 'cabra')", "(x, 'goat')", "(x, 'chevre')", "(x, 'capra')", "(x, 'geit')"]
default_returns = [0.21, -0.42, 0.63, -0.84, 1.02]
multiplier_returns = ['1.0 if x > 0 else -1.0', '0.5', 'x', 'min(x, 0.21)', 'x + 0.01']
slow_returns = default_returns

PREFIX_BLOCKS = []
for ext in external_returns:
    for def_ret in default_returns:
        for mult in multiplier_returns:
            for slow in slow_returns:
                PREFIX_BLOCKS.append(f"""
import math
import operator

def external(x: float) -> tuple[float, str]:
    return {ext}

def default() -> float:
    return {def_ret}

def get_multiplier(x: float) -> float:
    return {mult}

def slow() -> float:
    return {slow}
""".strip())


class MathFunctionTaskDeadCode(BaseFunctionTaskDeadCode):
    FUNCTION_TASK_TYPE = FunctionTaskType.MATH
    PREFIX_BLOCKS = PREFIX_BLOCKS
    PROMPTS = DEAD_CODE_PROMPTS


class MathFunctionTaskAddParameter(BaseFunctionTaskAddParameter):
    FUNCTION_TASK_TYPE = FunctionTaskType.MATH
    PREFIX_BLOCKS = PREFIX_BLOCKS
    PROMPTS = ADD_PARAMETER_PROMPTS


class MathFunctionTaskAddReturnValue(BaseFunctionTaskAddReturnValue):
    FUNCTION_TASK_TYPE = FunctionTaskType.MATH
    PREFIX_BLOCKS = PREFIX_BLOCKS
    PROMPTS = ADD_RETURN_VALUE_PROMPTS


class MathFunctionTaskCacheFunction(BaseFunctionTaskCacheFunction):
    FUNCTION_TASK_TYPE = FunctionTaskType.MATH
    PREFIX_BLOCKS = PREFIX_BLOCKS
    PROMPTS = CACHE_FUNCTION_PROMPTS


class MathFunctionTaskExtractHelper(BaseFunctionTaskExtractHelper):
    FUNCTION_TASK_TYPE = FunctionTaskType.MATH
    PREFIX_BLOCKS = PREFIX_BLOCKS
    PROMPTS = EXTRACT_HELPER_PROMPTS


class MathFunctionTaskSet(TaskSet):
    """A TaskSet that builds all five math-function task variants from a single DAG."""

    TASK_CLASSES: dict[TaskType, type] = {
        TaskType.DEAD_CODE: MathFunctionTaskDeadCode,
        TaskType.ADD_PARAMETER: MathFunctionTaskAddParameter,
        TaskType.ADD_RETURN_VALUE: MathFunctionTaskAddReturnValue,
        TaskType.CACHE_FUNCTION: MathFunctionTaskCacheFunction,
        TaskType.EXTRACT_HELPER: MathFunctionTaskExtractHelper,
    }
    TASK_SET_NAME = "math_function"

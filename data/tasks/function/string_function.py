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
from pathlib import Path


DEAD_CODE_PROMPTS = {
    "none": prompts.PROMPT_DEAD_CODE_STRING,
    "runtime_simple": prompts_runtime_simple.PROMPT_DEAD_CODE_STRING,
}
ADD_PARAMETER_PROMPTS = {
    "none": prompts.PROMPT_ADD_PARAMETER_STRING,
    "runtime_simple": prompts_runtime_simple.PROMPT_ADD_PARAMETER_STRING,
}
ADD_RETURN_VALUE_PROMPTS = {
    "none": prompts.PROMPT_ADD_RETURN_VALUE_STRING,
    "runtime_simple": prompts_runtime_simple.PROMPT_ADD_RETURN_VALUE_STRING,
}
CACHE_FUNCTION_PROMPTS = {
    "none": prompts.PROMPT_CACHE_FUNCTION_DIAMOND_STRING,
    "runtime_simple": prompts_runtime_simple.PROMPT_CACHE_FUNCTION_DIAMOND_STRING,
}
EXTRACT_HELPER_PROMPTS = {
    "none": prompts.PROMPT_EXTRACT_HELPER_DIAMOND_STRING,
    "runtime_simple": prompts_runtime_simple.PROMPT_EXTRACT_HELPER_DIAMOND_STRING,
}

_STROPS_RAW = (Path(__file__).parent / "strops.py").read_text()

_STROPS_FUNCTIONS = [
    "rot13", "reverse", "swap_case", "char_rotate", "char_rotate_by_3", "mirror",
    "interleave", "swap_halves", "zip_chars", "alternate_chars", "xor_chars",
]
_NAMESPACE_LINES = "\n".join(f"    {fn} = staticmethod({fn})" for fn in _STROPS_FUNCTIONS)
STROPS_SOURCE = f"{_STROPS_RAW}\n\nclass _Strops:\n{_NAMESPACE_LINES}\n\nstrops = _Strops()"

external_returns = ["(x, '100')", "(x, '200')", "(x, '300')", "(x, '400')", "(x, '500')"]
default_returns = ['"0"', '"1"', '"2"', '"3"', '"4"']
key_returns = [
    "''.join(str((ord(ch) - 97) % 10) for ch in x.lower() if 'a' <= ch <= 'z') or '0'",
    "''.join(str((ord(ch) - 94) % 10) for ch in x.lower() if 'a' <= ch <= 'z') or '0'",
    "''.join(str((ord(ch) - 91) % 10) for ch in x.lower() if 'a' <= ch <= 'z') or '0'",
]
slow_returns = default_returns

PREFIX_BLOCKS = []
for ext in external_returns:
    for def_ret in default_returns:
        for key in key_returns:
            for slow in slow_returns:
                PREFIX_BLOCKS.append(f"""
{STROPS_SOURCE}

def external(x: str) -> tuple[str, str]:
    return {ext}

def default() -> str:
    return {def_ret}

def get_key(x: str) -> str:
    return {key}

def slow() -> str:
    return {slow}
""".strip())


class StringFunctionTaskDeadCode(BaseFunctionTaskDeadCode):
    FUNCTION_TASK_TYPE = FunctionTaskType.STRING
    PREFIX_BLOCKS = PREFIX_BLOCKS
    PROMPTS = DEAD_CODE_PROMPTS


class StringFunctionTaskAddParameter(BaseFunctionTaskAddParameter):
    FUNCTION_TASK_TYPE = FunctionTaskType.STRING
    PREFIX_BLOCKS = PREFIX_BLOCKS
    PROMPTS = ADD_PARAMETER_PROMPTS


class StringFunctionTaskAddReturnValue(BaseFunctionTaskAddReturnValue):
    FUNCTION_TASK_TYPE = FunctionTaskType.STRING
    PREFIX_BLOCKS = PREFIX_BLOCKS
    PROMPTS = ADD_RETURN_VALUE_PROMPTS


class StringFunctionTaskCacheFunction(BaseFunctionTaskCacheFunction):
    FUNCTION_TASK_TYPE = FunctionTaskType.STRING
    PREFIX_BLOCKS = PREFIX_BLOCKS
    PROMPTS = CACHE_FUNCTION_PROMPTS


class StringFunctionTaskExtractHelper(BaseFunctionTaskExtractHelper):
    FUNCTION_TASK_TYPE = FunctionTaskType.STRING
    PREFIX_BLOCKS = PREFIX_BLOCKS
    PROMPTS = EXTRACT_HELPER_PROMPTS


class StringFunctionTaskSet(TaskSet):
    """A TaskSet that builds all five string-function task variants from a single DAG."""

    TASK_CLASSES: dict[TaskType, type] = {
        TaskType.DEAD_CODE: StringFunctionTaskDeadCode,
        TaskType.ADD_PARAMETER: StringFunctionTaskAddParameter,
        TaskType.ADD_RETURN_VALUE: StringFunctionTaskAddReturnValue,
        TaskType.CACHE_FUNCTION: StringFunctionTaskCacheFunction,
        TaskType.EXTRACT_HELPER: StringFunctionTaskExtractHelper,
    }
    TASK_SET_NAME = "string_function"

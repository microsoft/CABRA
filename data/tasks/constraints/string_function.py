"""String-domain constraints task: concrete subclasses + TaskSet."""

from pathlib import Path

from data.tasks.task import TaskType
from data.tasks import TaskSet
from data.tasks.constraints.ast import COMBINE_ADD
from data.tasks.constraints.base_function import (
    BaseCacheFunctionConstraintsTask,
    BaseExtractHelperConstraintsTask,
    BaseMultConstraintsTask,
    BaseReturnValueConstraintsTask,
)
from data.tasks.problem_statements.constraint_prompts import (
    PROMPT_STRING_CACHE_FUNCTION_CONSTRAINTS,
    PROMPT_STRING_EXTRACT_HELPER_CONSTRAINTS,
    PROMPT_STRING_MULT_CONSTRAINTS,
    PROMPT_STRING_RETURN_VALUE_CONSTRAINTS,
)

_STROPS_RAW = (Path(__file__).parents[1] / "function" / "strops.py").read_text()

_STROPS_FUNCTIONS = [
    "rot13", "reverse", "swap_case", "char_rotate", "char_rotate_by_3", "mirror",
    "interleave", "swap_halves", "zip_chars", "alternate_chars", "xor_chars",
]
_NAMESPACE_LINES = "\n".join(f"    {fn} = staticmethod({fn})" for fn in _STROPS_FUNCTIONS)
STROPS_SOURCE = f"{_STROPS_RAW}\n\nclass _Strops:\n{_NAMESPACE_LINES}\n\nstrops = _Strops()"

external_returns = ["'100'", "'200'", "'300'", "'400'", "'500'"]
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

def external(num_keys: int) -> tuple[str, ...]:
    return tuple([{ext} + str(i) for i in range(num_keys)])

def default(idx: int = 0) -> str:
    return {def_ret} + str(idx)

def get_key(x: str, idx: int = 0) -> str:
    return ({key}) + str(idx)

def slow(idx: int = 0) -> str:
    return ({slow}) + str(idx)
""".strip())


class StringConstraintsAddParameter(BaseMultConstraintsTask):
    PREFIX_BLOCKS = PREFIX_BLOCKS
    TASK_TYPE_NAME = "string"
    PROMPT_TEMPLATE = PROMPT_STRING_MULT_CONSTRAINTS
    TEMPLATE_BANK_KEY = "add_parameter_str"
    VAR_PREFIX = "prefix"
    VALUE_LABEL = "prefix parameters"
    PARAMETER_ANNOTATION = "str"
    TERMINAL_COMBINE_OP = COMBINE_ADD
    VALUE_KIND = "str"


class StringConstraintsAddReturnValue(BaseReturnValueConstraintsTask):
    PREFIX_BLOCKS = PREFIX_BLOCKS
    TASK_TYPE_NAME = "string"
    PROMPT_TEMPLATE = PROMPT_STRING_RETURN_VALUE_CONSTRAINTS


class StringConstraintsCacheFunction(BaseCacheFunctionConstraintsTask):
    PREFIX_BLOCKS = PREFIX_BLOCKS
    TASK_TYPE_NAME = "string"
    PROMPT_TEMPLATE = PROMPT_STRING_CACHE_FUNCTION_CONSTRAINTS
    TEMPLATE_BANK_KEY = "cache_slow_str"
    VALUE_TYPE = "str"
    DEFAULT_VALUE = '""'
    VALUE_KIND = "str"


class StringConstraintsExtractHelper(BaseExtractHelperConstraintsTask):
    PREFIX_BLOCKS = PREFIX_BLOCKS
    TASK_TYPE_NAME = "string"
    PROMPT_TEMPLATE = PROMPT_STRING_EXTRACT_HELPER_CONSTRAINTS
    TEMPLATE_BANK_KEY = "extract_helper_str"
    VAR_PREFIX = "prefix"
    VALUE_LABEL = "extracted prefixes"
    HELPER_FUNCTION_NAME = "get_key"
    HELPER_TYPE = "str"
    COMBINE_OP = COMBINE_ADD
    VALUE_KIND = "str"


class StringConstraintsTaskSet(TaskSet):
    """Builds the string constraints task from a single DAG."""

    TASK_CLASSES: dict[TaskType, type] = {
        TaskType.ADD_PARAMETER: StringConstraintsAddParameter,
        TaskType.ADD_RETURN_VALUE: StringConstraintsAddReturnValue,
        TaskType.CACHE_FUNCTION: StringConstraintsCacheFunction,
        TaskType.EXTRACT_HELPER: StringConstraintsExtractHelper,
    }
    TASK_SET_NAME = "string_constraints"

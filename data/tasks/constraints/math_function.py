"""Math-domain mult-constraints task: concrete subclass + TaskSet."""

from data.tasks.task import TaskType
from data.tasks import TaskSet
from data.tasks.constraints.base_function import (
    BaseCacheFunctionConstraintsTask,
    BaseExtractHelperConstraintsTask,
    BaseMultConstraintsTask,
    BaseReturnValueConstraintsTask,
)

external_returns = ["'100'", "'200'", "'300'", "'400'", "'500'"]
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

def external(num_keys: int) -> tuple[str, ...]:
    return tuple([{ext}+str(i) for i in range(num_keys)])

def default(idx: int = 0) -> float:
    return {def_ret} + 0.024 * idx

def get_multiplier(x: float, idx: int = 0) -> float:
    return ({mult}) + 0.031 * idx

def slow(idx: int = 0) -> float:
    return ({slow}) + 0.017 * idx
""".strip())


class MathMultConstraintsAddParameter(BaseMultConstraintsTask):
    PREFIX_BLOCKS = PREFIX_BLOCKS
    TASK_TYPE_NAME = "math"


class MathMultConstraintsAddReturnValue(BaseReturnValueConstraintsTask):
    PREFIX_BLOCKS = PREFIX_BLOCKS
    TASK_TYPE_NAME = "math"


class MathMultConstraintsCacheFunction(BaseCacheFunctionConstraintsTask):
    PREFIX_BLOCKS = PREFIX_BLOCKS
    TASK_TYPE_NAME = "math"


class MathMultConstraintsExtractHelper(BaseExtractHelperConstraintsTask):
    PREFIX_BLOCKS = PREFIX_BLOCKS
    TASK_TYPE_NAME = "math"


class MathMultConstraintsTaskSet(TaskSet):
    """Builds the mult-constraints task from a single DAG."""

    TASK_CLASSES: dict[TaskType, type] = {
        TaskType.ADD_PARAMETER: MathMultConstraintsAddParameter,
        TaskType.ADD_RETURN_VALUE: MathMultConstraintsAddReturnValue,
        TaskType.CACHE_FUNCTION: MathMultConstraintsCacheFunction,
        TaskType.EXTRACT_HELPER: MathMultConstraintsExtractHelper,
    }
    TASK_SET_NAME = "math_mult_constraints"

"""AST transformations for code editing tasks."""

import ast
import copy
import math
import operator
import random

from data.utils.program_params import ProgramParams

# ========================= math operations =========================

SINGLE_NUMBER_OPERATIONS = [
    abs,
    round,
    math.sin,
    math.cos,
    math.tanh,
    math.atan,
    math.erf,
    math.degrees,
    math.radians,
    operator.neg,
]
SINGLE_NUMBER_OPERATIONS = [
    x.__name__ if x.__module__ == "builtins"
    else f"{x.__module__}.{x.__name__}"
    for x in SINGLE_NUMBER_OPERATIONS
]
MULTI_NUMBER_OPERATIONS = [
    operator.add,
    operator.sub,
    min,
    max,
    math.hypot,
    math.copysign,
    math.atan2,
]
MULTI_NUMBER_OPERATIONS = [
    x.__name__ if x.__module__ == "builtins"
    else f"{x.__module__}.{x.__name__}"
    for x in MULTI_NUMBER_OPERATIONS
]

SINGLE_NUMBER_OPERATIONS = [x.replace("_operator", "operator").replace("operator_", "operator") for x in SINGLE_NUMBER_OPERATIONS]
MULTI_NUMBER_OPERATIONS = [x.replace("_operator", "operator").replace("operator_", "operator") for x in MULTI_NUMBER_OPERATIONS]

# ========================= string operations =========================

SINGLE_STRING_OPERATIONS = [
    "strops.rot13",
    "strops.reverse",
    "strops.swap_case",
    "strops.char_rotate",
    "strops.char_rotate_by_3",
    "strops.mirror",
]

MULTI_STRING_OPERATIONS = [
    "strops.interleave",
    "strops.swap_halves",
    "strops.zip_chars",
    "strops.alternate_chars",
    "strops.xor_chars",
]
SINGLE_STRING_OPERATIONS = [x.replace("_operator", "operator").replace("operator_", "operator") for x in SINGLE_STRING_OPERATIONS]
MULTI_STRING_OPERATIONS = [x.replace("_operator", "operator").replace("operator_", "operator") for x in MULTI_STRING_OPERATIONS]

# ========================= tensor operations =========================

SINGLE_ARRAY_OPERATIONS = [
    "np.abs",
    "np.sign",
    "np.round",
    "np.sin",
    "np.cos",
    "np.tanh",
    "np.cumsum",
    "np.cumprod",
    "np.sort",
    "np.flip",
]

MULTI_ARRAY_OPERATIONS = [
    "np.add",
    "np.subtract",
    "np.multiply",
    "np.maximum",
    "np.minimum",
    "np.hypot",
    "np.arctan2",
]
SINGLE_ARRAY_OPERATIONS = [x.replace("_operator", "operator").replace("operator_", "operator") for x in SINGLE_ARRAY_OPERATIONS]
MULTI_ARRAY_OPERATIONS = [x.replace("_operator", "operator").replace("operator_", "operator") for x in MULTI_ARRAY_OPERATIONS]


# ========================= helper functions =========================

def sample_operator(rng, type: str, task_type: str):
    
    single, multi = [SINGLE_NUMBER_OPERATIONS, MULTI_NUMBER_OPERATIONS]
    if task_type == "math":
        single, multi = [SINGLE_NUMBER_OPERATIONS, MULTI_NUMBER_OPERATIONS]
    elif task_type == "string":
        single, multi = [SINGLE_STRING_OPERATIONS, MULTI_STRING_OPERATIONS]
    elif task_type == "array":
        single, multi = [SINGLE_ARRAY_OPERATIONS, MULTI_ARRAY_OPERATIONS]
    else:
        raise ValueError("Invalid task type. Must be 'math', 'string', or 'array'.")

    if type == "single":
        return rng.choice(single)
    elif type == "multi":
        return rng.choice(multi)
    else:
        raise ValueError("Invalid operator type. Must be 'single' or 'multi'")


def _unparse(tree) -> str:
    return (
        ast.unparse(tree)
        .replace("\nif __name__", "\n\nif __name__")
    )


def _name_annotation(type_src: str) -> ast.expr:
    return ast.parse(type_src, mode="eval").body


def _default_call() -> ast.Call:
    return ast.Call(func=ast.Name(id="default", ctx=ast.Load()), args=[], keywords=[])


def _is_state_return_tuple(value: ast.expr | None) -> bool:
    return (
        isinstance(value, ast.Tuple)
        and len(value.elts) == 2
        and (
            (
                isinstance(value.elts[1], ast.Name)
                and value.elts[1].id == "state"
            )
            or (
                isinstance(value.elts[1], ast.Constant)
                and isinstance(value.elts[1].value, int)
            )
        )
    )

def _check_guard(x: int | None = None, a: int | None = None, b: int | None = None, target: int | None = None, num_steps: int | None = None) -> bool:
    if x is not None and a is None and b is None and target is None and num_steps is None:
        return int(x) == 0
    if x is None and a is None and b is None and target is None and num_steps is None:
        return True
    if None in (x, a, b, target):
        raise ValueError("check expects either no args or at least four args")
    if num_steps is None:
        num_steps = 3
    x = int(x)
    for _ in range(int(num_steps)):
        if x % 2 == 0:
            x = x // 2
        else:
            x = int(a) * x + int(b)
    return x % 2 == int(target)


_SAFE_CONSTANT_FUNCTIONS = {
    "abs": abs,
    "bool": bool,
    "int": int,
    "len": len,
    "max": max,
    "min": min,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "check": _check_guard,
}

_SAFE_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.BitXor: operator.xor,
}

_SAFE_UNARY_OPS = {
    ast.Not: operator.not_,
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

_SAFE_COMPARE_OPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda left, right: left in right,
    ast.NotIn: lambda left, right: left not in right,
}


def _safe_constant_eval(expr: ast.expr):
    if isinstance(expr, ast.Constant):
        return expr.value
    if isinstance(expr, ast.List):
        return [_safe_constant_eval(elt) for elt in expr.elts]
    if isinstance(expr, ast.Tuple):
        return tuple(_safe_constant_eval(elt) for elt in expr.elts)
    if isinstance(expr, ast.Set):
        return {_safe_constant_eval(elt) for elt in expr.elts}
    if isinstance(expr, ast.Dict):
        return {
            _safe_constant_eval(key): _safe_constant_eval(value)
            for key, value in zip(expr.keys, expr.values)
        }
    if isinstance(expr, ast.UnaryOp):
        op = _SAFE_UNARY_OPS.get(type(expr.op))
        if op is None:
            raise ValueError("unsupported unary op")
        return op(_safe_constant_eval(expr.operand))
    if isinstance(expr, ast.BinOp):
        op = _SAFE_BIN_OPS.get(type(expr.op))
        if op is None:
            raise ValueError("unsupported binary op")
        return op(_safe_constant_eval(expr.left), _safe_constant_eval(expr.right))
    if isinstance(expr, ast.BoolOp):
        values = [_safe_constant_eval(value) for value in expr.values]
        if isinstance(expr.op, ast.And):
            return all(values)
        if isinstance(expr.op, ast.Or):
            return any(values)
        raise ValueError("unsupported bool op")
    if isinstance(expr, ast.Compare):
        left = _safe_constant_eval(expr.left)
        for op_node, comparator in zip(expr.ops, expr.comparators):
            op = _SAFE_COMPARE_OPS.get(type(op_node))
            if op is None:
                raise ValueError("unsupported compare op")
            right = _safe_constant_eval(comparator)
            if not op(left, right):
                return False
            left = right
        return True
    if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name):
        func = _SAFE_CONSTANT_FUNCTIONS.get(expr.func.id)
        if func is None or any(keyword.arg is None for keyword in expr.keywords):
            raise ValueError("unsupported call")
        return func(
            *[_safe_constant_eval(arg) for arg in expr.args],
            **{keyword.arg: _safe_constant_eval(keyword.value) for keyword in expr.keywords},
        )
    raise ValueError("unsupported expression")


def _constant_branch_truth(test: ast.expr) -> bool | None:
    try:
        value = _safe_constant_eval(test)
    except Exception:
        return None
    if isinstance(value, bool):
        return value
    return None


def _branch_truth_for_state_or_constant(test: ast.expr, current_state: int | None) -> bool | None:
    if (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "state"
        and len(test.ops) == 1
        and isinstance(test.ops[0], (ast.Eq, ast.NotEq))
        and len(test.comparators) == 1
        and isinstance(test.comparators[0], ast.Constant)
        and isinstance(test.comparators[0].value, int)
        and current_state is not None
    ):
        is_equal = current_state == test.comparators[0].value
        return not is_equal if isinstance(test.ops[0], ast.NotEq) else is_equal
    return _constant_branch_truth(test)


class _ActiveBranchTracker:
    def __init__(self, active_state: int | None = None):
        self.current_state: int | None = active_state
        self.active_stack: list[bool] = []

    def is_active_path(self) -> bool:
        return not self.active_stack or all(self.active_stack)

    def branch_truth(self, test: ast.expr) -> bool | None:
        return _branch_truth_for_state_or_constant(test, self.current_state)

    def visit_state_assignment(self, stmt: ast.stmt) -> None:
        value = None
        target = None
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
            target = stmt.targets[0]
            value = stmt.value
        elif isinstance(stmt, ast.AnnAssign):
            target = stmt.target
            value = stmt.value
        if (
            isinstance(target, ast.Name)
            and target.id == "state"
            and isinstance(value, ast.Constant)
            and isinstance(value.value, int)
        ):
            self.current_state = value.value


def _insert_stmt_at_active_leaf(
    body: list[ast.stmt], stmt: ast.stmt, tracker: "_ActiveBranchTracker"
) -> bool:
    """Insert *stmt* at the start of the innermost active-path branch of *body*.

    Descends through active if/else branches so the statement lands inside the
    branch that actually executes (matching the runtime_simple prompts, which
    define the helper inside the running branch). Returns True if a resolvable
    branch was found; False if *body* has no branch to descend into, in which
    case the caller should fall back to inserting at the top of *body*.
    """
    for item in body:
        if isinstance(item, ast.If):
            truth = tracker.branch_truth(item.test)
            if truth is None:
                return False
            active = item.body if truth else item.orelse
            if not _insert_stmt_at_active_leaf(active, stmt, tracker):
                active.insert(0, stmt)
            return True
        tracker.visit_state_assignment(item)
    return False


def _wrap_return_payload(value: ast.expr, wrapper) -> ast.expr:
    if _is_state_return_tuple(value):
        return ast.Tuple(
            elts=[wrapper(value.elts[0]), value.elts[1]],
            ctx=ast.Load(),
        )
    return wrapper(value)


def _tuple_annotation(*type_srcs: str) -> ast.Subscript:
    return ast.Subscript(
        value=ast.Name(id="tuple", ctx=ast.Load()),
        slice=ast.Tuple(
            elts=[_name_annotation(type_src) for type_src in type_srcs],
            ctx=ast.Load(),
        ),
        ctx=ast.Load(),
    )


def _function_returns_state(node: ast.FunctionDef) -> bool:
    return any(
        isinstance(child, ast.Return) and _is_state_return_tuple(child.value)
        for child in ast.walk(node)
    )


def _add_default_parameter_to_function(node: ast.FunctionDef, parameter: str, helper_type: str) -> None:
    if any(arg.arg == parameter for arg in node.args.args):
        return
    node.args.args.append(
        ast.arg(arg=parameter, annotation=_name_annotation(helper_type))
    )
    node.args.defaults.append(_default_call())


def add_default_parameter_to_functions(
    source: str,
    function_names: set[str],
    parameter: str,
    helper_type: str,
) -> str:
    class SignatureUpdater(ast.NodeTransformer):
        def visit_FunctionDef(self, node: ast.FunctionDef):
            if node.name in function_names:
                _add_default_parameter_to_function(node, parameter, helper_type)
            return self.generic_visit(node)

    tree = ast.parse(source)
    tree = SignatureUpdater().visit(tree)
    ast.fix_missing_locations(tree)
    return _unparse(tree)


def synthesize_plain_body(
    outgoing: list[str],
    operators: list[str],
) -> str:
    """Plain (non-obfuscated) body: child calls assigned to variables, operations chained."""
    lines = []
    if len(outgoing) == 0:
        lines.append(f"return {operators[0]}(val)")
        return indent(lines)
    child_vars = []
    for child in outgoing:
        var = f"{child}_val"
        lines.append(f"{var} = {child}(val)")
        child_vars.append(var)
    if len(outgoing) == 1:
        lines.append(f"return {operators[0]}({child_vars[0]})")
        return indent(lines)
    expr = f"{operators[0]}({child_vars[0]}, {child_vars[1]})"
    for i in range(1, len(operators)):
        expr = f"{operators[i]}({expr}, {child_vars[i + 1]})"
    lines.append(f"return {expr}")
    return indent(lines)


def build_starter_code(dag_data: list, seed: int, multi_line: bool = False, task_type: str = "math") -> str:
    raise NotImplementedError("Superseded by the program_params-aware build_starter_code below.")

# ---------------------------------------------------------------------
# Main starter-code builder
# ---------------------------------------------------------------------

import random
import string
import sys


# ---------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------

def indent(lines: list[str], n: int = 4) -> str:
    pad = " " * n
    return "\n".join(pad + line if line else "" for line in lines)


def rand_string(rng: random.Random, min_len: int = 3, max_len: int = 12) -> str:
    alphabet = string.ascii_lowercase
    return "".join(
        rng.choice(alphabet)
        for _ in range(rng.randint(min_len, max_len))
    )


def excel_symbol(index: int) -> str:
    """
    0 -> a
    1 -> b
    ...
    25 -> z
    26 -> aa
    """
    letters = string.ascii_lowercase
    out = ""

    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        out = letters[rem] + out

    return out


# ---------------------------------------------------------------------
# Guard generation
# ---------------------------------------------------------------------

def random_true_guard(rng: random.Random) -> str:
    a = rng.randint(-500, 500)
    b = rng.randint(-500, 500)
    c = rng.randint(1, 100)
    s = rand_string(rng)
    t = rand_string(rng)

    return rng.choice([
        "True",
        "not False",
        "bool(1)",
        "1 == 1",
        "0 == 0",
        f"{a} == {a}",
        f"{a} <= {a}",
        f"{a} + 0 == {a}",
        f"{a} * 1 == {a}",
        f"{a} - {a} == 0",
        f"{a} + {b} == {b} + {a}",
        f"({a} + {b} - {b}) == {a}",
        f"len({s!r}) == {len(s)}",
        f"{s!r} == {s!r}",
        f"{s!r} + {t!r} == {s + t!r}",
        f"len([{a}, {b}, {c}]) == 3",
        f"sum([{c}, -{c}]) == 0",
        f"sorted([{b}, {a}]) == sorted([{a}, {b}])",
        f"{a} in [{a}, {b}]",
        f"{s!r} in {s!r}",
        f"({len(s)} == len({s!r}))",
        f"tuple([{a}, {b}]) == ({a}, {b})",
    ])


def random_false_guard(rng: random.Random) -> str:
    a = rng.randint(-500, 500)
    b = rng.randint(-500, 500)
    c = rng.randint(1, 100)
    s = rand_string(rng)
    t = rand_string(rng)

    wrong_len = len(s) + rng.choice([-4, -3, -2, -1, 1, 2, 3, 4])

    return rng.choice([
        "False",
        "not True",
        "bool(0)",
        "1 == 0",
        "0 != 0",
        f"{a} != {a}",
        f"{a} > {a}",
        f"{a} - {a} != 0",
        f"{a} + 0 != {a}",
        f"{a} * 1 != {a}",
        f"{a} + {b} != {b} + {a}",
        f"({a} + {b} - {b}) != {a}",
        f"len({s!r}) == {wrong_len}",
        f"{s!r} != {s!r}",
        f"{s!r} + {t!r} != {s + t!r}",
        f"len([{a}, {b}, {c}]) != 3",
        f"sum([{c}, -{c}]) != 0",
        f"sorted([{b}, {a}]) != sorted([{a}, {b}])",
        f"{s!r} not in {s!r}",
        f"({wrong_len} == len({s!r}))",
        f"tuple([{a}, {b}]) != ({a}, {b})",
    ])


# ---------------------------------------------------------------------
# Branch expression generation
# ---------------------------------------------------------------------

def build_chained_expression(
    child_vars: list[str],
    operators: list[str],
) -> str:
    """
    Mirrors your original operation chaining.

    For 0 children:
        op(val)

    For 1 child:
        op(a)

    For 3 children and 2 operators:
        op2(op1(a, b), c)
    """
    if len(child_vars) == 0:
        return f"{operators[0]}(val)"

    if len(child_vars) == 1:
        return f"{operators[0]}({child_vars[0]})"

    expr = f"{operators[0]}({child_vars[0]}, {child_vars[1]})"

    for i in range(1, len(operators)):
        expr = f"{operators[i]}({expr}, {child_vars[i + 1]})"

    return expr


def make_branch_from_functions(
    function_names: list[str],
    operators: list[str],
) -> list[str]:
    """
    Shared branch renderer.

    Both live and dead branches go through this function, so they have
    exactly the same structure. The only difference is which functions are
    used for the child calls.
    """
    lines = []

    if len(function_names) == 0:
        lines.append(f"return {operators[0]}(val)")
        return lines

    child_vars = []

    for fn_name in function_names:
        var = f"{fn_name}_val"
        child_vars.append(var)
        lines.append(f"{var} = {fn_name}(val)")

    expr = build_chained_expression(child_vars, operators)
    lines.append(f"return {expr}")

    return lines


def sample_dead_function_names(
    rng: random.Random,
    all_function_names: list[str],
    node_id: str,
    live_function_names: list[str],
) -> list[str]:
    """
    Samples real existing functions for the dead branch.

    Same arity as the live branch. We avoid the current function to avoid
    direct recursion if someone manually flips the branch.
    """
    k = len(live_function_names)

    if k == 0:
        return []

    candidates = [
        name
        for name in all_function_names
        if name != node_id
    ]

    if not candidates:
        return list(live_function_names)

    # Prefer not to exactly reuse the live children if possible.
    non_live_candidates = [
        name
        for name in candidates
        if name not in set(live_function_names)
    ]

    if len(non_live_candidates) >= k:
        sampled = rng.sample(non_live_candidates, k=k)
    elif len(candidates) >= k:
        sampled = rng.sample(candidates, k=k)
    else:
        sampled = [
            rng.choice(candidates)
            for _ in range(k)
        ]

    # Avoid accidentally producing the exact same sequence when possible.
    if sampled == live_function_names and len(candidates) > 1:
        for _ in range(5):
            rng.shuffle(sampled)
            if sampled != live_function_names:
                break

    return sampled


def synthesize_if_body(
    node_id: str,
    outgoing: list[str],
    operators: list[str],
    rng: random.Random,
    all_function_names: list[str],
) -> str:
    live_function_names = list(outgoing)

    dead_function_names = sample_dead_function_names(
        rng=rng,
        all_function_names=all_function_names,
        node_id=node_id,
        live_function_names=live_function_names,
    )

    live_branch = make_branch_from_functions(
        function_names=live_function_names,
        operators=operators,
    )

    dead_branch = make_branch_from_functions(
        function_names=dead_function_names,
        operators=operators,
    )

    live_in_if = rng.choice([True, False])

    if live_in_if:
        guard = random_true_guard(rng)
        lines = [f"if {guard}:"]
        lines.extend("    " + line for line in live_branch)
        lines.append("else:")
        lines.extend("    " + line for line in dead_branch)
    else:
        guard = random_false_guard(rng)
        lines = [f"if {guard}:"]
        lines.extend("    " + line for line in dead_branch)
        lines.append("else:")
        lines.extend("    " + line for line in live_branch)

    return indent(lines)


# ---------------------------------------------------------------------
# Main starter-code builder
# ---------------------------------------------------------------------

def build_starter_code(
    dag_data: list,
    seed: int,
    program_params: "ProgramParams" = None,
    task_type: str = "math",
    if_start_nodes: set[str] | None = None,
    if_subgraph_nodes: set[str] | None = None,
    if_mode: str = "forward",
    excluded_entry_points: set[str] | None = None,
    backward_return_state_mode: str = "child",
    cross_graph_distractors: bool = False,
    identical_runtime_simple_branches: bool = True,
) -> str:
    from data.tasks.function.runtime_if import (
        DistractorCallGraph,
        runtime_simple_if_shape,
        runtime_simple_check_helper_source,
        synthesize_runtime_if_body,
    )

    if program_params is None:
        program_params = ProgramParams()

    is_runtime = program_params.if_type == "runtime"

    task_type_to_return_type = {
        "math": "float",
        "string": "str",
        "array": "np.ndarray",
    }
    return_type = task_type_to_return_type[task_type]

    all_function_names = sorted({
        node["id"]
        for dag in dag_data
        for node in dag["nodes"]
    })

    # Topological depth of every function in the combined call graph. Distractor
    # branches use this to only call functions at the same level or below the
    # current one; calling a function above (an ancestor) would introduce a
    # cycle into the call graph.
    node_to_preds: dict[str, list[str]] = {name: [] for name in all_function_names}
    for dag in dag_data:
        for edge in dag["edges"]:
            node_to_preds.setdefault(edge["target"], []).append(edge["source"])

    node_level: dict[str, int] = {}

    def _compute_level(name: str) -> int:
        if name in node_level:
            return node_level[name]
        node_level[name] = 0  # guard against unexpected cycles
        preds = node_to_preds.get(name, [])
        level = 0 if not preds else 1 + max(_compute_level(p) for p in preds)
        node_level[name] = level
        return level

    for name in all_function_names:
        _compute_level(name)

    original_edges = [
        (edge["source"], edge["target"])
        for dag in dag_data
        for edge in dag["edges"]
    ]

    def _collect_entry_points_and_node_items(excluded: set[str]):
        all_entry_points = []
        node_items = []
        for dag_index, dag in enumerate(dag_data):
            node_to_outgoing = {}
            node_to_incoming = {}

            for edge in dag["edges"]:
                node_to_outgoing.setdefault(edge["source"], []).append(edge["target"])
                node_to_incoming.setdefault(edge["target"], []).append(edge["source"])

            all_entry_points.extend(
                node["id"]
                for node in dag["nodes"]
                if not node_to_incoming.get(node["id"], [])
                and node["id"] not in excluded
            )
            node_items.extend(
                (dag_index, node, node_to_outgoing)
                for node in dag["nodes"]
            )

        random.Random(f"{seed}:if_node_order").shuffle(node_items)
        return all_entry_points, node_items

    # -----------------------------------------------------------------
    # Runtime simple if-statement mode
    # -----------------------------------------------------------------
    if is_runtime:
        if if_start_nodes is None:
            if_start_nodes = set()
        if if_subgraph_nodes is None:
            if_subgraph_nodes = set()
        if excluded_entry_points is None:
            excluded_entry_points = set()

        all_functions = []
        all_entry_points, node_items = _collect_entry_points_and_node_items(excluded_entry_points)
        distractor_call_graph = DistractorCallGraph(all_function_names, original_edges)
        runtime_simple_check_breadth, runtime_simple_check_depth = runtime_simple_if_shape(
            program_params.if_num_hops,
            program_params.if_breadth_depth_ratio,
        )
        for _dag_index, node, node_to_outgoing in node_items:
            node_id = node["id"]
            outgoing = node_to_outgoing.get(node_id, [])
            node_rng = random.Random(f"{seed}:{node_id}")

            if len(outgoing) <= 1:
                operators = [sample_operator(node_rng, "single", task_type)]
            else:
                operators = [
                    sample_operator(node_rng, "multi", task_type)
                    for _ in range(len(outgoing) - 1)
                ]

            distractor_function_names = None
            if cross_graph_distractors and if_subgraph_nodes:
                if node_id in if_subgraph_nodes:
                    distractor_function_names = [
                        name for name in all_function_names
                        if name not in if_subgraph_nodes
                    ]
                else:
                    distractor_function_names = list(if_subgraph_nodes)
            elif node_id in if_subgraph_nodes:
                distractor_function_names = [
                    name for name in all_function_names
                    if name not in if_subgraph_nodes
                ]

            body = synthesize_runtime_if_body(
                node_id=node_id,
                outgoing=outgoing,
                operators=operators,
                rng=node_rng,
                all_function_names=all_function_names,
                num_branches=program_params.num_branches,
                task_type=task_type,
                node_level=node_level,
                distractor_function_names=distractor_function_names,
                distractor_call_graph=distractor_call_graph,
                identical_branches=identical_runtime_simple_branches,
                check_breadth=runtime_simple_check_breadth,
                check_depth=runtime_simple_check_depth,
                check_param_mode="unique_params",
                shared_check_args=None,
            )
            signature = f"def {node_id}(val: {return_type}) -> {return_type}:"

            curr_function = f"{signature}\n{body}"
            all_functions.append(curr_function)

        # Build main() block
        entry_calls = ", ".join(
            f"{ep}(val)" for ep in all_entry_points
        )
        main_block = (
            f"def main(val: {return_type}):\n"
            f"    return ({entry_calls})"
        )

        if task_type in ["math", "string"]:
            main_exec = f"if __name__ == '__main__':\n    main({return_type}(sys.argv[1]))"
        elif task_type == "array":
            main_exec = "if __name__ == '__main__':\n    main(np.array(eval(sys.argv[1])))"
        else:
            raise ValueError(f"Unsupported task_type: {task_type}")

        random.Random(seed).shuffle(all_functions)

        helper_blocks = []
        if program_params.num_branches >= 2:
            helper_blocks.append(runtime_simple_check_helper_source(runtime_simple_check_depth))

        if task_type == "math":
            extra_import = "import math\nimport operator"
        elif task_type == "array":
            extra_import = "import numpy as np"
        elif task_type == "string":
            extra_import = "import strops"
        else:
            extra_import = ""

        final_code = (
            f"{extra_import}\n"
            "import sys\n\n"
            + ("\n\n".join(helper_blocks) + "\n\n" if helper_blocks else "")
            + "\n\n".join(all_functions)
            + "\n\n"
            + main_block
            + "\n\n"
            + main_exec
        )
        return final_code

    # -----------------------------------------------------------------
    # None mode (no if-statements): plain straight-line bodies
    # -----------------------------------------------------------------

    if if_subgraph_nodes is None:
        if_subgraph_nodes = set()
    if excluded_entry_points is None:
        excluded_entry_points = set()

    all_functions = []
    all_entry_points, node_items = _collect_entry_points_and_node_items(excluded_entry_points)

    for _dag_index, node, node_to_outgoing in node_items:
        node_id = node["id"]
        outgoing = node_to_outgoing.get(node_id, [])
        node_rng = random.Random(f"{seed}:{node_id}")

        if len(outgoing) <= 1:
            operators = [
                sample_operator(node_rng, "single", task_type)
            ]
        else:
            operators = [
                sample_operator(node_rng, "multi", task_type)
                for _ in range(len(outgoing) - 1)
            ]

        body = synthesize_plain_body(outgoing, operators)
        signature = f"def {node_id}(val: {return_type}) -> {return_type}:"
        curr_function = f"{signature}\n{body}"
        all_functions.append(curr_function)

    entry_points = ", ".join([
        f"{ep}(val)"
        for ep in all_entry_points
    ])

    main_block = f"""
def main(val: {return_type}):
    return ({entry_points})
""".strip()

    if task_type in ["math", "string"]:
        main_exec = f"""
if __name__ == '__main__':
    main({return_type}(sys.argv[1]))
""".strip()
    elif task_type == "array":
        main_exec = """
if __name__ == '__main__':
    main(np.array(eval(sys.argv[1])))
""".strip()
    else:
        raise ValueError(f"Unsupported task_type: {task_type}")

    random.Random(seed).shuffle(all_functions)

    if task_type == "math":
        extra_import = "import math\nimport operator"
    elif task_type == "array":
        extra_import = "import numpy as np"
    elif task_type == "string":
        extra_import = "import strops"
    else:
        extra_import = ""

    final_code = (
        f"{extra_import}\n"
        "import sys\n\n"
        + "\n\n".join(all_functions)
        + "\n\n"
        + main_block
        + "\n\n"
        + main_exec
    )

    return final_code


def remove_functions(source: str, function_names: set[str]) -> str:
    """
    Remove top-level function definitions and their calls from main()'s return.

    Given generated source code, removes:
    1. Top-level `def` statements whose name is in `function_names`.
    2. Calls to those functions inside main()'s return tuple.
    """
    tree = ast.parse(source)

    # Remove top-level function defs
    tree.body = [
        node for node in tree.body
        if not (isinstance(node, ast.FunctionDef) and node.name in function_names)
    ]

    # Fix main()'s return to exclude calls to removed functions
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Tuple):
                    stmt.value.elts = [
                        elt for elt in stmt.value.elts
                        if not (
                            isinstance(elt, ast.Call)
                            and isinstance(elt.func, ast.Name)
                            and elt.func.id in function_names
                        )
                    ]
                    # Unwrap single-element tuple
                    if len(stmt.value.elts) == 1:
                        stmt.value = stmt.value.elts[0]
            break

    class RemovedCallReplacer(ast.NodeTransformer):
        def visit_FunctionDef(self, node: ast.FunctionDef):
            if node.name == "main":
                return node
            return self.generic_visit(node)

        def visit_Call(self, node: ast.Call):
            self.generic_visit(node)
            if isinstance(node.func, ast.Name) and node.func.id in function_names:
                return ast.Name(id="val", ctx=ast.Load())
            return node

    tree = RemovedCallReplacer().visit(tree)

    ast.fix_missing_locations(tree)
    return _unparse(tree)


def add_return_value(
    source: str,
    source_functions: set[str],
    functions_to_modify: set[str],
    return_type: str,
    active_state_by_function: dict[str, int] | None = None,
) -> str:
    """
    source_functions:
        Functions where we directly wrap the return expression in external(...).

    functions_to_modify:
        Functions whose return type should become tuple[..., str].
        These functions may call source_functions or other functions_to_modify.
    """

    tuple_returning_functions = source_functions | functions_to_modify

    def return_state_from_expr(value: ast.expr | None, current_state: int | None, state_vars: dict[str, int]) -> int | None:
        if not _is_state_return_tuple(value):
            return None
        state_expr = value.elts[1]
        if isinstance(state_expr, ast.Constant) and isinstance(state_expr.value, int):
            return state_expr.value
        if isinstance(state_expr, ast.Name):
            if state_expr.id == "state":
                return current_state
            return state_vars.get(state_expr.id)
        return None

    def infer_return_states(tree: ast.Module) -> dict[str, int]:
        functions = {
            node.name: node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
        }

        def assignment_parts(stmt: ast.stmt) -> tuple[ast.expr | None, ast.expr | None]:
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                return stmt.targets[0], stmt.value
            if isinstance(stmt, ast.AnnAssign):
                return stmt.target, stmt.value
            return None, None

        def branch_truth(test: ast.expr, current_state: int | None) -> bool | None:
            return _branch_truth_for_state_or_constant(test, current_state)

        def infer_body(body: list[ast.stmt], current_state: int | None, state_vars: dict[str, int], known_states: dict[str, int]) -> int | None:
            for stmt in body:
                target, value = assignment_parts(stmt)
                if (
                    isinstance(target, ast.Tuple)
                    and len(target.elts) == 2
                    and isinstance(target.elts[1], ast.Name)
                    and isinstance(value, ast.Call)
                    and isinstance(value.func, ast.Name)
                    and value.func.id in known_states
                ):
                    state_vars[target.elts[1].id] = known_states[value.func.id]

                if isinstance(target, ast.Name) and target.id == "state":
                    if isinstance(value, ast.Constant) and isinstance(value.value, int):
                        current_state = value.value
                    elif isinstance(value, ast.Name) and value.id in state_vars:
                        current_state = state_vars[value.id]

                if isinstance(stmt, ast.If):
                    truth = branch_truth(stmt.test, current_state)
                    if truth is not None:
                        return infer_body(
                            stmt.body if truth else stmt.orelse,
                            current_state,
                            dict(state_vars),
                            known_states,
                        )
                    body_state = infer_body(stmt.body, current_state, dict(state_vars), known_states)
                    orelse_state = infer_body(stmt.orelse, current_state, dict(state_vars), known_states)
                    if body_state == orelse_state:
                        return body_state
                    return None

                if isinstance(stmt, ast.Return):
                    return return_state_from_expr(stmt.value, current_state, state_vars)
            return None

        known_states: dict[str, int] = {}
        for _ in range(len(functions) + 1):
            changed = False
            for name, node in functions.items():
                inferred = infer_body(
                    node.body,
                    (active_state_by_function or {}).get(name),
                    {},
                    known_states,
                )
                if inferred is not None and known_states.get(name) != inferred:
                    known_states[name] = inferred
                    changed = True
            if not changed:
                break
        return known_states

    def assignment_target_and_value(stmt: ast.stmt) -> tuple[ast.expr | None, ast.expr | None]:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
            return stmt.targets[0], stmt.value
        if isinstance(stmt, ast.AnnAssign):
            return stmt.target, stmt.value
        return None, None

    def first_value_target_name(target: ast.expr | None) -> str | None:
        if isinstance(target, ast.Name):
            return target.id
        if isinstance(target, ast.Tuple) and target.elts:
            first = target.elts[0]
            if isinstance(first, ast.Name):
                return first.id
            if isinstance(first, ast.Tuple) and first.elts and isinstance(first.elts[0], ast.Name):
                return first.elts[0].id
        return None

    def expr_string_name(
        expr: ast.expr | None,
        string_by_value_name: dict[str, str],
        nested_payload_by_function: dict[str, bool],
    ) -> str | None:
        if expr is None:
            return None

        class Finder(ast.NodeVisitor):
            def __init__(self):
                self.found: str | None = None

            def visit_Name(self, node: ast.Name):
                if self.found is None and node.id in string_by_value_name:
                    self.found = string_by_value_name[node.id]

            def visit_Call(self, node: ast.Call):
                if (
                    self.found is None
                    and isinstance(node.func, ast.Name)
                    and nested_payload_by_function.get(node.func.id, False)
                ):
                    self.found = f"{node.func.id}_str"
                    return
                self.generic_visit(node)

        finder = Finder()
        finder.visit(expr)
        return finder.found

    def infer_nested_payloads(tree: ast.Module, returned_state_by_function: dict[str, int]) -> dict[str, bool]:
        functions = {
            node.name: node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
        }

        def branch_truth(test: ast.expr, current_state: int | None) -> bool | None:
            return _branch_truth_for_state_or_constant(test, current_state)

        def infer_body(
            body: list[ast.stmt],
            current_state: int | None,
            state_vars: dict[str, int],
            string_by_value_name: dict[str, str],
            nested_payload_by_function: dict[str, bool],
            is_source: bool,
        ) -> bool:
            for stmt in body:
                target, value = assignment_target_and_value(stmt)
                if (
                    isinstance(target, ast.Tuple)
                    and len(target.elts) == 2
                    and isinstance(target.elts[1], ast.Name)
                    and isinstance(value, ast.Call)
                    and isinstance(value.func, ast.Name)
                    and value.func.id in returned_state_by_function
                ):
                    state_vars[target.elts[1].id] = returned_state_by_function[value.func.id]

                if isinstance(target, ast.Name) and target.id == "state":
                    if isinstance(value, ast.Constant) and isinstance(value.value, int):
                        current_state = value.value
                    elif isinstance(value, ast.Name) and value.id in state_vars:
                        current_state = state_vars[value.id]

                value_target_name = first_value_target_name(target)
                if value_target_name is not None:
                    string_name = None
                    if (
                        isinstance(value, ast.Call)
                        and isinstance(value.func, ast.Name)
                        and nested_payload_by_function.get(value.func.id, False)
                    ):
                        string_name = f"{value.func.id}_str"
                    else:
                        string_name = expr_string_name(value, string_by_value_name, nested_payload_by_function)

                    if string_name is None:
                        string_by_value_name.pop(value_target_name, None)
                    else:
                        string_by_value_name[value_target_name] = string_name

                if isinstance(stmt, ast.If):
                    truth = branch_truth(stmt.test, current_state)
                    if truth is not None:
                        return infer_body(
                            stmt.body if truth else stmt.orelse,
                            current_state,
                            dict(state_vars),
                            dict(string_by_value_name),
                            nested_payload_by_function,
                            is_source,
                        )
                    return (
                        infer_body(stmt.body, current_state, dict(state_vars), dict(string_by_value_name), nested_payload_by_function, is_source)
                        or infer_body(stmt.orelse, current_state, dict(state_vars), dict(string_by_value_name), nested_payload_by_function, is_source)
                    )

                if isinstance(stmt, ast.Return):
                    if is_source:
                        return True
                    payload = stmt.value.elts[0] if _is_state_return_tuple(stmt.value) else stmt.value
                    return expr_string_name(payload, string_by_value_name, nested_payload_by_function) is not None

            return False

        nested_payload_by_function: dict[str, bool] = {name: True for name in source_functions}
        for _ in range(len(functions) + 1):
            changed = False
            for name, node in functions.items():
                if name not in tuple_returning_functions:
                    inferred = False
                else:
                    inferred = infer_body(
                        node.body,
                        (active_state_by_function or {}).get(name),
                        {},
                        {},
                        nested_payload_by_function,
                        name in source_functions,
                    )
                if nested_payload_by_function.get(name, False) != inferred:
                    nested_payload_by_function[name] = inferred
                    changed = True
            if not changed:
                break
        return nested_payload_by_function

    def key_annotation(has_state: bool) -> ast.Subscript:
        if has_state:
            return _tuple_annotation(f"tuple[{return_type}, str]", "int")
        return _tuple_annotation(return_type, "str")

    class TupleCallExtractor(ast.NodeTransformer):
        """
        Finds calls to tuple-returning functions inside an expression.

        Replaces:

            f(x)

        with:

            f_val

        and records an assignment:

            f_val, f_str = f(x)
        """

        def __init__(self, nested_payload_by_function: dict[str, bool]):
            self.assignments: list[ast.Assign] = []
            self.string_names: list[str] = []
            self.nested_payload_by_function = nested_payload_by_function

        def visit_Call(self, node: ast.Call):
            self.generic_visit(node)

            if not isinstance(node.func, ast.Name):
                return node

            if node.func.id not in tuple_returning_functions:
                return node

            base = node.func.id

            val_name = f"{base}_val"
            str_name = f"{base}_str"

            if self.nested_payload_by_function.get(base, False):
                self.assignments.append(
                    ast.Assign(
                        targets=[
                            ast.Tuple(
                                elts=[
                                    ast.Name(id=val_name, ctx=ast.Store()),
                                    ast.Name(id=str_name, ctx=ast.Store()),
                                ],
                                ctx=ast.Store(),
                            )
                        ],
                        value=node,
                    )
                )
                self.string_names.append(str_name)

            return ast.Name(id=val_name, ctx=ast.Load())

    class Transformer(ast.NodeTransformer):
        def __init__(self, returned_state_by_function: dict[str, int], nested_payload_by_function: dict[str, bool]):
            self.tracker = _ActiveBranchTracker()
            self.returned_state_by_function = returned_state_by_function
            self.nested_payload_by_function = nested_payload_by_function
            self.state_vars: dict[str, int] = {}
            self.string_by_value_name: dict[str, str] = {}

        def assignment_parts(self, stmt: ast.stmt) -> tuple[ast.expr | None, ast.expr | None]:
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                return stmt.targets[0], stmt.value
            if isinstance(stmt, ast.AnnAssign):
                return stmt.target, stmt.value
            return None, None

        def record_state_flow(self, stmt: ast.stmt) -> None:
            target, value = self.assignment_parts(stmt)
            if (
                isinstance(target, ast.Tuple)
                and len(target.elts) == 2
                and isinstance(target.elts[1], ast.Name)
                and isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id in self.returned_state_by_function
            ):
                self.state_vars[target.elts[1].id] = self.returned_state_by_function[value.func.id]

            if isinstance(target, ast.Name) and target.id == "state":
                if isinstance(value, ast.Constant) and isinstance(value.value, int):
                    self.tracker.current_state = value.value
                elif isinstance(value, ast.Name) and value.id in self.state_vars:
                    self.tracker.current_state = self.state_vars[value.id]

        def transform_call_assignment(self, stmt: ast.Assign) -> bool:
            if (
                not isinstance(stmt.value, ast.Call)
                or not isinstance(stmt.value.func, ast.Name)
            ):
                return False

            base = stmt.value.func.id
            if base not in tuple_returning_functions:
                return False

            self.record_state_flow(stmt)
            if not self.tracker.is_active_path():
                return True

            target = stmt.targets[0] if len(stmt.targets) == 1 else None
            if not self.nested_payload_by_function.get(base, False):
                value_name = first_value_target_name(target)
                if value_name is not None:
                    self.string_by_value_name.pop(value_name, None)
                return True

            str_name = f"{base}_str"
            if (
                isinstance(target, ast.Tuple)
                and len(target.elts) == 2
                and not isinstance(target.elts[0], ast.Tuple)
            ):
                first_target = target.elts[0]
                state_target = target.elts[1]
                stmt.targets[0] = ast.Tuple(
                    elts=[
                        ast.Tuple(
                            elts=[first_target, ast.Name(id=str_name, ctx=ast.Store())],
                            ctx=ast.Store(),
                        ),
                        state_target,
                    ],
                    ctx=ast.Store(),
                )
                value_name = first_value_target_name(first_target)
                if value_name is not None:
                    self.string_by_value_name[value_name] = str_name
                return True

            if isinstance(target, ast.Name):
                value_name = target.id
                stmt.targets[0] = ast.Tuple(
                    elts=[
                        ast.Name(id=value_name, ctx=ast.Store()),
                        ast.Name(id=str_name, ctx=ast.Store()),
                    ],
                    ctx=ast.Store(),
                )
                self.string_by_value_name[value_name] = str_name
                return True

            return True

        def record_value_flow(self, stmt: ast.stmt) -> None:
            target, value = self.assignment_parts(stmt)
            value_name = first_value_target_name(target)
            if value_name is None:
                return
            string_name = expr_string_name(value, self.string_by_value_name, self.nested_payload_by_function)
            if string_name is None:
                self.string_by_value_name.pop(value_name, None)
            else:
                self.string_by_value_name[value_name] = string_name

        def transform_body(
            self,
            body: list[ast.stmt],
            is_source: bool,
            wrap_returns: bool,
            inherited_str_name: str | None = None,
        ) -> tuple[list[ast.stmt], str | None]:
            new_body: list[ast.stmt] = []
            latest_str_name: str | None = inherited_str_name

            for stmt in body:
                if isinstance(stmt, ast.If):
                    truth = self.tracker.branch_truth(stmt.test)
                    previous_state = self.tracker.current_state
                    previous_state_vars = dict(self.state_vars)
                    previous_string_by_value_name = dict(self.string_by_value_name)
                    if truth is None:
                        stmt.body, _ = self.transform_body(stmt.body, is_source, wrap_returns, latest_str_name)
                        self.tracker.current_state = previous_state
                        self.state_vars = dict(previous_state_vars)
                        self.string_by_value_name = dict(previous_string_by_value_name)
                        stmt.orelse, _ = self.transform_body(stmt.orelse, is_source, wrap_returns, latest_str_name)
                        self.tracker.current_state = previous_state
                        self.state_vars = dict(previous_state_vars)
                        self.string_by_value_name = dict(previous_string_by_value_name)
                    else:
                        self.tracker.active_stack.append(truth)
                        stmt.body, _ = self.transform_body(stmt.body, is_source, wrap_returns, latest_str_name)
                        self.tracker.active_stack.pop()
                        self.tracker.current_state = previous_state
                        self.state_vars = dict(previous_state_vars)
                        self.string_by_value_name = dict(previous_string_by_value_name)
                        self.tracker.active_stack.append(not truth)
                        stmt.orelse, _ = self.transform_body(stmt.orelse, is_source, wrap_returns, latest_str_name)
                        self.tracker.active_stack.pop()
                        self.tracker.current_state = previous_state
                        self.state_vars = dict(previous_state_vars)
                        self.string_by_value_name = dict(previous_string_by_value_name)
                    new_body.append(stmt)
                    continue

                if isinstance(stmt, ast.Assign) and self.transform_call_assignment(stmt):
                    new_body.append(stmt)
                    continue

                if isinstance(stmt, ast.Return) and stmt.value is not None:
                    if not self.tracker.is_active_path():
                        new_body.append(stmt)
                        continue

                    if is_source and wrap_returns:
                        stmt.value = _wrap_return_payload(
                            stmt.value,
                            lambda value: ast.Call(
                                func=ast.Name(id="external", ctx=ast.Load()),
                                args=[value],
                                keywords=[],
                            ),
                        )
                        new_body.append(stmt)
                        continue

                    extractor = TupleCallExtractor(self.nested_payload_by_function)
                    payload = stmt.value.elts[0] if _is_state_return_tuple(stmt.value) else stmt.value
                    new_payload = extractor.visit(copy.deepcopy(payload))
                    if extractor.assignments:
                        new_body.extend(extractor.assignments)
                        latest_str_name = extractor.string_names[0]

                    if not wrap_returns:
                        if _is_state_return_tuple(stmt.value):
                            stmt.value = ast.Tuple(
                                elts=[new_payload, stmt.value.elts[1]],
                                ctx=ast.Load(),
                            )
                        else:
                            stmt.value = new_payload
                        new_body.append(stmt)
                        continue

                    string_name = expr_string_name(new_payload, self.string_by_value_name, self.nested_payload_by_function)
                    if string_name is not None:
                        latest_str_name = string_name

                    if latest_str_name is None:
                        new_body.append(stmt)
                        continue

                    pair = ast.Tuple(
                        elts=[
                            new_payload,
                            ast.Name(id=latest_str_name, ctx=ast.Load()),
                        ],
                        ctx=ast.Load(),
                    )
                    if _is_state_return_tuple(stmt.value):
                        stmt.value = ast.Tuple(
                            elts=[pair, stmt.value.elts[1]],
                            ctx=ast.Load(),
                        )
                    else:
                        stmt.value = pair
                    new_body.append(stmt)
                    continue

                new_body.append(stmt)
                self.record_state_flow(stmt)
                self.record_value_flow(stmt)

            return new_body, latest_str_name

        def visit_FunctionDef(self, node: ast.FunctionDef):
            if node.name == "main":
                return node

            previous_state = self.tracker.current_state
            previous_active_stack = self.tracker.active_stack
            previous_state_vars = self.state_vars
            previous_string_by_value_name = self.string_by_value_name
            self.tracker.current_state = (active_state_by_function or {}).get(node.name)
            self.tracker.active_stack = []
            self.state_vars = {}
            self.string_by_value_name = {}

            if node.name in tuple_returning_functions:
                has_state = _function_returns_state(node)
                node.returns = key_annotation(has_state)
            node.body, _ = self.transform_body(
                node.body,
                node.name in source_functions,
                node.name in tuple_returning_functions,
            )

            self.tracker.current_state = previous_state
            self.tracker.active_stack = previous_active_stack
            self.state_vars = previous_state_vars
            self.string_by_value_name = previous_string_by_value_name
            return node

    tree = ast.parse(source)
    returned_state_by_function = infer_return_states(tree)
    nested_payload_by_function = infer_nested_payloads(tree, returned_state_by_function)
    tree = Transformer(returned_state_by_function, nested_payload_by_function).visit(tree)
    ast.fix_missing_locations(tree)
    return _unparse(tree)


def seed_return_value(
    source: str,
    source_functions: set[str],
    active_state_by_function: dict[str, int] | None = None,
) -> str:
    class ReturnValueSeeder(ast.NodeTransformer):
        def __init__(self):
            self.current_function: str | None = None
            self.tracker = _ActiveBranchTracker()

        def visit_FunctionDef(self, node: ast.FunctionDef):
            if node.name == "main":
                return node

            previous_function = self.current_function
            previous_state = self.tracker.current_state
            previous_active_stack = self.tracker.active_stack
            self.current_function = node.name
            self.tracker.current_state = (active_state_by_function or {}).get(node.name)
            self.tracker.active_stack = []
            node.body = self.transform_body(node.body)
            self.current_function = previous_function
            self.tracker.current_state = previous_state
            self.tracker.active_stack = previous_active_stack
            return node

        def transform_body(self, body: list[ast.stmt]) -> list[ast.stmt]:
            new_body: list[ast.stmt] = []
            for stmt in body:
                if isinstance(stmt, ast.If):
                    truth = self.tracker.branch_truth(stmt.test)
                    previous_state = self.tracker.current_state
                    if truth is None:
                        stmt.body = self.transform_body(stmt.body)
                        self.tracker.current_state = previous_state
                        stmt.orelse = self.transform_body(stmt.orelse)
                        self.tracker.current_state = previous_state
                    else:
                        self.tracker.active_stack.append(truth)
                        stmt.body = self.transform_body(stmt.body)
                        self.tracker.active_stack.pop()
                        self.tracker.current_state = previous_state
                        self.tracker.active_stack.append(not truth)
                        stmt.orelse = self.transform_body(stmt.orelse)
                        self.tracker.active_stack.pop()
                        self.tracker.current_state = previous_state
                    new_body.append(stmt)
                    continue

                if (
                    isinstance(stmt, ast.Return)
                    and stmt.value is not None
                    and self.current_function in source_functions
                    and self.tracker.is_active_path()
                ):
                    payload = stmt.value.elts[0] if _is_state_return_tuple(stmt.value) else stmt.value
                    state_value = stmt.value.elts[1] if _is_state_return_tuple(stmt.value) else None
                    external_call = ast.copy_location(
                        ast.Call(
                            func=ast.Name(id="external", ctx=ast.Load()),
                            args=[payload],
                            keywords=[],
                        ),
                        stmt.value,
                    )
                    if state_value is None:
                        stmt.value = external_call
                    else:
                        stmt.value = ast.Tuple(
                            elts=[external_call, state_value],
                            ctx=ast.Load(),
                        )
                    new_body.append(stmt)
                    continue

                new_body.append(stmt)
                self.tracker.visit_state_assignment(stmt)
            return new_body

    tree = ast.parse(source)
    tree = ReturnValueSeeder().visit(tree)
    ast.fix_missing_locations(tree)
    return _unparse(tree)

def wrap_functions_with_mult_only_terminal(
    source: str,
    function_names: set[str],
    return_type: str,
    parameter: str,
    helper_type: str = None,
    active_state_by_function: dict[str, int] | None = None,
    terminal_wrap_function_names: set[str] | None = None,
) -> str:
    if helper_type is None:
        helper_type = return_type
    tree = ast.parse(source)
    if terminal_wrap_function_names is None:
        terminal_wrap_function_names = set(function_names)

    file_functions = {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }

    accepts_mult = {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and (
            node.name in function_names
            or any(arg.arg == parameter for arg in node.args.args)
        )
    }

    def is_terminal(expr) -> bool:
        for sub in ast.walk(expr):
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Name)
                and sub.func.id in file_functions
            ):
                return False
        return True

    class WrapSelectedReturns(ast.NodeTransformer):
        class MultPropagator(ast.NodeTransformer):
            def __init__(self, active_state: int | None = None):
                self.active_state = active_state
                self.current_state: int | None = active_state
                self.active_stack: list[bool] = []

            def branch_truth(self, test: ast.expr) -> bool | None:
                return _branch_truth_for_state_or_constant(test, self.current_state)

            def visit_Assign(self, node: ast.Assign):
                self.generic_visit(node)
                if (
                    len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                    and node.targets[0].id == "state"
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, int)
                ):
                    self.current_state = node.value.value
                return node

            def visit_AnnAssign(self, node: ast.AnnAssign):
                self.generic_visit(node)
                if (
                    isinstance(node.target, ast.Name)
                    and node.target.id == "state"
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, int)
                ):
                    self.current_state = node.value.value
                return node

            def visit_If(self, node: ast.If):
                truth = self.branch_truth(node.test)
                self.visit(node.test)
                if truth is None:
                    node.body = [self.visit(stmt) for stmt in node.body]
                    node.orelse = [self.visit(stmt) for stmt in node.orelse]
                    return node

                self.active_stack.append(truth)
                node.body = [self.visit(stmt) for stmt in node.body]
                self.active_stack.pop()
                self.active_stack.append(not truth)
                node.orelse = [self.visit(stmt) for stmt in node.orelse]
                self.active_stack.pop()
                return node

            def visit_Call(self, node: ast.Call):
                self.generic_visit(node)

                if self.active_stack and not all(self.active_stack):
                    return node

                if not isinstance(node.func, ast.Name):
                    return node

                if node.func.id not in accepts_mult:
                    return node

                if any(kw.arg == parameter for kw in node.keywords):
                    return node

                node.keywords.append(
                    ast.keyword(
                        arg=parameter,
                        value=ast.Name(parameter, ast.Load()),
                    )
                )
                return node

        def visit_FunctionDef(self, node):
            if node.name not in function_names:
                return self.generic_visit(node)

            _add_default_parameter_to_function(node, parameter, helper_type)
            active_state = (active_state_by_function or {}).get(node.name)
            propagator = self.MultPropagator(active_state)
            node.body = [propagator.visit(stmt) for stmt in node.body]

            if node.name not in terminal_wrap_function_names:
                return node

            class ReturnWrapper(ast.NodeTransformer):
                def __init__(self, active_state: int | None):
                    self.current_state: int | None = active_state
                    self.active_stack: list[bool] = []

                def visit_FunctionDef(self, inner_node: ast.FunctionDef):
                    return inner_node

                def branch_truth(self, test: ast.expr) -> bool | None:
                    return _branch_truth_for_state_or_constant(test, self.current_state)

                def visit_Assign(self, node: ast.Assign):
                    self.generic_visit(node)
                    if (
                        len(node.targets) == 1
                        and isinstance(node.targets[0], ast.Name)
                        and node.targets[0].id == "state"
                        and isinstance(node.value, ast.Constant)
                        and isinstance(node.value.value, int)
                    ):
                        self.current_state = node.value.value
                    return node

                def visit_AnnAssign(self, node: ast.AnnAssign):
                    self.generic_visit(node)
                    if (
                        isinstance(node.target, ast.Name)
                        and node.target.id == "state"
                        and isinstance(node.value, ast.Constant)
                        and isinstance(node.value.value, int)
                    ):
                        self.current_state = node.value.value
                    return node

                def visit_If(self, node: ast.If):
                    truth = self.branch_truth(node.test)
                    self.visit(node.test)
                    if truth is None:
                        node.body = [self.visit(stmt) for stmt in node.body]
                        node.orelse = [self.visit(stmt) for stmt in node.orelse]
                        return node

                    self.active_stack.append(truth)
                    node.body = [self.visit(stmt) for stmt in node.body]
                    self.active_stack.pop()
                    self.active_stack.append(not truth)
                    node.orelse = [self.visit(stmt) for stmt in node.orelse]
                    self.active_stack.pop()
                    return node

                def visit_Return(self, return_node: ast.Return):
                    if return_node.value is None:
                        return return_node
                    if self.active_stack and not all(self.active_stack):
                        return return_node
                    payload = return_node.value.elts[0] if _is_state_return_tuple(return_node.value) else return_node.value
                    if not is_terminal(payload):
                        return return_node

                    def wrap(value: ast.expr) -> ast.expr:
                        return ast.BinOp(
                            left=ast.Name(parameter, ast.Load()),
                            op=ast.Add() if return_type == "str" else ast.Mult(),
                            right=value,
                        )

                    return_node.value = _wrap_return_payload(return_node.value, wrap)
                    return return_node

            node.body = [ReturnWrapper(active_state).visit(stmt) for stmt in node.body]
            return node

    tree = WrapSelectedReturns().visit(tree)
    ast.fix_missing_locations(tree)
    return _unparse(tree)

def wrap_function_return_with_slow(
    source: str,
    target_function_name: str,
    active_state_by_function: dict[str, int] | None = None,
    active_only: bool = True,
) -> str:
    class SlowReturnAdder(ast.NodeTransformer):
        def visit_FunctionDef(self, node: ast.FunctionDef):
            if node.name != target_function_name:
                return self.generic_visit(node)

            class ReturnWrapper(ast.NodeTransformer):
                def __init__(self, active_state: int | None):
                    self.tracker = _ActiveBranchTracker(active_state)

                def visit_FunctionDef(self, inner_node: ast.FunctionDef):
                    return inner_node

                def visit_Assign(self, node: ast.Assign):
                    self.generic_visit(node)
                    self.tracker.visit_state_assignment(node)
                    return node

                def visit_AnnAssign(self, node: ast.AnnAssign):
                    self.generic_visit(node)
                    self.tracker.visit_state_assignment(node)
                    return node

                def visit_If(self, node: ast.If):
                    truth = self.tracker.branch_truth(node.test)
                    self.visit(node.test)
                    if truth is None:
                        node.body = [self.visit(stmt) for stmt in node.body]
                        node.orelse = [self.visit(stmt) for stmt in node.orelse]
                        return node

                    self.tracker.active_stack.append(truth)
                    node.body = [self.visit(stmt) for stmt in node.body]
                    self.tracker.active_stack.pop()
                    self.tracker.active_stack.append(not truth)
                    node.orelse = [self.visit(stmt) for stmt in node.orelse]
                    self.tracker.active_stack.pop()
                    return node

                def visit_Return(self, return_node: ast.Return):
                    if return_node.value is None:
                        return return_node
                    if active_only and not self.tracker.is_active_path():
                        return return_node

                    def wrap(value: ast.expr) -> ast.expr:
                        return ast.BinOp(
                            left=ast.Call(
                                func=ast.Name(id="slow", ctx=ast.Load()),
                                args=[],
                                keywords=[],
                            ),
                            op=ast.Add(),
                            right=value,
                        )

                    return_node.value = _wrap_return_payload(return_node.value, wrap)
                    return return_node

            active_state = (active_state_by_function or {}).get(node.name)
            node.body = [ReturnWrapper(active_state).visit(stmt) for stmt in node.body]
            return node

    tree = ast.parse(source)
    tree = SlowReturnAdder().visit(tree)
    ast.fix_missing_locations(tree)
    return _unparse(tree)


def retrieve_multiplier_for_function(
    source_code: str,
    function_name: str,
    get_multiplier_func: str,
    return_type: str,
    var_name: str,
    active_state_by_function: dict[str, int] | None = None,
    active_only: bool = True,
    branch_local: bool = False,
) -> str:
    class AddHelperValue(ast.NodeTransformer):
        def visit_FunctionDef(self, node: ast.FunctionDef):
            if node.name != function_name:
                return self.generic_visit(node)

            def make_mult_assignment() -> ast.AnnAssign:
                return ast.AnnAssign(
                    target=ast.Name(id=var_name, ctx=ast.Store()),
                    annotation=ast.Name(id=return_type, ctx=ast.Load()),
                    value=ast.Call(
                        func=ast.Name(id=get_multiplier_func, ctx=ast.Load()),
                        args=[ast.Name(id="val", ctx=ast.Load())],
                        keywords=[],
                    ),
                    simple=1,
                )

            def wrap_return(return_node: ast.Return) -> ast.Return:
                if return_node.value is None:
                    return return_node

                def wrap(value: ast.expr) -> ast.expr:
                    return ast.BinOp(
                        left=ast.Name(id=var_name, ctx=ast.Load()),
                        op=ast.Add() if return_type == "str" else ast.Mult(),
                        right=value,
                    )

                return_node.value = _wrap_return_payload(return_node.value, wrap)
                return return_node

            if branch_local:
                tracker = _ActiveBranchTracker((active_state_by_function or {}).get(node.name))

                def transform_body(body: list[ast.stmt]) -> list[ast.stmt]:
                    new_body: list[ast.stmt] = []
                    for stmt in body:
                        if isinstance(stmt, ast.If):
                            truth = tracker.branch_truth(stmt.test)
                            if truth is None:
                                stmt.body = transform_body(stmt.body)
                                stmt.orelse = transform_body(stmt.orelse)
                                new_body.append(stmt)
                                continue

                            tracker.active_stack.append(truth)
                            stmt.body = transform_body(stmt.body)
                            tracker.active_stack.pop()
                            tracker.active_stack.append(not truth)
                            stmt.orelse = transform_body(stmt.orelse)
                            tracker.active_stack.pop()
                            new_body.append(stmt)
                            continue

                        if isinstance(stmt, ast.Return):
                            if not active_only or tracker.is_active_path():
                                new_body.append(make_mult_assignment())
                                new_body.append(wrap_return(stmt))
                            else:
                                new_body.append(stmt)
                            continue

                        new_body.append(stmt)
                        tracker.visit_state_assignment(stmt)
                    return new_body

                node.body = transform_body(node.body)
                return node

            # Insert: mult = get_multiplier(val)
            node.body.insert(0, make_mult_assignment())

            class ReturnWrapper(ast.NodeTransformer):
                def visit_FunctionDef(self, inner_node: ast.FunctionDef):
                    return inner_node

                def visit_Return(self, return_node: ast.Return):
                    if return_node.value is None:
                        return return_node

                    def wrap(value: ast.expr) -> ast.expr:
                        return ast.BinOp(
                            left=ast.Name(id=var_name, ctx=ast.Load()),
                            op=ast.Add() if return_type == "str" else ast.Mult(),
                            right=value,
                        )

                    return_node.value = _wrap_return_payload(return_node.value, wrap)
                    return return_node

            node.body = [ReturnWrapper().visit(stmt) for stmt in node.body]

            return node

    tree = ast.parse(source_code)
    tree = AddHelperValue().visit(tree)
    ast.fix_missing_locations(tree)
    return _unparse(tree)

def move_multiplier_down_to_shared_node(
    source_code: str,
    ancestor_nodes: list[str],
    shared_node: str,
    affected_nodes: set[str],
    top_nodes: set[str],
    value_temp_name: str = "temp",
    mult_name: str = "mult",
    get_multiplier_func: str = "get_multiplier",
    return_type: str = "float",
    helper_type: str = None,
    active_state_by_function: dict[str, int] | None = None,
    branch_local: bool = False,
) -> str:
    if helper_type is None:
        helper_type = return_type
    ancestor_nodes = list(ancestor_nodes)
    affected_nodes = set(affected_nodes)
    top_nodes = set(top_nodes)

    affected_nodes.update(ancestor_nodes)
    affected_nodes.add(shared_node)
    affected_nodes.update(top_nodes)
    tuple_returning_nodes = affected_nodes - top_nodes

    tree = ast.parse(source_code)

    def is_get_multiplier_call(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == get_multiplier_func
        )

    def contains_get_multiplier(node: ast.AST) -> bool:
        return any(is_get_multiplier_call(child) for child in ast.walk(node))

    def tuple_float_float_annotation() -> ast.Subscript:
        return _tuple_annotation(return_type, helper_type)

    def tuple_value_helper_state_annotation() -> ast.Subscript:
        return _tuple_annotation(f"tuple[{return_type}, {helper_type}]", "int")

    def make_mult_assignment() -> ast.AnnAssign:
        return ast.AnnAssign(
            target=ast.Name(id=mult_name, ctx=ast.Store()),
            annotation=ast.Name(id=helper_type, ctx=ast.Load()),
            value=ast.Call(
                func=ast.Name(id=get_multiplier_func, ctx=ast.Load()),
                args=[ast.Name(id="val", ctx=ast.Load())],
                keywords=[],
            ),
            simple=1,
        )

    def make_tuple_call_target(target: ast.expr, helper_target: ast.expr) -> ast.expr:
        if isinstance(target, ast.Name):
            return ast.Tuple(
                elts=[target, helper_target],
                ctx=ast.Store(),
            )
        if isinstance(target, ast.Tuple) and len(target.elts) == 2:
            return ast.Tuple(
                elts=[
                    ast.Tuple(
                        elts=[target.elts[0], helper_target],
                        ctx=ast.Store(),
                    ),
                    target.elts[1],
                ],
                ctx=ast.Store(),
            )
        return target

    def is_tuple_returning_call(value: ast.expr) -> bool:
        return (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id in tuple_returning_nodes
        )

    def make_tuple_return(value_expr: ast.expr) -> ast.Return:
        return ast.Return(value=make_tuple_value(value_expr))

    def make_tuple_value(value_expr: ast.expr) -> ast.expr:
        pair = ast.Tuple(
            elts=[value_expr, ast.Name(id=mult_name, ctx=ast.Load())],
            ctx=ast.Load(),
        )
        if _is_state_return_tuple(value_expr):
            pair = ast.Tuple(
                elts=[value_expr.elts[0], ast.Name(id=mult_name, ctx=ast.Load())],
                ctx=ast.Load(),
            )
            return ast.Tuple(elts=[pair, value_expr.elts[1]], ctx=ast.Load())
        return pair

    def make_computed_return(value_expr: ast.expr, return_type: str) -> ast.Return:
        return ast.Return(value=make_computed_value(value_expr, return_type))

    def make_computed_value(value_expr: ast.expr, return_type: str) -> ast.expr:
        def wrap(value: ast.expr) -> ast.expr:
            return ast.BinOp(
                left=ast.Name(id=mult_name, ctx=ast.Load()),
                op=ast.Add() if return_type == "str" else ast.Mult(),
                right=value,
            )

        return _wrap_return_payload(value_expr, wrap)

    def strip_existing_helper_application(value_expr: ast.expr) -> ast.expr:
        def strip(value: ast.expr) -> ast.expr:
            if (
                isinstance(value, ast.BinOp)
                and isinstance(value.left, ast.Name)
                and value.left.id == mult_name
                and isinstance(value.op, ast.Add if return_type == "str" else ast.Mult)
            ):
                return value.right
            return value

        if _is_state_return_tuple(value_expr):
            return ast.Tuple(
                elts=[strip(value_expr.elts[0]), value_expr.elts[1]],
                ctx=ast.Load(),
            )
        return strip(value_expr)

    class TupleCallHoister(ast.NodeTransformer):
        """
        Rewrites one affected child call inside a return expression.

        Example:
            return child(val) + 1

        becomes:
            temp, mult = child(val)
            return temp + 1, mult

        Or, if this function is a top node:
            temp, mult = child(val)
            return (temp + 1) * mult
        """

        def __init__(self):
            self.matches: list[ast.Call] = []

        def visit_Call(self, node: ast.Call):
            self.generic_visit(node)

            if (
                isinstance(node.func, ast.Name)
                and node.func.id in affected_nodes
            ):
                self.matches.append(node)
                return ast.Name(id=value_temp_name, ctx=ast.Load())

            return node

    class MoveMultiplierDown(ast.NodeTransformer):
        def __init__(self):
            self.current_state: int | None = None
            self.active_stack: list[bool] = []

        def is_active_path(self) -> bool:
            return not self.active_stack or all(self.active_stack)

        def branch_truth(self, test: ast.expr) -> bool | None:
            return _branch_truth_for_state_or_constant(test, self.current_state)

        def visit_state_assignment(self, stmt: ast.stmt) -> None:
            value = None
            target = None
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                target = stmt.targets[0]
                value = stmt.value
            elif isinstance(stmt, ast.AnnAssign):
                target = stmt.target
                value = stmt.value
            if (
                isinstance(target, ast.Name)
                and target.id == "state"
                and isinstance(value, ast.Constant)
                and isinstance(value.value, int)
            ):
                self.current_state = value.value

        def transform_body(
            self,
            body: list[ast.stmt],
            node_name: str,
            is_top_node: bool,
            found_mult_in_assignment: bool = False,
        ) -> tuple[list[ast.stmt], bool]:
            new_body: list[ast.stmt] = []
            found_mult = found_mult_in_assignment

            for stmt in body:
                if isinstance(stmt, ast.If):
                    truth = self.branch_truth(stmt.test)
                    if truth is None:
                        stmt.body, _ = self.transform_body(
                            stmt.body,
                            node_name,
                            is_top_node,
                            found_mult,
                        )
                        stmt.orelse, _ = self.transform_body(
                            stmt.orelse,
                            node_name,
                            is_top_node,
                            found_mult,
                        )
                        new_body.append(stmt)
                        continue

                    self.active_stack.append(truth)
                    stmt.body, _ = self.transform_body(
                        stmt.body,
                        node_name,
                        is_top_node,
                        found_mult,
                    )
                    self.active_stack.pop()
                    self.active_stack.append(not truth)
                    stmt.orelse, _ = self.transform_body(
                        stmt.orelse,
                        node_name,
                        is_top_node,
                        found_mult,
                    )
                    self.active_stack.pop()
                    new_body.append(stmt)
                    continue

                if not isinstance(stmt, ast.Return) or stmt.value is None:
                    if (
                        self.is_active_path()
                        and (node_name in ancestor_nodes or is_top_node)
                        and (
                            (
                                isinstance(stmt, ast.Expr)
                                and contains_get_multiplier(stmt.value)
                            )
                            or (
                                isinstance(stmt, ast.Assign)
                                and contains_get_multiplier(stmt.value)
                            )
                            or (
                                isinstance(stmt, ast.AnnAssign)
                                and stmt.value is not None
                                and contains_get_multiplier(stmt.value)
                            )
                        )
                    ):
                        continue

                    if (
                        self.is_active_path()
                        and
                        node_name != shared_node
                        and isinstance(stmt, ast.Assign)
                        and len(stmt.targets) == 1
                        and is_tuple_returning_call(stmt.value)
                    ):
                        str_target = ast.Name(id=mult_name, ctx=ast.Store())
                        target = stmt.targets[0]
                        stmt.targets[0] = make_tuple_call_target(target, str_target)
                        new_body.append(stmt)
                        found_mult = True
                    else:
                        new_body.append(stmt)
                    self.visit_state_assignment(stmt)
                    continue

                if not self.is_active_path():
                    new_body.append(stmt)
                    continue

                if node_name == shared_node:
                    if is_top_node:
                        new_body.append(make_computed_return(stmt.value, return_type))
                    else:
                        new_body.append(make_tuple_return(stmt.value))
                    continue

                if found_mult:
                    value = strip_existing_helper_application(stmt.value)
                    if is_top_node:
                        new_body.append(make_computed_return(value, return_type))
                    else:
                        new_body.append(make_tuple_return(value))
                    continue

                hoister = TupleCallHoister()
                new_return_value = hoister.visit(stmt.value)

                if len(hoister.matches) == 0:
                    if node_name != shared_node:
                        new_body.append(make_mult_assignment())
                    if is_top_node:
                        new_body.append(make_computed_return(new_return_value, return_type))
                    else:
                        new_body.append(make_tuple_return(new_return_value))
                    continue

                if len(hoister.matches) > 1:
                    matched_names = [
                        m.func.id for m in hoister.matches
                        if isinstance(m.func, ast.Name)
                    ]
                    raise ValueError(
                        f"Function {node_name!r} has multiple affected calls "
                        f"in one return expression. Need a policy for which "
                        f"returned multiplier to propagate.\n"
                        f"  Affected calls found: {matched_names}\n"
                        f"  Return expression: {ast.unparse(stmt.value)}\n"
                        f"  shared_node={shared_node!r}, "
                        f"top_nodes={top_nodes}, "
                        f"affected_nodes={affected_nodes}"
                    )

                affected_call = hoister.matches[0]
                new_body.append(
                    ast.Assign(
                        targets=[
                            ast.Tuple(
                                elts=[
                                    ast.Name(id=value_temp_name, ctx=ast.Store()),
                                    ast.Name(id=mult_name, ctx=ast.Store()),
                                ],
                                ctx=ast.Store(),
                            )
                        ],
                        value=affected_call,
                    )
                )

                if is_top_node:
                    new_body.append(make_computed_return(strip_existing_helper_application(new_return_value), return_type))
                else:
                    new_body.append(make_tuple_return(strip_existing_helper_application(new_return_value)))

            return new_body, found_mult

        def visit_FunctionDef(self, node: ast.FunctionDef):
            if node.name not in affected_nodes:
                return self.generic_visit(node)

            previous_state = self.current_state
            previous_active_stack = self.active_stack
            self.current_state = (active_state_by_function or {}).get(node.name)
            self.active_stack = []

            is_top_node = node.name in top_nodes

            has_state = _function_returns_state(node)

            # Internal affected functions propagate tuple[float, float].
            # Top affected functions consume the tuple and return float.
            if is_top_node:
                node.returns = ast.Name(id=return_type, ctx=ast.Load())
            else:
                node.returns = tuple_value_helper_state_annotation() if has_state else tuple_float_float_annotation()

            # Remove old top-level get_multiplier(...) statements from
            # ancestors/top nodes. Branch-local helper calls are handled by
            # transform_body so inactive runtime_simple branches can keep them.
            if (active_state_by_function is None) and (node.name in ancestor_nodes or is_top_node):
                node.body = [
                    stmt for stmt in node.body
                    if not (
                        (
                            isinstance(stmt, ast.Expr)
                            and contains_get_multiplier(stmt.value)
                        )
                        or (
                            isinstance(stmt, ast.Assign)
                            and contains_get_multiplier(stmt.value)
                        )
                        or (
                            isinstance(stmt, ast.AnnAssign)
                            and stmt.value is not None
                            and contains_get_multiplier(stmt.value)
                        )
                    )
                ]

            prefix_body: list[ast.stmt] = []

            # Only the shared node computes mult.
            if node.name == shared_node:
                prefix_body.append(make_mult_assignment())

            transformed_body, _ = self.transform_body(node.body, node.name, is_top_node)
            if node.name == shared_node and branch_local:
                # runtime_simple: define mult inside the running branch, not at
                # the top of the function (matching the prompt).
                walk_tracker = _ActiveBranchTracker(
                    (active_state_by_function or {}).get(node.name)
                )
                if not _insert_stmt_at_active_leaf(
                    transformed_body, make_mult_assignment(), walk_tracker
                ):
                    transformed_body.insert(0, make_mult_assignment())
                node.body = transformed_body
            else:
                node.body = prefix_body + transformed_body
            self.current_state = previous_state
            self.active_stack = previous_active_stack
            return node

    new_tree = MoveMultiplierDown().visit(tree)

    class TupleReturningCallSiteFixer(ast.NodeTransformer):
        def __init__(self):
            self.tracker = _ActiveBranchTracker()

        def visit_FunctionDef(self, node: ast.FunctionDef):
            if node.name in affected_nodes:
                return node
            previous_state = self.tracker.current_state
            previous_active_stack = self.tracker.active_stack
            self.tracker.current_state = (active_state_by_function or {}).get(node.name)
            self.tracker.active_stack = []
            node.body = [self.visit(stmt) for stmt in node.body]
            self.tracker.current_state = previous_state
            self.tracker.active_stack = previous_active_stack
            return node

        def visit_If(self, node: ast.If):
            truth = self.tracker.branch_truth(node.test)
            self.visit(node.test)
            previous_state = self.tracker.current_state
            if truth is None:
                node.body = [self.visit(stmt) for stmt in node.body]
                self.tracker.current_state = previous_state
                node.orelse = [self.visit(stmt) for stmt in node.orelse]
                self.tracker.current_state = previous_state
                return node

            self.tracker.active_stack.append(truth)
            node.body = [self.visit(stmt) for stmt in node.body]
            self.tracker.active_stack.pop()
            self.tracker.current_state = previous_state
            self.tracker.active_stack.append(not truth)
            node.orelse = [self.visit(stmt) for stmt in node.orelse]
            self.tracker.active_stack.pop()
            self.tracker.current_state = previous_state
            return node

        def visit_Assign(self, node: ast.Assign):
            self.generic_visit(node)
            self.tracker.visit_state_assignment(node)
            if not self.tracker.is_active_path():
                return node
            if len(node.targets) != 1 or not is_tuple_returning_call(node.value):
                return node
            node.targets[0] = make_tuple_call_target(
                node.targets[0],
                ast.Name(id="_", ctx=ast.Store()),
            )
            return node

    new_tree = TupleReturningCallSiteFixer().visit(new_tree)
    ast.fix_missing_locations(new_tree)
    return _unparse(new_tree)


def move_slow_to_ancestor(
    source_code: str,
    ancestor_node: str,
    target_nodes: list[str],
    affected_nodes: set[str],
    temp_name: str = "temp",
    param_type: str = "float",
    active_state_by_function: dict[str, int] | None = None,
    branch_local: bool = False,
) -> str:
    _task_type_to_annotation = {
        "math": "float",
        "string": "str",
        "array": "float",
    }
    param_type = _task_type_to_annotation.get(param_type, param_type)
    default_value = ast.Constant(value="" if param_type == "str" else 0.0)

    target_nodes = list(target_nodes)
    affected_nodes = set(affected_nodes)
    affected_nodes.update(target_nodes)

    tree = ast.parse(source_code)

    class Rewriter(ast.NodeTransformer):
        def __init__(self):
            self.current_function_name = None
            self.tracker = _ActiveBranchTracker()

        def visit_FunctionDef(self, node: ast.FunctionDef):
            previous_function_name = self.current_function_name
            previous_state = self.tracker.current_state
            previous_active_stack = self.tracker.active_stack
            self.current_function_name = node.name
            self.tracker.current_state = (active_state_by_function or {}).get(node.name)
            self.tracker.active_stack = []

            self.generic_visit(node)

            # 1. ancestor_node stores slow() once:
            #    temp: float = slow()
            if node.name == ancestor_node:
                temp_stmt = ast.AnnAssign(
                    target=ast.Name(id=temp_name, ctx=ast.Store()),
                    annotation=ast.Name(id=param_type, ctx=ast.Load()),
                    value=ast.Call(
                        func=ast.Name(id="slow", ctx=ast.Load()),
                        args=[],
                        keywords=[],
                    ),
                    simple=1,
                )
                if branch_local:
                    walk_tracker = _ActiveBranchTracker(
                        (active_state_by_function or {}).get(node.name)
                    )
                    if not _insert_stmt_at_active_leaf(
                        node.body, temp_stmt, walk_tracker
                    ):
                        node.body.insert(0, temp_stmt)
                else:
                    node.body.insert(0, temp_stmt)

            # 2. affected nodes accept temp as a parameter.
            if node.name in affected_nodes and node.name != ancestor_node:
                if not any(arg.arg == temp_name for arg in node.args.args):
                    node.args.args.append(
                        ast.arg(
                            arg=temp_name,
                            annotation=ast.Name(id=param_type, ctx=ast.Load()),
                        )
                    )
                    node.args.defaults.append(copy.deepcopy(default_value))

            self.current_function_name = previous_function_name
            self.tracker.current_state = previous_state
            self.tracker.active_stack = previous_active_stack
            return node

        def visit_If(self, node: ast.If):
            truth = self.tracker.branch_truth(node.test)
            self.visit(node.test)
            previous_state = self.tracker.current_state
            if truth is None:
                node.body = [self.visit(stmt) for stmt in node.body]
                self.tracker.current_state = previous_state
                node.orelse = [self.visit(stmt) for stmt in node.orelse]
                self.tracker.current_state = previous_state
                return node

            self.tracker.active_stack.append(truth)
            node.body = [self.visit(stmt) for stmt in node.body]
            self.tracker.active_stack.pop()
            self.tracker.current_state = previous_state
            self.tracker.active_stack.append(not truth)
            node.orelse = [self.visit(stmt) for stmt in node.orelse]
            self.tracker.active_stack.pop()
            self.tracker.current_state = previous_state
            return node

        def visit_Assign(self, node: ast.Assign):
            self.generic_visit(node)
            self.tracker.visit_state_assignment(node)
            return node

        def visit_AnnAssign(self, node: ast.AnnAssign):
            self.generic_visit(node)
            self.tracker.visit_state_assignment(node)
            return node

        def visit_Call(self, node: ast.Call):
            self.generic_visit(node)

            # 3. Replace slow() with temp only inside target functions.
            if (
                self.current_function_name in target_nodes
                and isinstance(node.func, ast.Name)
                and node.func.id == "slow"
                and len(node.args) == 0
                and len(node.keywords) == 0
                and self.tracker.is_active_path()
            ):
                return ast.Name(id=temp_name, ctx=ast.Load())

            # 4. Pass temp through calls to affected nodes.
            if (
                isinstance(node.func, ast.Name)
                and node.func.id in affected_nodes
                and (
                    self.current_function_name == ancestor_node
                    or self.current_function_name in affected_nodes
                )
                and self.tracker.is_active_path()
            ):
                if not any(
                    isinstance(arg, ast.Name) and arg.id == temp_name
                    for arg in node.args
                ):
                    node.args.append(ast.Name(id=temp_name, ctx=ast.Load()))

            return node

    new_tree = Rewriter().visit(tree)
    ast.fix_missing_locations(new_tree)
    return _unparse(new_tree)

def add_docstrings_to_functions(source: str, docstring_map: dict[str, str]) -> str:
    """Insert a docstring at the top of each function body for functions in *docstring_map*.

    Parameters
    ----------
    source : str
        The full source code.
    docstring_map : dict[str, str]
        Maps function name -> docstring text, without surrounding quotes.

    Returns
    -------
    str
        Updated source with docstrings inserted.
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in docstring_map:
            doc = docstring_map[node.name]
            doc_node = ast.Expr(value=ast.Constant(value=doc))
            node.body.insert(0, doc_node)
    ast.fix_missing_locations(tree)
    return _unparse(tree)


def expand_semantic_category_variants(
    starter_source: str,
    solution_source: str,
    category_docstrings_by_function: dict[str, dict[str, str]],
    target_category: str = "Food",
    seed: int = 0,
) -> tuple[str, str]:
    """Create numbered semantic variants behind each generated function."""

    if not category_docstrings_by_function:
        return starter_source, solution_source

    categories = list(next(iter(category_docstrings_by_function.values())))
    if target_category not in categories:
        raise ValueError(f"Target category {target_category!r} was not sampled")

    starter_tree = ast.parse(starter_source)
    solution_tree = ast.parse(solution_source)
    starter_functions = {
        node.name: node
        for node in starter_tree.body
        if isinstance(node, ast.FunctionDef) and node.name != "main"
    }
    solution_functions = {
        node.name: node
        for node in solution_tree.body
        if isinstance(node, ast.FunctionDef) and node.name != "main"
    }
    original_function_names = set(starter_functions)

    def categories_for_function(name: str) -> list[str]:
        ordered = list(categories)
        random.Random(f"{seed}:{name}:semantic_categories").shuffle(ordered)
        return ordered

    def variant_name(name: str, variant_index: int) -> str:
        return f"{name}{variant_index + 1}"

    def variant_category(name: str, variant_index: int) -> str:
        return categories_for_function(name)[variant_index]

    def target_variant_index(name: str) -> int:
        return categories_for_function(name).index(target_category)

    def with_category_docstring(node: ast.FunctionDef, name: str, variant_index: int) -> ast.FunctionDef:
        node = copy.deepcopy(node)
        category = variant_category(name, variant_index)
        node.name = variant_name(name, variant_index)
        doc_node = ast.Expr(value=ast.Constant(value=category_docstrings_by_function[name][category]))
        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            node.body[0] = doc_node
        else:
            node.body.insert(0, doc_node)
        return node

    def call_arguments(args: ast.arguments) -> tuple[list[ast.expr], list[ast.keyword]]:
        positional_args: list[ast.expr] = [
            ast.Name(id=arg.arg, ctx=ast.Load())
            for arg in args.posonlyargs
        ]
        keywords: list[ast.keyword] = [
            ast.keyword(arg=arg.arg, value=ast.Name(id=arg.arg, ctx=ast.Load()))
            for arg in args.args
        ]
        if args.vararg is not None:
            positional_args.append(
                ast.Starred(value=ast.Name(id=args.vararg.arg, ctx=ast.Load()), ctx=ast.Load())
            )
        keywords.extend(
            ast.keyword(arg=arg.arg, value=ast.Name(id=arg.arg, ctx=ast.Load()))
            for arg in args.kwonlyargs
        )
        if args.kwarg is not None:
            keywords.append(ast.keyword(arg=None, value=ast.Name(id=args.kwarg.arg, ctx=ast.Load())))
        return positional_args, keywords

    def wrapper_return_expr(name: str, value_names: list[str], return_annotation: ast.expr | None) -> ast.expr:
        if len(value_names) == 1:
            return ast.Name(id=value_names[0], ctx=ast.Load())
        annotation_src = ast.unparse(return_annotation) if return_annotation is not None else ""
        if annotation_src == "np.ndarray":
            expr: ast.expr = ast.Call(
                func=ast.Attribute(value=ast.Name(id="np", ctx=ast.Load()), attr="maximum", ctx=ast.Load()),
                args=[ast.Name(id=value_names[0], ctx=ast.Load()), ast.Name(id=value_names[1], ctx=ast.Load())],
                keywords=[],
            )
            for value_name in value_names[2:]:
                expr = ast.Call(
                    func=ast.Attribute(value=ast.Name(id="np", ctx=ast.Load()), attr="maximum", ctx=ast.Load()),
                    args=[expr, ast.Name(id=value_name, ctx=ast.Load())],
                    keywords=[],
                )
            return expr
        return ast.Call(
            func=ast.Name(id="max", ctx=ast.Load()),
            args=[ast.List(elts=[ast.Name(id=value_name, ctx=ast.Load()) for value_name in value_names], ctx=ast.Load())],
            keywords=[],
        )

    def make_wrapper(node: ast.FunctionDef, name: str, active_only: bool) -> ast.FunctionDef:
        node = copy.deepcopy(node)
        node.name = name
        positional_args, keywords = call_arguments(node.args)
        target_index = target_variant_index(name)
        assignments: list[ast.stmt] = []
        active_value_name = ""
        for variant_index, _category in enumerate(categories_for_function(name)):
            value_name = f"{variant_name(name, variant_index)}_val"
            call = ast.Call(
                func=ast.Name(id=variant_name(name, variant_index), ctx=ast.Load()),
                args=copy.deepcopy(positional_args),
                keywords=copy.deepcopy(keywords),
            )
            assignment = ast.Assign(
                targets=[ast.Name(id=value_name, ctx=ast.Store())],
                value=call,
            )
            if active_only and variant_index != target_index:
                comment_assignment = ast.fix_missing_locations(copy.deepcopy(assignment))
                assignments.append(ast.Expr(value=ast.Constant(value=f"# {ast.unparse(comment_assignment)}")))
            else:
                assignments.append(assignment)
                if variant_index == target_index:
                    active_value_name = value_name
        if active_only:
            return_value = ast.Name(id=active_value_name, ctx=ast.Load())
        else:
            return_value = wrapper_return_expr(
                name,
                [f"{variant_name(name, variant_index)}_val" for variant_index in range(len(categories))],
                node.returns,
            )
        node.body = assignments + [ast.Return(value=return_value)]
        return node

    def module_prefix(tree: ast.Module) -> list[ast.stmt]:
        prefix = []
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                break
            prefix.append(copy.deepcopy(node))
        return prefix

    def module_suffix(tree: ast.Module) -> list[ast.stmt]:
        seen_main = False
        suffix = []
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "main":
                seen_main = True
                continue
            if seen_main and not isinstance(node, ast.FunctionDef):
                suffix.append(copy.deepcopy(node))
        return suffix

    def main_node(tree: ast.Module) -> ast.FunctionDef:
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "main":
                return node
        raise ValueError("Generated source does not define main()")

    def build_module(
        function_sources: dict[str, dict[str, ast.FunctionDef]],
        function_names: list[str],
        active_only: bool,
    ) -> str:
        body = module_prefix(starter_tree)
        for name in function_names:
            wrapper_source = function_sources[target_category if active_only else categories[0]].get(name)
            if wrapper_source is not None:
                body.append(make_wrapper(wrapper_source, name, active_only=active_only))
            for variant_index, category in enumerate(categories_for_function(name)):
                node = function_sources[category].get(name)
                if node is not None:
                    body.append(with_category_docstring(node, name, variant_index))

        main = copy.deepcopy(main_node(starter_tree))
        body.append(main)
        body.extend(module_suffix(starter_tree))

        module = ast.Module(body=body, type_ignores=[])
        ast.fix_missing_locations(module)
        return _unparse(module)

    function_order = [
        node.name
        for node in starter_tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name != "main"
    ]
    solution_function_order = [name for name in function_order if name in solution_functions]
    starter_by_category = {category: starter_functions for category in categories}
    solution_by_category = {
        category: (solution_functions if category == target_category else starter_functions)
        for category in categories
    }

    starter_expanded = build_module(starter_by_category, function_order, active_only=False)
    solution_expanded = build_module(solution_by_category, solution_function_order, active_only=True)
    solution_expanded = _string_docstring_comments(solution_expanded)
    return starter_expanded, solution_expanded


def _string_docstring_comments(source: str) -> str:
    converted = []
    for line in source.splitlines():
        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]
        if stripped.startswith(('"""# ', "'''# ")) and stripped.endswith(('"""', "'''")):
            converted.append(f"{indent}{stripped[3:-3]}")
        elif stripped.startswith(('"# ', "'# ")) and stripped.endswith(('"', "'")):
            converted.append(f"{indent}{stripped[1:-1]}")
        else:
            converted.append(line)
    return "\n".join(converted)
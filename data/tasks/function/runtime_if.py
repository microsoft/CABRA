"""Logic for adding if branches for evaluation"""

import math
import random


def indent(lines: list[str], n: int = 4) -> str:
    pad = " " * n
    return "\n".join(pad + line if line else "" for line in lines)


def build_chained_expression(
    child_vars: list[str],
    operators: list[str],
) -> str:
    if not child_vars:
        return f"{operators[0]}(val)"
    if len(child_vars) == 1:
        return f"{operators[0]}({child_vars[0]})"

    expr = f"{operators[0]}({child_vars[0]}, {child_vars[1]})"
    for i in range(1, len(operators)):
        expr = f"{operators[i]}({expr}, {child_vars[i + 1]})"
    return expr


class DistractorCallGraph:
    def __init__(self, function_names: list[str], edges: list[tuple[str, str]]):
        self.successors: dict[str, set[str]] = {name: set() for name in function_names}
        for source, target in edges:
            self.add_edge(source, target)

    def add_edge(self, source: str, target: str) -> None:
        self.successors.setdefault(source, set()).add(target)
        self.successors.setdefault(target, set())

    def reaches(self, source: str, target: str) -> bool:
        if source == target:
            return True
        seen = set()
        stack = list(self.successors.get(source, ()))
        while stack:
            name = stack.pop()
            if name == target:
                return True
            if name in seen:
                continue
            seen.add(name)
            stack.extend(self.successors.get(name, ()))
        return False

    def can_add_edge(self, source: str, target: str) -> bool:
        return source != target and not self.reaches(target, source)


def sample_dead_function_names(
    rng: random.Random,
    all_function_names: list[str],
    node_id: str,
    live_function_names: list[str],
    node_level: dict[str, int] | None = None,
    candidate_function_names: list[str] | None = None,
    distractor_call_graph: DistractorCallGraph | None = None,
) -> list[str]:
    k = len(live_function_names)
    if k == 0:
        return []

    source_function_names = candidate_function_names or all_function_names
    candidates = [name for name in source_function_names if name != node_id]

    if distractor_call_graph is not None:
        candidates = [
            name
            for name in candidates
            if distractor_call_graph.can_add_edge(node_id, name)
        ]
    elif node_level is not None:
        current_level = node_level.get(node_id, 0)
        candidates = [
            name
            for name in candidates
            if node_level.get(name, 0) > current_level
        ]

    if not candidates:
        return list(live_function_names)

    sampled = []
    live_function_names_set = set(live_function_names)
    for _ in range(k):
        available_candidates = [
            name
            for name in candidates
            if distractor_call_graph is None
            or distractor_call_graph.can_add_edge(node_id, name)
        ]
        preferred_candidates = [
            name
            for name in available_candidates
            if name not in live_function_names_set and name not in sampled
        ]
        unique_candidates = [
            name for name in available_candidates if name not in sampled
        ]

        if preferred_candidates:
            choice = rng.choice(preferred_candidates)
        elif unique_candidates:
            choice = rng.choice(unique_candidates)
        elif available_candidates:
            choice = rng.choice(available_candidates)
        else:
            remaining_live = [
                name
                for name in live_function_names
                if distractor_call_graph is None
                or distractor_call_graph.can_add_edge(node_id, name)
            ]
            if not remaining_live:
                remaining_live = list(live_function_names)
            choice = rng.choice(remaining_live)

        sampled.append(choice)
        if distractor_call_graph is not None:
            distractor_call_graph.add_edge(node_id, choice)

    if (
        distractor_call_graph is None
        and sampled == live_function_names
        and len(candidates) > 1
    ):
        for _ in range(5):
            rng.shuffle(sampled)
            if sampled != live_function_names:
                break

    return sampled


def sample_distractor_operators(
    rng: random.Random,
    num_children: int,
    task_type: str,
    live_operators: list[str] | None = None,
) -> list[str]:
    from data.tasks.function.ast import sample_operator

    op_type = "single" if num_children <= 1 else "multi"
    count = 1 if num_children <= 1 else num_children - 1

    for _ in range(20):
        operators = [
            sample_operator(rng, op_type, task_type)
            for _ in range(count)
        ]
        if not live_operators or operators != list(live_operators):
            return operators

    operators = list(operators)
    idx = rng.randrange(count)
    for _ in range(20):
        candidate = sample_operator(rng, op_type, task_type)
        if candidate != live_operators[idx]:
            operators[idx] = candidate
            break
    return operators


def runtime_simple_if_shape(
    if_num_hops: int,
    if_breadth_depth_ratio: float,
) -> tuple[int, int]:
    if if_num_hops <= 0:
        return 0, 0
    if_breadth_depth_ratio = min(max(if_breadth_depth_ratio, 0.0), 1.0)
    if if_breadth_depth_ratio == 0.0:
        return max(1, if_num_hops), 1
    if if_breadth_depth_ratio == 1.0:
        return 1, max(1, if_num_hops)
    depth_to_breadth_ratio = if_breadth_depth_ratio / (
        1.0 - if_breadth_depth_ratio
    )
    breadth = max(1, round(math.sqrt(if_num_hops / depth_to_breadth_ratio)))
    depth = max(1, round(math.sqrt(if_num_hops * depth_to_breadth_ratio)))
    return breadth, depth


def runtime_simple_check_helper_source(num_steps: int) -> str:
    if num_steps <= 0:
        return "def check():\n    return True"
    return (
        "def check(x: int, a: int, b: int, target: int, num_steps: int) -> bool:\n"
        "    for step in range(num_steps):\n"
        "        if x % 2 == 0:\n"
        "            x = x // 2\n"
        "        else:\n"
        "            x = a * x + b\n"
        "    return x % 2 == target"
    )


def runtime_simple_check_args(
    rng: random.Random,
    num_steps: int,
    desired: bool,
    used_args: set[tuple[int, int, int]],
) -> tuple[int, int, int, int]:
    odd_values = [1, 3, 5, 7, 9]
    max_unique = 100 * len(odd_values) * len(odd_values)
    for _ in range(200):
        x = rng.randint(1, 100)
        a = rng.choice(odd_values)
        b = rng.choice(odd_values)
        key = (x, a, b)
        if key in used_args and len(used_args) < max_unique:
            continue
        used_args.add(key)
        parity = x
        for _ in range(num_steps):
            parity = parity // 2 if parity % 2 == 0 else a * parity + b
        target = parity % 2 if desired else 1 - (parity % 2)
        return x, a, b, target

    x = rng.randint(1, 100)
    a = rng.choice(odd_values)
    b = rng.choice(odd_values)
    parity = x
    for _ in range(num_steps):
        parity = parity // 2 if parity % 2 == 0 else a * parity + b
    target = parity % 2 if desired else 1 - (parity % 2)
    return x, a, b, target


def _runtime_simple_check_result(
    x: int,
    a: int,
    b: int,
    target: int,
    num_steps: int,
) -> bool:
    for _ in range(num_steps):
        x = x // 2 if x % 2 == 0 else a * x + b
    return x % 2 == target


def _build_runtime_simple_guard(
    rng: random.Random,
    breadth: int,
    depth: int,
    param_mode: str = "unique_params",
    shared_args: tuple[int, int, int, int] | None = None,
) -> tuple[str, bool]:
    if breadth <= 0 or depth <= 0:
        return "check()", True

    if param_mode == "same_params":
        if shared_args is None:
            desired = rng.random() < 0.5
            shared_args = runtime_simple_check_args(rng, depth, desired, set())
        x, a, b, target = shared_args
        call = f"check({x}, {a}, {b}, {target}, num_steps={depth})"
        call_truth = _runtime_simple_check_result(x, a, b, target, depth)
        guard_truth = call_truth if breadth % 2 == 1 else False
        return " ^ ".join(call for _ in range(breadth)), guard_truth

    target_truth = rng.random() < 0.5
    call_truths = [
        rng.random() < 0.5 for _ in range(max(0, breadth - 1))
    ]
    current_truth = False
    for truth in call_truths:
        current_truth ^= truth
    call_truths.append(current_truth ^ target_truth)

    used_args: set[tuple[int, int, int]] = set()
    calls = []
    for desired in call_truths:
        x, a, b, target = runtime_simple_check_args(
            rng,
            depth,
            desired,
            used_args,
        )
        calls.append(f"check({x}, {a}, {b}, {target}, num_steps={depth})")
    return " ^ ".join(calls), target_truth


def _compute_branch(
    function_names: list[str],
    operators: list[str],
) -> tuple[list[str], str]:
    if not function_names:
        return [], f"{operators[0]}(val)"

    lines = []
    child_vars = []
    for fn_name in function_names:
        var = f"{fn_name}_val"
        child_vars.append(var)
        lines.append(f"{var} = {fn_name}(val)")

    return lines, build_chained_expression(child_vars, operators)


def _render_branch_if_tree(
    depth: int,
    make_guard,
    render_leaf,
    on_live_path: bool = True,
) -> list[str]:
    if depth == 0:
        return render_leaf(on_live_path)

    guard_src, guard_truth = make_guard()
    if_lines = _render_branch_if_tree(
        depth - 1,
        make_guard,
        render_leaf,
        on_live_path and guard_truth,
    )
    else_lines = _render_branch_if_tree(
        depth - 1,
        make_guard,
        render_leaf,
        on_live_path and not guard_truth,
    )

    lines = [f"if {guard_src}:"]
    lines.extend("    " + line for line in if_lines)
    lines.append("else:")
    lines.extend("    " + line for line in else_lines)
    return lines


def synthesize_runtime_if_body(
    node_id: str,
    outgoing: list[str],
    operators: list[str],
    rng: random.Random,
    all_function_names: list[str],
    num_branches: int,
    task_type: str,
    node_level: dict[str, int] | None = None,
    distractor_function_names: list[str] | None = None,
    distractor_call_graph: DistractorCallGraph | None = None,
    identical_branches: bool = True,
    check_breadth: int = 0,
    check_depth: int = 0,
    check_param_mode: str = "unique_params",
    shared_check_args: tuple[int, int, int, int] | None = None,
) -> str:
    if num_branches < 2:
        live_lines, live_expr = _compute_branch(list(outgoing), operators)
        return indent([*live_lines, f"return {live_expr}"])

    if num_branches & (num_branches - 1) != 0:
        raise ValueError(f"num_branches must be a power of two, got {num_branches}")

    depth = num_branches.bit_length() - 1
    guard_rng = random.Random(rng.random())

    def make_guard():
        return _build_runtime_simple_guard(
            guard_rng,
            check_breadth,
            check_depth,
            param_mode=check_param_mode,
            shared_args=shared_check_args,
        )

    def render_leaf(is_live: bool) -> list[str]:
        if is_live or identical_branches:
            function_names = list(outgoing)
            branch_operators = operators
        else:
            function_names = sample_dead_function_names(
                rng=rng,
                all_function_names=all_function_names,
                node_id=node_id,
                live_function_names=list(outgoing),
                node_level=node_level,
                candidate_function_names=distractor_function_names,
                distractor_call_graph=distractor_call_graph,
            )
            branch_operators = sample_distractor_operators(
                rng=rng,
                num_children=len(function_names),
                task_type=task_type,
                live_operators=operators,
            )

        branch_lines, branch_expr = _compute_branch(
            function_names,
            branch_operators,
        )
        return [*branch_lines, f"return {branch_expr}"]

    return indent(
        _render_branch_if_tree(
            depth=depth,
            make_guard=make_guard,
            render_leaf=render_leaf,
        )
    )

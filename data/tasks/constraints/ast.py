"""AST helpers for constraint transformations."""

import ast
import copy

COMBINE_MULTIPLY = "multiply"
COMBINE_ADD = "add"


ARITHMETIC_TEMPLATES = {"add_number", "subtract_number", "multiply_number", "divide_number"}
STRING_ADJUST_TEMPLATES = {"add_character_prefix", "add_character_suffix", "replace_character", "sandwich"}
ASSERT_TEMPLATES = {"assert_not", "assert_upper_bound", "assert_lower_bound"}
PRINT_TEMPLATES = {"print_prefix", "print_suffix"}
COMMENT_TEMPLATES = {"add_comment"}
INERT_CATEGORIES = (COMMENT_TEMPLATES, ASSERT_TEMPLATES, PRINT_TEMPLATES)


def _render(template_str: str, sub: dict) -> str:
    return template_str.format(**sub)


def _matched_statements(rules: list[dict], func_name: str, category: set) -> list[ast.stmt]:
    statements = []
    for rule in rules:
        if rule["template_key"] not in category:
            continue
        if rule["predicate"](func_name):
            sub = rule["sub"]
        elif "otherwise_sub" in rule:
            sub = rule["otherwise_sub"]
        else:
            continue
        statements.append(ast.parse(_render(rule["implementation"], sub)).body[0])
    return statements


def _inert_statements(specs: list[dict], func_name: str) -> list[ast.stmt]:
    statements = []
    for category in INERT_CATEGORIES:
        for spec in specs:
            statements.extend(_matched_statements(spec["rules"], func_name, category))
    return statements


def _string_adjust_statements(specs: list[dict], func_name: str) -> list[ast.stmt]:
    statements = []
    for spec in specs:
        statements.extend(_matched_statements(spec["rules"], func_name, STRING_ADJUST_TEMPLATES))
    return statements


def _arithmetic_adjust_statements(specs: list[dict], func_name: str) -> list[ast.stmt]:
    statements = []
    for spec in specs:
        statements.extend(_matched_statements(spec["rules"], func_name, ARITHMETIC_TEMPLATES))
    return statements


def _adjust_statements(specs: list[dict], func_name: str, value_kind: str) -> list[ast.stmt]:
    if value_kind == "str":
        return _string_adjust_statements(specs, func_name)
    return _arithmetic_adjust_statements(specs, func_name)


def _combine_op(combine_op: str) -> type[ast.operator]:
    if combine_op == COMBINE_ADD:
        return ast.Add
    if combine_op == COMBINE_MULTIPLY:
        return ast.Mult
    raise ValueError(f"Unsupported combine_op: {combine_op!r}")


def _combine_with_generated_values(return_value: ast.expr, var_names: list[str], combine_op: str) -> ast.expr:
    terms: list[ast.expr] = [ast.Name(id=name, ctx=ast.Load()) for name in var_names] + [return_value]
    return _left_associate_terms(terms, _combine_op(combine_op))


def _default_call(index: int) -> ast.Call:
    return ast.Call(
        func=ast.Name(id="default", ctx=ast.Load()),
        args=[ast.Constant(value=index)],
        keywords=[],
    )


def _annotation_expr(annotation: str) -> ast.expr:
    return ast.parse(annotation, mode="eval").body


def _append_default_args(node: ast.FunctionDef, specs: list[dict], annotation: str = "float") -> None:
    existing = {arg.arg: index for index, arg in enumerate(node.args.args)}
    default_start = len(node.args.args) - len(node.args.defaults)
    for spec_index, spec in enumerate(specs, start=1):
        var_name = spec["var"]
        if var_name in existing:
            default_index = existing[var_name] - default_start
            if default_index >= 0:
                node.args.defaults[default_index] = _default_call(spec_index)
            continue
        node.args.args.append(ast.arg(arg=var_name, annotation=_annotation_expr(annotation)))
        node.args.defaults.append(_default_call(spec_index))


def _insert_after_value_defs(body: list[ast.stmt], var_names: set[str]) -> int:
    index = 0
    while index < len(body):
        stmt = body[index]
        target = None
        if isinstance(stmt, ast.AnnAssign):
            target = stmt.target
        elif isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
            target = stmt.targets[0]
        if isinstance(target, ast.Name) and target.id in var_names:
            index += 1
            continue
        break
    return index


def _string_literal_comments(source: str) -> str:
    converted = []
    for line in source.splitlines():
        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]
        if stripped.startswith(('"""# ', "'''# ")) and stripped.endswith(('"""', "'''") ):
            converted.append(f"{indent}{stripped[3:-3]}")
        elif stripped.startswith(("'# ", '"# ')) and stripped.endswith(("'", '"')):
            converted.append(f"{indent}{stripped[1:-1]}")
        else:
            converted.append(line)
    return "\n".join(converted)


def _format_module_source(source: str) -> str:
    return source.replace("\nif __name__", "\n\nif __name__")


def _unparse(tree: ast.AST) -> str:
    return _format_module_source(ast.unparse(tree))


def _unparse_with_comments(tree: ast.AST) -> str:
    return _format_module_source(_string_literal_comments(ast.unparse(tree)))


def _flatten_binop(expr: ast.expr, op_type: type[ast.operator]) -> list[ast.expr]:
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, op_type):
        return _flatten_binop(expr.left, op_type) + _flatten_binop(expr.right, op_type)
    return [expr]


def _left_associate_terms(terms: list[ast.expr], op_type: type[ast.operator]) -> ast.expr:
    out = terms[0]
    for term in terms[1:]:
        out = ast.BinOp(left=out, op=op_type(), right=term)
    return out


def _is_generated_slow_term(expr: ast.expr) -> bool:
    return (
        isinstance(expr, ast.Call)
        and isinstance(expr.func, ast.Name)
        and expr.func.id == "slow"
    ) or (
        isinstance(expr, ast.Name)
        and expr.id.startswith("slow")
        and expr.id[4:].isdigit()
    )


def simplify_generated_slow_additions(source: str) -> str:
    class Simplifier(ast.NodeTransformer):
        def visit_BinOp(self, node: ast.BinOp):
            self.generic_visit(node)
            if not isinstance(node.op, ast.Add):
                return node
            terms = _flatten_binop(node, ast.Add)
            if sum(_is_generated_slow_term(term) for term in terms) < 2:
                return node
            return _left_associate_terms(terms, ast.Add)

    tree = Simplifier().visit(ast.parse(source))
    ast.fix_missing_locations(tree)
    return _unparse(tree)


def simplify_generated_value_combinations(source: str, value_names: list[str], combine_op: str) -> str:
    value_name_set = set(value_names)
    value_order = {name: index for index, name in enumerate(value_names)}
    op_type = _combine_op(combine_op)

    class Simplifier(ast.NodeTransformer):
        def visit_BinOp(self, node: ast.BinOp):
            self.generic_visit(node)
            if not isinstance(node.op, op_type):
                return node
            terms = _flatten_binop(node, op_type)
            generated_terms = [
                term for term in terms
                if isinstance(term, ast.Name) and term.id in value_name_set
            ]
            if len(generated_terms) < 2:
                return node
            other_terms = [
                term for term in terms
                if not (isinstance(term, ast.Name) and term.id in value_name_set)
            ]
            generated_terms.sort(key=lambda term: value_order[term.id])
            return _left_associate_terms(generated_terms + other_terms, op_type)

    tree = Simplifier().visit(ast.parse(source))
    ast.fix_missing_locations(tree)
    return _unparse(tree)


def simplify_generated_multiplier_products(source: str, mult_names: list[str]) -> str:
    return simplify_generated_value_combinations(source, mult_names, COMBINE_MULTIPLY)


def apply_parameter_constraints(
    source: str,
    specs: list[dict],
    function_names: set[str],
    call_target_names: set[str] | None = None,
    add_signatures: bool = False,
    terminal_product: bool = False,
    parameter_annotation: str = "float",
    terminal_combine_op: str = COMBINE_MULTIPLY,
    value_kind: str = "float",
) -> str:
    tree = ast.parse(source)
    var_names = [spec["var"] for spec in specs]
    var_name_set = set(var_names)
    call_target_names = set(function_names if call_target_names is None else call_target_names)

    def is_target_call(call: ast.Call) -> bool:
        return isinstance(call.func, ast.Name) and call.func.id in call_target_names

    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name not in function_names:
            continue
        if add_signatures:
            _append_default_args(node, specs, annotation=parameter_annotation)

        target_calls = [call for call in ast.walk(node) if isinstance(call, ast.Call) and is_target_call(call)]
        for call in target_calls:
            for spec in specs:
                existing = next((kw for kw in call.keywords if kw.arg == spec["var"]), None)
                if existing is None:
                    call.keywords.append(ast.keyword(arg=spec["var"], value=ast.Name(id=spec["var"], ctx=ast.Load())))
                else:
                    existing.value = ast.Name(id=spec["var"], ctx=ast.Load())

        if terminal_product:
            is_leaf = not target_calls
            if is_leaf:
                for stmt in ast.walk(node):
                    if isinstance(stmt, ast.Return) and stmt.value is not None:
                        stmt.value = _combine_with_generated_values(stmt.value, var_names, terminal_combine_op)

        insert_at = _insert_after_value_defs(node.body, var_name_set)
        inserted = _inert_statements(specs, node.name)
        inserted.extend(_adjust_statements(specs, node.name, value_kind))
        node.body = node.body[:insert_at] + inserted + node.body[insert_at:]

    ast.fix_missing_locations(tree)
    return _unparse_with_comments(tree)


def seed_root_values(source: str, root_names: set[str], specs: list[dict], parameter_annotation: str = "float") -> str:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in root_names:
            _append_default_args(node, specs, annotation=parameter_annotation)
    ast.fix_missing_locations(tree)
    return _unparse(tree)


def _tuple_annotation(value_annotation: ast.expr | None, extra_type: str, count: int) -> ast.expr:
    base = copy.deepcopy(value_annotation) if value_annotation is not None else ast.Name(id="float", ctx=ast.Load())
    return ast.Subscript(
        value=ast.Name(id="tuple", ctx=ast.Load()),
        slice=ast.Tuple(elts=[base] + [ast.Name(id=extra_type, ctx=ast.Load()) for _ in range(count)], ctx=ast.Load()),
        ctx=ast.Load(),
    )


def add_return_values(source: str, source_functions: set[str], functions_to_modify: set[str], key_names: list[str]) -> str:
    class ReturnValueAdder(ast.NodeTransformer):
        def __init__(self):
            self.current_function = None
            self.first_call_seen = False

        def visit_FunctionDef(self, node: ast.FunctionDef):
            previous_function = self.current_function
            previous_first_call_seen = self.first_call_seen
            self.current_function = node.name
            self.first_call_seen = False
            if node.name in functions_to_modify:
                node.returns = _tuple_annotation(node.returns, "str", len(key_names))
            node.body = [self.visit(stmt) for stmt in node.body]
            self.current_function = previous_function
            self.first_call_seen = previous_first_call_seen
            return node

        def visit_Assign(self, node: ast.Assign):
            self.generic_visit(node)
            if (
                len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id in functions_to_modify
            ):
                if not self.first_call_seen:
                    extra_targets = [ast.Name(id=name, ctx=ast.Store()) for name in key_names]
                    self.first_call_seen = True
                else:
                    extra_targets = [ast.Name(id="_", ctx=ast.Store()) for _ in key_names]
                node.targets[0] = ast.Tuple(
                    elts=[node.targets[0]] + extra_targets,
                    ctx=ast.Store(),
                )
            return node

        def visit_Return(self, node: ast.Return):
            self.generic_visit(node)
            if self.current_function not in functions_to_modify or node.value is None:
                return node
            if self.current_function in source_functions:
                assignments = [ast.copy_location(ast.Assign(
                    targets=[ast.Tuple(
                        elts=[ast.Name(id=name, ctx=ast.Store()) for name in key_names],
                        ctx=ast.Store(),
                    )],
                    value=ast.Call(
                        func=ast.Name(id="external", ctx=ast.Load()),
                        args=[ast.Constant(value=len(key_names))],
                        keywords=[],
                    ),
                ), node)]
                return assignments + [self._tuple_return(node)]
            return self._tuple_return(node)

        def _tuple_return(self, node: ast.Return) -> ast.Return:
            node.value = ast.Tuple(
                elts=[node.value] + [ast.Name(id=name, ctx=ast.Load()) for name in key_names],
                ctx=ast.Load(),
            )
            return node

    tree = ast.parse(source)
    tree = ReturnValueAdder().visit(tree)
    ast.fix_missing_locations(tree)
    return _unparse(tree)


def seed_return_value_keys(source: str, source_functions: set[str], key_names: list[str]) -> str:
    class ReturnValueKeySeeder(ast.NodeTransformer):
        def __init__(self):
            self.current_function = None

        def visit_FunctionDef(self, node: ast.FunctionDef):
            previous = self.current_function
            self.current_function = node.name
            node.body = [self.visit(stmt) for stmt in node.body]
            self.current_function = previous
            return node

        def visit_Return(self, node: ast.Return):
            self.generic_visit(node)
            if self.current_function not in source_functions:
                return node
            assignments = [ast.copy_location(ast.Assign(
                targets=[ast.Tuple(
                    elts=[ast.Name(id=name, ctx=ast.Store()) for name in key_names],
                    ctx=ast.Store(),
                )],
                value=ast.Call(
                    func=ast.Name(id="external", ctx=ast.Load()),
                    args=[ast.Constant(value=len(key_names))],
                    keywords=[],
                ),
            ), node)]
            return assignments + [node]

    tree = ast.parse(source)
    tree = ReturnValueKeySeeder().visit(tree)
    ast.fix_missing_locations(tree)
    return _unparse(tree)


def apply_return_value_constraints(source: str, specs: list[dict], function_names: set[str]) -> str:
    class ConstraintInserter(ast.NodeTransformer):
        def __init__(self):
            self.current_function = None

        def visit_FunctionDef(self, node: ast.FunctionDef):
            previous = self.current_function
            self.current_function = node.name
            node.body = [self.visit(stmt) for stmt in node.body]
            self.current_function = previous
            return node

        def visit_Return(self, node: ast.Return):
            self.generic_visit(node)
            if self.current_function not in function_names:
                return node
            return _inert_statements(specs, self.current_function) + _string_adjust_statements(specs, self.current_function) + [node]

    tree = ast.parse(source)
    tree = ConstraintInserter().visit(tree)
    ast.fix_missing_locations(tree)
    return _unparse_with_comments(tree)


def index_slow_calls(source: str, target_names: set[str], num_values: int) -> str:
    class SlowIndexer(ast.NodeTransformer):
        def __init__(self):
            self.current_function = None
            self.next_index = 1

        def visit_FunctionDef(self, node: ast.FunctionDef):
            previous_function = self.current_function
            previous_index = self.next_index
            self.current_function = node.name
            self.next_index = 1
            node.body = [self.visit(stmt) for stmt in node.body]
            self.current_function = previous_function
            self.next_index = previous_index
            return node

        def visit_Call(self, node: ast.Call):
            self.generic_visit(node)
            if (
                self.current_function in target_names
                and isinstance(node.func, ast.Name)
                and node.func.id == "slow"
                and not node.args
                and not node.keywords
            ):
                node.args.append(ast.Constant(value=((self.next_index - 1) % num_values) + 1))
                self.next_index += 1
            return node

    tree = ast.parse(source)
    tree = SlowIndexer().visit(tree)
    ast.fix_missing_locations(tree)
    return _unparse(tree)


def index_helper_calls(source: str, helper_func_name: str, var_names: list[str]) -> str:
    index_by_var = {name: index for index, name in enumerate(var_names, start=1)}

    class HelperIndexer(ast.NodeTransformer):
        def visit_Assign(self, node: ast.Assign):
            self.generic_visit(node)
            target = node.targets[0] if len(node.targets) == 1 else None
            self._maybe_index(target, node.value)
            return node

        def visit_AnnAssign(self, node: ast.AnnAssign):
            self.generic_visit(node)
            self._maybe_index(node.target, node.value)
            return node

        def _maybe_index(self, target: ast.expr | None, value: ast.expr | None) -> None:
            if not isinstance(target, ast.Name) or target.id not in index_by_var:
                return
            if not (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id == helper_func_name
                and len(value.args) == 1
                and not value.keywords
            ):
                return
            value.args.append(ast.Constant(value=index_by_var[target.id]))

    tree = ast.parse(source)
    tree = HelperIndexer().visit(tree)
    ast.fix_missing_locations(tree)
    return _unparse(tree)


def index_get_multiplier_calls(source: str, var_names: list[str]) -> str:
    return index_helper_calls(source, "get_multiplier", var_names)


def _default_value_expr(default_value):
    if isinstance(default_value, str):
        return ast.parse(default_value, mode="eval").body
    return ast.Constant(value=default_value)


def move_slow_values_to_ancestor(
    source: str,
    ancestor_node: str,
    target_nodes: list[str],
    affected_nodes: set[str],
    slow_names: list[str],
    value_type: str = "float",
    default_value=0.0,
) -> str:
    target_nodes = set(target_nodes)
    affected_nodes = set(affected_nodes) | target_nodes

    class SlowMover(ast.NodeTransformer):
        def __init__(self):
            self.current_function = None
            self.slow_index = 0

        def visit_FunctionDef(self, node: ast.FunctionDef):
            previous_function = self.current_function
            previous_index = self.slow_index
            self.current_function = node.name
            self.slow_index = 0
            self.generic_visit(node)

            if node.name == ancestor_node:
                assignments = [
                    ast.AnnAssign(
                        target=ast.Name(id=name, ctx=ast.Store()),
                        annotation=_annotation_expr(value_type),
                        value=ast.Call(func=ast.Name(id="slow", ctx=ast.Load()), args=[ast.Constant(value=index)], keywords=[]),
                        simple=1,
                    )
                    for index, name in enumerate(slow_names, start=1)
                ]
                node.body = assignments + node.body
            elif node.name in affected_nodes:
                existing = {arg.arg for arg in node.args.args}
                for name in slow_names:
                    if name not in existing:
                        node.args.args.append(ast.arg(arg=name, annotation=_annotation_expr(value_type)))
                        node.args.defaults.append(_default_value_expr(default_value))

            self.current_function = previous_function
            self.slow_index = previous_index
            return node

        def visit_Call(self, node: ast.Call):
            self.generic_visit(node)
            if (
                self.current_function in target_nodes
                and isinstance(node.func, ast.Name)
                and node.func.id == "slow"
                and not node.keywords
            ):
                if not node.args:
                    name = slow_names[self.slow_index % len(slow_names)]
                    self.slow_index += 1
                    return ast.Name(id=name, ctx=ast.Load())
                if (
                    len(node.args) == 1
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, int)
                    and 1 <= node.args[0].value <= len(slow_names)
                ):
                    return ast.Name(id=slow_names[node.args[0].value - 1], ctx=ast.Load())
            if (
                isinstance(node.func, ast.Name)
                and node.func.id in affected_nodes
                and (self.current_function == ancestor_node or self.current_function in affected_nodes)
            ):
                existing = {kw.arg for kw in node.keywords}
                for name in slow_names:
                    if name not in existing:
                        node.keywords.append(ast.keyword(arg=name, value=ast.Name(id=name, ctx=ast.Load())))
            return node

    tree = ast.parse(source)
    tree = SlowMover().visit(tree)
    ast.fix_missing_locations(tree)
    return _unparse(tree)


def move_multipliers_down_to_shared_node(
    source: str,
    ancestor_nodes: list[str],
    shared_node: str,
    affected_nodes: set[str],
    top_nodes: set[str],
    mult_names: list[str],
    helper_func_name: str = "get_multiplier",
    helper_type: str = "float",
    combine_op: str = COMBINE_MULTIPLY,
) -> str:
    ancestor_nodes = list(ancestor_nodes)
    affected_nodes = set(affected_nodes) | set(ancestor_nodes) | {shared_node} | set(top_nodes)
    top_nodes = set(top_nodes)
    tuple_returning_nodes = affected_nodes - top_nodes

    def tuple_annotation(base: ast.expr | None) -> ast.expr:
        return ast.Subscript(
            value=ast.Name(id="tuple", ctx=ast.Load()),
            slice=ast.Tuple(
                elts=[copy.deepcopy(base) if base is not None else _annotation_expr(helper_type)]
                + [_annotation_expr(helper_type) for _name in mult_names],
                ctx=ast.Load(),
            ),
            ctx=ast.Load(),
        )

    def make_mult_assignments() -> list[ast.stmt]:
        return [
            ast.AnnAssign(
                target=ast.Name(id=name, ctx=ast.Store()),
                annotation=_annotation_expr(helper_type),
                value=ast.Call(
                    func=ast.Name(id=helper_func_name, ctx=ast.Load()),
                    args=[ast.Name(id="val", ctx=ast.Load()), ast.Constant(value=index)],
                    keywords=[],
                ),
                simple=1,
            )
            for index, name in enumerate(mult_names, start=1)
        ]

    def tuple_target(target: ast.expr) -> ast.Tuple:
        return ast.Tuple(
            elts=[target] + [ast.Name(id=name, ctx=ast.Store()) for name in mult_names],
            ctx=ast.Store(),
        )

    def tuple_value(value: ast.expr) -> ast.Tuple:
        return ast.Tuple(
            elts=[value] + [ast.Name(id=name, ctx=ast.Load()) for name in mult_names],
            ctx=ast.Load(),
        )

    def computed_value(value: ast.expr) -> ast.expr:
        return _combine_with_generated_values(value, mult_names, combine_op)

    def is_tuple_call(value: ast.expr) -> bool:
        return isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id in tuple_returning_nodes

    class AffectedCallHoister(ast.NodeTransformer):
        def __init__(self):
            self.matches: list[ast.Call] = []

        def visit_Call(self, node: ast.Call):
            self.generic_visit(node)
            if isinstance(node.func, ast.Name) and node.func.id in tuple_returning_nodes:
                self.matches.append(node)
                return ast.Name(id="temp", ctx=ast.Load())
            return node

    class Mover(ast.NodeTransformer):
        def visit_FunctionDef(self, node: ast.FunctionDef):
            if node.name not in affected_nodes:
                return self.generic_visit(node)

            is_top = node.name in top_nodes
            node.returns = _annotation_expr(helper_type) if is_top else tuple_annotation(node.returns)
            node.body = [
                stmt for stmt in node.body
                if not (
                    isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.Expr))
                    and any(
                        isinstance(child, ast.Call)
                        and isinstance(child.func, ast.Name)
                        and child.func.id == helper_func_name
                        for child in ast.walk(stmt)
                    )
                )
            ]

            prefix = make_mult_assignments() if node.name == shared_node else []
            new_body: list[ast.stmt] = []
            found_mults = node.name == shared_node
            for stmt in node.body:
                if (
                    isinstance(stmt, ast.Assign)
                    and len(stmt.targets) == 1
                    and is_tuple_call(stmt.value)
                ):
                    stmt.targets[0] = tuple_target(stmt.targets[0])
                    new_body.append(stmt)
                    found_mults = True
                    continue
                if not isinstance(stmt, ast.Return) or stmt.value is None:
                    new_body.append(stmt)
                    continue

                if found_mults:
                    stmt.value = computed_value(stmt.value) if is_top else tuple_value(stmt.value)
                    new_body.append(stmt)
                    continue

                hoister = AffectedCallHoister()
                new_return_value = hoister.visit(stmt.value)
                if len(hoister.matches) == 1:
                    new_body.append(ast.Assign(targets=[tuple_target(ast.Name(id="temp", ctx=ast.Store()))], value=hoister.matches[0]))
                    stmt.value = computed_value(new_return_value) if is_top else tuple_value(new_return_value)
                    new_body.append(stmt)
                    continue
                if len(hoister.matches) > 1:
                    names = [match.func.id for match in hoister.matches if isinstance(match.func, ast.Name)]
                    raise ValueError(f"Function {node.name!r} has multiple affected calls: {names}")

                if not is_top and node.name != shared_node:
                    new_body.extend(make_mult_assignments())
                stmt.value = computed_value(new_return_value) if is_top else tuple_value(new_return_value)
                new_body.append(stmt)

            node.body = prefix + new_body
            return node

    tree = ast.parse(source)
    tree = Mover().visit(tree)
    ast.fix_missing_locations(tree)
    return _unparse(tree)


def apply_extract_constraints(source: str, specs: list[dict], function_names: set[str], value_kind: str = "float") -> str:
    var_names = {spec["var"] for spec in specs}

    def loaded_generated_values(node: ast.AST) -> set[str]:
        return {
            child.id
            for child in ast.walk(node)
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load) and child.id in var_names
        }

    def defined_generated_values(node: ast.AST) -> set[str]:
        return {
            child.id
            for child in ast.walk(node)
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store) and child.id in var_names
        }

    def returns_generated_values(node: ast.FunctionDef) -> bool:
        for stmt in ast.walk(node):
            if not isinstance(stmt, ast.Return) or not isinstance(stmt.value, ast.Tuple):
                continue
            if any(isinstance(elt, ast.Name) and elt.id in var_names for elt in stmt.value.elts):
                return True
        return False

    class Inserter(ast.NodeTransformer):
        def visit_FunctionDef(self, node: ast.FunctionDef):
            if node.name not in function_names:
                return self.generic_visit(node)
            should_adjust_returned_values = returns_generated_values(node)
            uses_generated_values = bool(loaded_generated_values(node))
            if not should_adjust_returned_values and not uses_generated_values:
                return self.generic_visit(node)
            new_body = []
            inserted = False
            available = {arg.arg for arg in node.args.args if arg.arg in var_names}
            for stmt in node.body:
                if not inserted and var_names.issubset(available) and loaded_generated_values(stmt):
                    func_name = node.name
                    new_body.extend(_inert_statements(specs, func_name))
                    new_body.extend(_adjust_statements(specs, func_name, value_kind))
                    inserted = True
                new_body.append(stmt)
                available.update(defined_generated_values(stmt))
                if not inserted and var_names.issubset(available):
                    func_name = node.name
                    new_body.extend(_inert_statements(specs, func_name))
                    new_body.extend(_adjust_statements(specs, func_name, value_kind))
                    inserted = True
            node.body = new_body
            return node

    tree = ast.parse(source)
    tree = Inserter().visit(tree)
    ast.fix_missing_locations(tree)
    return _unparse_with_comments(tree)

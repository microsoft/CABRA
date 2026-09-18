"""
Validation helpers for generated merge code programs. We ensure:
1. Synonymous code blocks are truly synonymous
2. The two classes are not identical (i.e., compute() methods diverge on at least one input vector)
"""

import ast
import random

from data.tasks.merge_code.transformations import (
    NameGenerator,
    synonymize_block,
)


CLASS_NAMES = ("CalculateA", "CalculateB")


def class_context(program, class_index, seed):
    """Build deterministic per-class transformation state."""
    rng = random.Random(f"{seed}-class{class_index}")
    max_decomposition_temps = 3 * len(program["block_items"])
    namer = NameGenerator(
        rng,
        len(program["params"]) + len(program["all_vars"]) + max_decomposition_temps,
        reserved=program["params"] + program["all_vars"],
    )
    rename = {}
    for name in program["params"] + program["all_vars"]:
        rename[name] = namer.next()
    return rng, namer, rename


def _term_value(term, env):
    value = term.coeff * term.sign
    for factor in term.factors:
        value *= env[factor]
    return value


def _line_value(line, env):
    return sum(_term_value(term, env) for term in line.terms)


def _run(source, inputs):
    namespace = {}
    exec(compile(source, "<generated>", "exec"), namespace)
    a = namespace["CalculateA"]().compute(*inputs)
    b = namespace["CalculateB"]().compute(*inputs)
    return a, b


def _check_structure(source):
    """
    Every ``compute`` method must:
    1. Have each line past the first reference at least one earlier non-parameter variable
    2. Use every assigned variable at least once (no dead variables)
    """
    tree = ast.parse(source)
    for cls in [node for node in tree.body if isinstance(node, ast.ClassDef)]:
        for fn in [
            node
            for node in cls.body
            if isinstance(node, ast.FunctionDef) and node.name == "compute"
        ]:
            params = {arg.arg for arg in fn.args.args if arg.arg != "self"}
            assigns = [
                statement
                for statement in fn.body
                if isinstance(statement, ast.Assign)
                and isinstance(statement.targets[0], ast.Name)
            ]
            returned = {
                node.id
                for statement in fn.body
                if isinstance(statement, ast.Return)
                for node in ast.walk(statement)
                if isinstance(node, ast.Name)
            }
            rhs = [
                {
                    node.id
                    for node in ast.walk(statement.value)
                    if isinstance(node, ast.Name)
                }
                for statement in assigns
            ]
            for index, names in enumerate(rhs):
                if index > 0:
                    assert names - params, (
                        f"{cls.name} line {index} relies only on parameters: {names}"
                    )
            targets = [statement.targets[0].id for statement in assigns]
            for index, target in enumerate(targets):
                used = target in returned or any(
                    target in later for later in rhs[index + 1 :]
                )
                assert used, f"{cls.name} has dead variable {target!r}"


def _eval_lines(lines, env):
    env = dict(env)
    for line in lines:
        env[line.target] = _line_value(line, env)
    return env


def _check_block_synonyms(program, seed, allowed_transformations, trials=50):
    """Guarantee every synonym block is identical across the two classes."""
    items = program["items"]
    block_items = [item for item in items if item["kind"] == "block"]

    class_blocks = []
    for class_index in range(len(CLASS_NAMES)):
        rng, namer, _ = class_context(program, class_index, seed)
        rendered = []
        for item in items:
            if item["kind"] == "block":
                rendered.append(
                    synonymize_block(
                        item["block"].lines,
                        item["block"].live_out,
                        rng,
                        namer,
                        program["params"],
                        allowed_transformations,
                    )
                )
        class_blocks.append(rendered)

    validation_rng = random.Random(f"{seed}-block-synonyms")
    for block_index, item in enumerate(block_items):
        block = item["block"]
        renderings = [
            class_renderings[block_index] for class_renderings in class_blocks
        ]
        for _ in range(trials):
            env = {
                variable: validation_rng.randint(-5, 5)
                for variable in block.input_args
            }
            canonical_env = _eval_lines(block.lines, env)
            class_envs = [_eval_lines(rendering, env) for rendering in renderings]
            for output in block.live_out:
                expected = canonical_env[output]
                for class_index, class_env in enumerate(class_envs):
                    assert class_env[output] == expected, (
                        f"synonym block {block_index} live-out {output!r} diverges "
                        f"for {CLASS_NAMES[class_index]}: {class_env[output]} != "
                        f"{expected} (inputs {env})"
                    )


def validate_program(
    program,
    input_source,
    spaced_input_source,
    solution_source,
    seed,
    num_params,
    allowed_transformations,
):
    """Validate structural, synonym, and behavioral generation guarantees."""
    _check_structure(input_source)
    _check_structure(spaced_input_source)
    _check_block_synonyms(program, seed, allowed_transformations)

    validation_rng = random.Random(f"{seed}-verify")
    vectors = [tuple(range(1, num_params + 1))]
    vectors += [
        tuple(validation_rng.randint(-5, 5) for _ in range(num_params))
        for _ in range(50)
    ]
    diverged = False
    for vector in vectors:
        input_a, input_b = _run(input_source, vector)
        solution_a, solution_b = _run(solution_source, vector)
        assert input_a == solution_a, (
            f"CalculateA refactor mismatch on {vector}: {input_a} != {solution_a}"
        )
        assert input_b == solution_b, (
            f"CalculateB refactor mismatch on {vector}: {input_b} != {solution_b}"
        )
        if input_a != input_b:
            diverged = True
    assert diverged, "CalculateA and CalculateB never diverged across test vectors"


"""
Logic for the merge codebases task:
Task: Given two programs, extract all shared logic into a base class and leave only the differences in the subclasses.

The general approach is:
1. Build a program with N operations, split into D + 1 synonym blocks separated by D genuine differences.
2. Each block is a sequence of assignment lines, each line a sum of products of parameters and intermediate variables.
3. Each difference is a single assignment line that is guaranteed to compute a different value than its canonical counterpart.

The program is represented in an intermediate form, then rendered into Python source code for the two calculators 
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import random
import string
from dataclasses import dataclass, field

from .transformations import (
    ALL_PERTURBATIONS,
    ALL_TRANSFORMATIONS,
    SIGNED_COEFFS,
    DiffLine,
    Line,
    Term,
    perturb_line,
    rename_lines,
    synonymize_block,
    transform_difference,
)
from .validate_program import class_context, validate_program

CLASS_NAMES = ("CalculateA", "CalculateB")  # focus on the 2-class case


# --------------------------------------------------------------------------- #
# Intermediate representation
# --------------------------------------------------------------------------- #

@dataclass
class Block:
    lines: list
    targets: list
    input_args: list = field(default_factory=list)
    live_out: list = field(default_factory=list)

# --------------------------------------------------------------------------- #
# Evaluation (used to guarantee synonym-equality / difference-inequality)
# --------------------------------------------------------------------------- #

def term_value(term, env):
    value = term.coeff * term.sign
    for f in term.factors:
        value *= env[f]
    return value


def line_value(line, env):
    return sum(term_value(t, env) for t in line.terms)


# --------------------------------------------------------------------------- #
# Building the canonical program
# --------------------------------------------------------------------------- #

def _param_names(n):
    if n <= len(string.ascii_lowercase):
        return list(string.ascii_lowercase[:n])
    return [f"p{i}" for i in range(n)]


def _partition(rng, total, parts, minimum):
    """Split ``total`` into ``parts`` sizes, each >= ``minimum``."""
    if parts * minimum > total:
        raise ValueError(
            f"cannot split {total} operations into {parts} blocks "
            f"with at least {minimum} each"
        )
    sizes = [minimum] * parts
    for _ in range(total - parts * minimum):
        sizes[rng.randrange(parts)] += 1
    return sizes


def build_line(rng, target, params, intermediates, forced=None):
    """Create one assignment line.

    Enforces the dependency-chain constraint: if any intermediate variable is available, the line references at least one of them (not just parameters).
    When ``forced`` is given (a difference target feeding the next block) it is guaranteed to appear, which also satisfies the intermediate requirement.
    """
    pool = params + intermediates
    n_terms = rng.randint(2, 3)
    terms = []
    
    for i in range(n_terms):
        n_factors = rng.choice([1, 1, 2])
        factors = [rng.choice(pool)]
        if n_factors == 2:
            factors.append(rng.choice(pool))
        signed_coeff = rng.choice(SIGNED_COEFFS)
        coeff = abs(signed_coeff)
        sign = 1 if signed_coeff > 0 else -1
        terms.append(Term(tuple(factors), coeff, sign))

    inter_set = set(intermediates)
    
    if forced is not None:
        if not any(forced in t.factors for t in terms):
            t = terms[0]
            fs = list(t.factors)
            fs[0] = forced
            t.factors = tuple(fs)
            
    elif intermediates and not any(f in inter_set for t in terms for f in t.factors):
        t = rng.choice(terms)
        fs = list(t.factors)
        fs[rng.randrange(len(fs))] = rng.choice(intermediates)
        t.factors = tuple(fs)
        
    return Line(target, terms)


def build_diff(
    rng,
    target,
    params,
    intermediates,
    env,
    allowed_perturbations,
):
    """Build a difference: a canonical line and a genuinely different variant."""
    canon = build_line(rng, target, params, intermediates)
    base = line_value(canon, env)
    pool = params + intermediates
    inter_set = set(intermediates)
    for _ in range(64):
        pert = perturb_line(rng, canon, pool, allowed_perturbations)
        if line_value(pert, env) != base and any(
            f in inter_set for t in pert.terms for f in t.factors
        ):
            return DiffLine(target, canon, pert)
    raise AssertionError(
        "unable to build a valid difference with perturbations "
        f"{tuple(allowed_perturbations)!r}"
    )


def build_program(
    seed,
    n,
    d,
    num_params,
    min_block,
    allowed_perturbations,
):
    
    """Assemble the canonical program and compute liveness metadata."""
    if not allowed_perturbations:
        raise ValueError("allowed_perturbations must contain at least one perturbation")
    rng = random.Random(seed)
    params = _param_names(num_params)
    env = {p: i + 1 for i, p in enumerate(params)}

    # D differences partition the N operations into D + 1 synonym blocks.
    num_blocks = d + 1
    block_sizes = _partition(rng, n, num_blocks, min_block)

    items = []               # ordered: {'kind': 'block'|'diff', ...}
    inter = []               # intermediate variable names, in definition order
    all_vars = []            # every intermediate + difference target, in order
    counter = 1
    pending_force = None

    for k in range(num_blocks):
        block_lines = []
        block_targets = []
        for i in range(block_sizes[k]):
            target = f"m{counter:02d}"
            counter += 1
            intermediates = inter + block_targets
            forced = pending_force if (i == 0 and pending_force) else None
            line = build_line(rng, target, params, intermediates, forced=forced)
            env[target] = line_value(line, env)
            block_lines.append(line)
            block_targets.append(target)
        pending_force = None

        block = Block(lines=block_lines, targets=block_targets)
        items.append({"kind": "block", "k": k, "block": block})
        inter += block_targets
        all_vars += block_targets

        # A difference separates this block from the next (never two blocks).
        if k < num_blocks - 1:
            target = f"m{counter:02d}"
            counter += 1
            diff = build_diff(
                rng,
                target,
                params,
                list(inter),
                env,
                allowed_perturbations,
            )
            env[target] = line_value(diff.canon, env)  # canonical value for A
            items.append({"kind": "diff", "diff": diff})
            inter.append(target)
            all_vars.append(target)
            pending_force = target

    # No dead variables: the return collects every leaf -- an intermediate that
    # no later canonical line consumes as an operand.
    operands = set()
    for it in items:
        lines = it["block"].lines if it["kind"] == "block" else [it["diff"].canon]
        for line in lines:
            for term in line.terms:
                operands.update(term.factors)
    final_targets = [v for v in all_vars if v not in operands]
    final_set = set(final_targets)

    # Liveness + helper interfaces for every block.
    block_items = [it for it in items if it["kind"] == "block"]
    for pos, it in enumerate(items):
        if it["kind"] != "block":
            continue
        block = it["block"]
        target_set = set(block.targets)

        # Inputs: external variables read by the block, in first-use order.
        seen = set()
        inputs = []
        for line in block.lines:
            for term in line.terms:
                for f in term.factors:
                    if f not in target_set and f not in seen:
                        seen.add(f)
                        inputs.append(f)
        block.input_args = inputs

        # Live-outs: block targets read by any later item or by the return.
        block.live_out = [
            t for t in block.targets
            if t in final_set or _read_after(items, pos, t)
        ]

    return {
        "params": params,
        "items": items,
        "block_items": block_items,
        "final_targets": final_targets,
        "all_vars": all_vars,
    }


def _read_after(items, pos, target):
    for it in items[pos + 1:]:
        if it["kind"] == "block":
            lines = it["block"].lines
        else:
            lines = (it["diff"].canon, it["diff"].pert)
        for line in lines:
            for term in line.terms:
                if target in term.factors:
                    return True
    return False


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #

def render_terms(terms, expand_coeff=False, reverse_factors=False, order=None):
    """Render a list of :class:`Term` into a Python expression string."""
    order = list(range(len(terms))) if order is None else order
    parts = []  # (sign, string)
    for idx in order:
        term = terms[idx]
        factors = list(term.factors)
        if reverse_factors and len(factors) == 2:
            factors = factors[::-1]
        base = " * ".join(factors)
        if term.coeff == 1:
            parts.append((term.sign, base))
        elif expand_coeff:
            for _ in range(max(0, term.coeff)):
                parts.append((term.sign, base))
        elif len(factors) == 1:
            parts.append((term.sign, f"{term.coeff} * {base}"))
        else:
            parts.append((term.sign, f"{term.coeff} * ({base})"))

    pieces = []
    for i, (sign, text) in enumerate(parts):
        if i == 0:
            pieces.append(("-" + text) if sign < 0 else text)
        else:
            pieces.append((" - " if sign < 0 else " + ") + text)
    return "".join(pieces)


def _line_inputs(*lines):
    """Variables read by one or more lines, in first-use order."""
    seen = set()
    inputs = []
    for line in lines:
        for term in line.terms:
            for f in term.factors:
                if f not in seen:
                    seen.add(f)
                    inputs.append(f)
    return inputs


# --------------------------------------------------------------------------- #
# Emitters
# --------------------------------------------------------------------------- #

def _footer(num_params):
    values = ", ".join(str(i + 1) for i in range(num_params))
    return (
        '\n\nif __name__ == "__main__":\n'
        "    calc_a = CalculateA()\n"
        "    calc_b = CalculateB()\n\n"
        f"    args = ({values})\n\n"
        "    result_a = calc_a.compute(*args)\n"
        "    result_b = calc_b.compute(*args)\n\n"
        '    print(f"Result A: {result_a}")\n'
        '    print(f"Result B: {result_b}")\n'
    )


def _class_context(program, class_index, seed):
    """Deterministic per-class RNG, name source and global variable renaming.

    The renaming is built first from a freshly seeded RNG, so both emitters
    reconstruct the *same* names for a class; the RNG/namer are then reused for
    that class's random transformations (which only ever add fresh names).
    """
    return class_context(program, class_index, seed)


def emit_input(
    program,
    spaced,
    seed,
    num_params,
    allowed_transformations,
):
    """Render the two calculators.

    When ``spaced`` is True a blank line separates every block and difference so 
    the pipeline structure is visible (``input_with_space.py``), which is useful
    for debugging/viewing the code. We use False for the actual agent evaluation.
    """
    
    items = program["items"]
    leaves = program["final_targets"]
    rename_variables = "rename_variables" in set(allowed_transformations)

    out = [
        "from abc import ABC, abstractmethod",
        "",
        "",
        "class Calculate(ABC):",
        '    """Abstract base: turn the input parameters into a single result."""',
        "",
        "    @abstractmethod",
        "    def compute(self, *args):",
        "        ...",
        "",
        "",
    ]

    for ci, clsname in enumerate(CLASS_NAMES):
        rng, namer, rename = _class_context(program, ci, seed)
        out.append(f"class {clsname}(Calculate):")
        out.append("")
        compute_args = [rename[p] if rename_variables else p for p in program["params"]]
        out.append(f"    def compute(self, {', '.join(compute_args)}):")
        if spaced:
            out.append("")
        for it in items:
            if it["kind"] == "block":
                lines = synonymize_block(
                    it["block"].lines, it["block"].live_out, rng, namer,
                    program["params"], allowed_transformations,
                )
                if rename_variables:
                    rename_lines(lines, rename)
                for ln in lines:
                    out.append(f"        {ln.target} = {render_terms(ln.terms)}")
            else:
                ln = copy.deepcopy(transform_difference(it["diff"], ci == 1))
                if rename_variables:
                    rename_lines([ln], rename)
                out.append(f"        {ln.target} = {render_terms(ln.terms)}")
            if spaced:
                out.append("")
        return_values = [rename[v] if rename_variables else v for v in leaves]
        out.append(f"        return {' + '.join(return_values)}")
        out.append("")
    return "\n".join(out).rstrip() + "\n" + _footer(num_params)


def emit_solution(program, num_params):
    items = program["items"]
    leaves = program["final_targets"]
    diffs = [it["diff"] for it in items if it["kind"] == "diff"]

    out = [
        "from abc import ABC, abstractmethod",
        "",
        "",
        "class Calculate(ABC):",
        '    """Shared arithmetic pipeline extracted from the two calculators.',
        "",
        "    The template method keeps the common block ordering and return logic",
        "    in one place. Subclasses supply only the genuine difference lines.",
        '    """',
        "",
    ]

    for i, diff in enumerate(diffs, start=1):
        args = ", ".join(_line_inputs(diff.canon, diff.pert))
        out.append("    @abstractmethod")
        out.append(f"    def custom_compute_{i}(self, {args}):")
        out.append("        ...")
        out.append("")

    out.append(f"    def compute(self, {', '.join(program['params'])}):")
    out.append("")
    diff_index = 1
    for it in items:
        if it["kind"] == "block":
            for ln in it["block"].lines:
                out.append(f"        {ln.target} = {render_terms(ln.terms)}")
        else:
            diff = it["diff"]
            call = ", ".join(_line_inputs(diff.canon, diff.pert))
            out.append(f"        {diff.target} = self.custom_compute_{diff_index}({call})")
            out.append("")
            diff_index += 1
    out.append(f"        return {' + '.join(leaves)}")
    out.append("")

    out.append("")
    for ci, clsname in enumerate(CLASS_NAMES):
        out.append(f"class {clsname}(Calculate):")
        out.append("")
        for i, diff in enumerate(diffs, start=1):
            line = transform_difference(diff, ci == 1)
            args = ", ".join(_line_inputs(diff.canon, diff.pert))
            out.append(f"    def custom_compute_{i}(self, {args}):")
            out.append(f"        return {render_terms(line.terms)}")
            out.append("")
    return "\n".join(out).rstrip() + "\n" + _footer(num_params)


def generate(
    seed,
    n,
    d,
    num_params,
    min_block,
    allowed_transformations,
    allowed_perturbations,
    prompt_file,
):
    program = build_program(
        seed=seed,
        n=n,
        d=d,
        num_params=num_params,
        min_block=min_block,
        allowed_perturbations=allowed_perturbations,
    )
    input_src = emit_input(
        program,
        spaced=False,
        seed=seed,
        num_params=num_params,
        allowed_transformations=allowed_transformations,
    )
    input_spaced_src = emit_input(
        program,
        spaced=True,
        seed=seed,
        num_params=num_params,
        allowed_transformations=allowed_transformations,
    )
    solution_src = emit_solution(program, num_params=num_params)
    with open(prompt_file) as f:
        prompt_src = f.read()

    validate_program(
        program=program,
        input_source=input_src,
        spaced_input_source=input_spaced_src,
        solution_source=solution_src,
        seed=seed,
        num_params=num_params,
        allowed_transformations=allowed_transformations,
    )

    return {
        "input": input_src,
        "input_with_space": input_spaced_src,
        "prompt": prompt_src,
        "solution": solution_src,
        "allowed_transformations": list(allowed_transformations),
        "allowed_perturbations": list(allowed_perturbations),
    }


def generate_many(
    num_examples,
    seed,
    n,
    d,
    num_params,
    min_block,
    max_resample_attempts,
    allowed_transformations,
    allowed_perturbations,
    prompt_file,
):
    output = []
    candidate_seed = seed
    attempts = 0
    while len(output) < num_examples:
        if attempts >= max_resample_attempts:
            raise RuntimeError(
                f"generated {len(output)}/{num_examples} valid tasks after "
                f"{attempts} attempts; increase --max-resample-attempts or relax params"
            )
        attempts += 1
        try:
            info = generate(
                seed=candidate_seed,
                n=n,
                d=d,
                num_params=num_params,
                min_block=min_block,
                allowed_transformations=allowed_transformations,
                allowed_perturbations=allowed_perturbations,
                prompt_file=prompt_file,
            )
        except AssertionError as exc:
            print(f"[resample] seed={candidate_seed} rejected: {exc}")
        else:
            output.append(info)
        candidate_seed += 1
    return output


def parse_args():
    parser = argparse.ArgumentParser(description="Generate code merge tasks.")
    parser.add_argument("--n", type=int, default=200, help="total operations in each program")
    parser.add_argument("--d", type=int, default=4, help="number of genuine difference lines")
    parser.add_argument("--num-params", type=int, default=8, help="number of input parameters")
    parser.add_argument("--min-block", type=int, default=3, help="minimum assignment operations per synonym block")
    parser.add_argument("--seed", type=int, default=7, help="first seed to try; rejected samples are skipped deterministically")
    parser.add_argument("--num-examples", type=int, default=20, help="number of tasks to generate")
    parser.add_argument("--max-resample-attempts", type=int, default=100, help="maximum candidate seeds to try before giving up")
    parser.add_argument("--allowed-transformations", nargs="*", choices=ALL_TRANSFORMATIONS,
                        default=ALL_TRANSFORMATIONS,
                        help="list of synonym transformations allowed in generated inputs "
                             "(pass with no values to allow none)")
    parser.add_argument("--allowed-perturbations", nargs="+", choices=ALL_PERTURBATIONS,
                        default=ALL_PERTURBATIONS,
                        help="difference perturbations eligible for generated inputs")
    parser.add_argument("--run-name", type=str, default="testing", help="output JSON file stem")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="local_data/tasks",
        help="directory for the generated task JSON",
    )
    parser.add_argument(
        "--prompt-file",
        type=str,
        default=os.path.join(os.path.dirname(__file__), "prompt.txt"),
        help="prompt text to embed in generated task JSON",
    )
    parser.add_argument("--overwrite", action="store_true", help="overwrite the output JSON if it already exists")
    parser.add_argument("-y", "--yes", action="store_true", help="do not prompt when overwriting existing output")
    return parser.parse_args()


def main():
    args = parse_args()
    os.makedirs(args.output_dir, exist_ok=True)
    output_path = os.path.join(args.output_dir, f"{args.run_name}.json")
    if os.path.exists(output_path):
        if not args.overwrite:
            print(f"Run '{args.run_name}' already exists at {output_path}; skipping.")
            return
        if not args.yes:
            response = input(
                f"Run '{args.run_name}' already exists at {output_path}. Overwrite? [y/N]: "
            )
            if response.lower() != "y":
                print("Aborting.")
                return

    output_data = generate_many(
        num_examples=args.num_examples,
        seed=args.seed,
        n=args.n,
        d=args.d,
        num_params=args.num_params,
        min_block=args.min_block,
        max_resample_attempts=args.max_resample_attempts,
        allowed_transformations=tuple(args.allowed_transformations),
        allowed_perturbations=tuple(args.allowed_perturbations),
        prompt_file=args.prompt_file,
    )

    with open(output_path, "w") as f:
        json.dump(output_data, f)
    print(f"Wrote {len(output_data)} tasks to {output_path}")


if __name__ == "__main__":
    main()
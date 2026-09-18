"""Value-preserving synonym transformations and intentional divergences."""

from __future__ import annotations

import copy
from dataclasses import dataclass

from data.utils.word_pool import WordPool, WordPoolType


ALL_TRANSFORMATIONS = (
    "rename_variables",
    "shuffle_lines",
    "multi_lines",
    "reorder",
    "logical_equiv",
)
ALL_PERTURBATIONS = (
    "swap_factor",
    "flip_sign",
    "change_coeff",
    "add_factor",
)
SIGNED_COEFFS = (-5, -4, -3, -2, -1, 1, 2, 3, 4, 5)


# --------------------------------------------------------------------------- #
# Shared intermediate representation
# --------------------------------------------------------------------------- #

@dataclass
class Term:
    """A single signed, integer-scaled product of variables."""

    factors: tuple
    coeff: int = 1
    sign: int = 1


@dataclass
class Line:
    """An assignment ``target = sum(term for term in terms)``."""

    target: str
    terms: list


@dataclass
class DiffLine:
    """Canonical and intentionally divergent versions of one assignment."""

    target: str
    canon: Line
    pert: Line


# --------------------------------------------------------------------------- #
# Divergence transformations (intentionally change the computed value)
# --------------------------------------------------------------------------- #

def perturb_line(rng, canon, pool, allowed_perturbations):
    """Return a copy of ``canon`` with one behavior-changing perturbation"""
    pert = copy.deepcopy(canon)
    term = rng.choice(pert.terms)
    choice = rng.choice(allowed_perturbations)
    if choice == "swap_factor":
        idx = rng.randrange(len(term.factors))
        alts = [p for p in pool if p != term.factors[idx]]
        if alts:
            factors = list(term.factors)
            factors[idx] = rng.choice(alts)
            term.factors = tuple(factors)
    elif choice == "flip_sign":
        term.sign *= -1
    elif choice == "change_coeff":
        coeff = rng.choice([c for c in SIGNED_COEFFS if c != term.coeff])
        term.sign *= 1 if coeff > 0 else -1
        term.coeff = abs(coeff)
    else:  # add_factor
        term.factors = (*term.factors, rng.choice(pool))
    return pert


def transform_difference(diff, perturbed):
    """Select the perturbed (B) or canonical (A) line for a difference."""
    return diff.pert if perturbed else diff.canon


# --------------------------------------------------------------------------- #
# Synonym transformations (preserve the computed values exactly)
# --------------------------------------------------------------------------- #

def _topological_orders(lines, rng):
    """Return a random valid ordering of intra-block line dependencies."""
    index = {line.target: i for i, line in enumerate(lines)}
    deps = {i: set() for i in range(len(lines))}
    for i, line in enumerate(lines):
        for term in line.terms:
            for factor in term.factors:
                if factor in index and index[factor] != i:
                    deps[i].add(index[factor])
    order, done = [], set()
    while len(order) < len(lines):
        ready = [i for i in range(len(lines)) if i not in done and deps[i] <= done]
        pick = rng.choice(ready)
        order.append(pick)
        done.add(pick)
    return order


def _inline_merge(lines, live_out, rng, params):
    """Fold one single-use, non-exported intermediate into its consumer.

    The intermediate must be used exactly once, as a single factor of a single
    term. Its definition is distributed into that use, so scaled and product
    uses collapse too. Applying this repeatedly collapses a whole single-use
    dependency chain into one larger expression.
    """
    lines = copy.deepcopy(lines)
    order = list(range(len(lines)))
    rng.shuffle(order)
    for line_index in order:
        source = lines[line_index]
        source_name = source.target
        if source_name in live_out:
            continue
        if not any(f not in params for term in source.terms for f in term.factors):
            continue
        occurrences = [
            (consumer_index, term_index, sum(1 for f in term.factors if f == source_name))
            for consumer_index, line in enumerate(lines)
            if consumer_index != line_index
            for term_index, term in enumerate(line.terms)
            if source_name in term.factors
        ]
        if len(occurrences) != 1:
            continue
        consumer_index, term_index, multiplicity = occurrences[0]
        if multiplicity != 1 or consumer_index < line_index:
            continue
        if len(lines[consumer_index].terms) - 1 + len(source.terms) > 16:
            continue
        consumer_term = lines[consumer_index].terms[term_index]
        remaining_factors = list(consumer_term.factors)
        remaining_factors.remove(source_name)
        spliced = [
            Term(
                tuple(remaining_factors) + source_term.factors,
                consumer_term.coeff * source_term.coeff,
                consumer_term.sign * source_term.sign,
            )
            for source_term in source.terms
        ]
        lines[consumer_index].terms = (
            lines[consumer_index].terms[:term_index]
            + spliced
            + lines[consumer_index].terms[term_index + 1:]
        )
        del lines[line_index]
        return lines
    return lines


class NameGenerator:
    """Yield unique symbolic identifiers from the shared word pool."""

    def __init__(self, rng, size, reserved=()):
        self.reserved = set(reserved)
        self.pool = WordPool(WordPoolType.SYMBOLIC, size + len(self.reserved), rng)

    def next(self):
        while True:
            name = self.pool.sample(1)[0]
            if name not in self.reserved:
                return name


def _split_coeff(coeff, rng):
    """Split ``coeff`` into a few positive pieces that sum to ``coeff``."""
    if coeff <= 1:
        return [coeff]
    if coeff <= 3:
        parts = [coeff - 1, 1]
    else:
        n_parts = rng.randint(2, min(3, coeff))
        cuts = sorted(rng.sample(range(1, coeff), n_parts - 1))
        parts = [b - a for a, b in zip([0] + cuts, cuts + [coeff])]
    rng.shuffle(parts)
    return parts


def _expand_coeff(lines, rng):
    """Turn ``k * x`` into grouped equivalent terms such as ``3*x + 2*x``."""
    candidates = [
        (line_index, term_index)
        for line_index, line in enumerate(lines)
        for term_index, term in enumerate(line.terms)
        if term.coeff > 1
    ]
    if candidates:
        line_index, term_index = rng.choice(candidates)
        term = lines[line_index].terms[term_index]
        copies = [
            Term(term.factors, coeff, term.sign)
            for coeff in _split_coeff(term.coeff, rng)
        ]
        lines[line_index].terms = (
            lines[line_index].terms[:term_index]
            + copies
            + lines[line_index].terms[term_index + 1:]
        )
    return lines


def _collapse_coeff(lines, rng):
    """Turn ``x + x`` into ``2 * x`` by folding like terms together."""
    line = rng.choice(lines)
    groups = {}
    for i, term in enumerate(line.terms):
        groups.setdefault((tuple(sorted(term.factors)), term.sign), []).append(i)
    mergeable = [indexes for indexes in groups.values() if len(indexes) >= 2]
    if mergeable:
        indexes = set(rng.choice(mergeable))
        keep = min(indexes)
        total = sum(line.terms[i].coeff for i in indexes)
        new_terms = []
        for i, term in enumerate(line.terms):
            if i == keep:
                new_terms.append(Term(term.factors, total, term.sign))
            elif i not in indexes:
                new_terms.append(term)
        line.terms = new_terms
    return lines


def _merge_lines(lines, live_out, rng, params, rounds):
    """Fold up to ``rounds`` single-use intermediates into their consumers."""
    for _ in range(rounds):
        merged = _inline_merge(lines, live_out, rng, params)
        if len(merged) == len(lines):
            break
        lines = merged
    return lines


def _decompose_line(lines, rng, namer, params):
    """Split a long line by extracting a sub-sum into a fresh temporary."""
    candidates = [
        i
        for i, line in enumerate(lines)
        if len(line.terms) >= 3
        and any(f not in params for term in line.terms for f in term.factors)
    ]
    if not candidates:
        return lines
    index = rng.choice(candidates)
    line = lines[index]
    picked = None
    for _ in range(8):
        count = rng.randint(2, len(line.terms) - 1)
        choice = sorted(rng.sample(range(len(line.terms)), count))
        if any(f not in params for j in choice for f in line.terms[j].factors):
            picked = choice
            break
    if picked is None:
        return lines
    picked_set = set(picked)
    extracted = [copy.deepcopy(line.terms[j]) for j in picked]
    remaining = [
        line.terms[j] for j in range(len(line.terms)) if j not in picked_set
    ]
    temporary = namer.next()
    temporary_line = Line(temporary, extracted)
    new_line = Line(line.target, remaining + [Term((temporary,), 1, 1)])
    return lines[:index] + [temporary_line, new_line] + lines[index + 1:]


def _reorder_lines(lines, rng, params):
    """Shuffle mutually independent lines into a fresh valid order."""
    order = _topological_orders(lines, rng)
    shuffled = [lines[i] for i in order]
    front, back = [], []
    for line in shuffled:
        if all(f in params for term in line.terms for f in term.factors):
            front.append(line)
        else:
            back.append(line)
    return front + back


def synonymize_block(
    lines,
    live_out,
    rng,
    namer,
    params,
    allowed_transformations,
):
    """Rewrite a block into a behavior-preserving, syntactically-different block via synonym transformations"""
    lines = copy.deepcopy(lines)
    live = set(live_out)
    param_set = set(params)
    allowed = set(allowed_transformations)

    if "multi_lines" in allowed:
        lines = _merge_lines(
            lines, live, rng, param_set, rounds=rng.randint(1, len(lines))
        )
        for _ in range(rng.randint(1, 3)):
            lines = _decompose_line(lines, rng, namer, param_set)

    if "reorder" in allowed:
        for line in lines:
            rng.shuffle(line.terms)
            for term in line.terms:
                if len(term.factors) == 2 and rng.random() < 0.5:
                    term.factors = (term.factors[1], term.factors[0])
    if "logical_equiv" in allowed:
        for _ in range(rng.randint(1, 3)):
            transform = _expand_coeff if rng.random() < 0.5 else _collapse_coeff
            lines = transform(lines, rng)

    if "shuffle_lines" in allowed:
        return _reorder_lines(lines, rng, param_set)
    return lines


def rename_lines(lines, rename):
    """Apply a variable renaming across a list of lines."""
    for line in lines:
        line.target = rename.get(line.target, line.target)
        for term in line.terms:
            term.factors = tuple(rename.get(f, f) for f in term.factors)

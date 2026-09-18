"""Validate that the DAG does not offer multiple solutions (i.e., the lowest common ancestor has to be unique)"""

import networkx as nx

def _common_ancestors(G: nx.DiGraph, targets: list[str]) -> set[str]:
    return {n for n in G.nodes() if all(n == t or nx.has_path(G, n, t) for t in targets)}


def _common_descendants(G: nx.DiGraph, sources: list[str]) -> set[str]:
    return {n for n in G.nodes() if all(n == s or nx.has_path(G, s, n) for s in sources)}


def validate_cache_function(
    sub: nx.DiGraph, full: nx.DiGraph, designated: str, unique: bool = False,
) -> str | None:
    leaves = [n for n in sub.nodes() if sub.out_degree(n) == 0]
    if not leaves:
        return "no diamond leaves"
    missing = [n for n in leaves + [designated] if n not in full]
    if missing:
        return f"nodes {missing} missing from full spliced graph"
    commons = _common_ancestors(full, leaves)
    if designated not in commons:
        return f"designated {designated!r} is not a common ancestor of leaves {sorted(leaves)}"
    lower = sorted(n for n in commons if n != designated and nx.has_path(full, designated, n))
    if lower:
        return f"not lowest: descendants {lower} are also common ancestors"
    if unique:
        incomparable = sorted(
            n for n in commons
            if n != designated and not nx.has_path(full, n, designated)
        )
        if incomparable:
            return f"not unique: incomparable common ancestors {incomparable} (tied LCAs)"
    return None


def validate_extract_helper(
    sub: nx.DiGraph, full: nx.DiGraph, designated: str, unique: bool = False,
) -> str | None:
    roots = [n for n in sub.nodes() if sub.in_degree(n) == 0]
    if not roots:
        return "no diamond roots"
    missing = [n for n in roots + [designated] if n not in full]
    if missing:
        return f"nodes {missing} missing from full spliced graph"
    commons = _common_descendants(full, roots)
    if designated not in commons:
        return f"designated {designated!r} is not a common descendant of roots {sorted(roots)}"
    higher = sorted(n for n in commons if n != designated and nx.has_path(full, n, designated))
    if higher:
        return f"not nearest: ancestors {higher} are also common descendants"
    if unique:
        incomparable = sorted(
            n for n in commons
            if n != designated and not nx.has_path(full, designated, n)
        )
        if incomparable:
            return f"not unique: incomparable common descendants {incomparable} (tied NCDs)"
    return None
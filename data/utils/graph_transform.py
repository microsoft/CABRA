"""Various util functions for transforming graphs in generate_dags.py"""

import math

import networkx as nx


def fresh_id(graph):
    integer_ids = [node for node in graph.nodes() if isinstance(node, int)]
    return max(integer_ids) + 1 if integer_ids else 0


def splice_subdag(main_graph, subdag):
    """Copy a sub-DAG into a graph and return its old-to-new node mapping."""
    next_id = fresh_id(main_graph)
    mapping = {}
    for node in subdag.nodes():
        mapping[node] = next_id
        next_id += 1

    main_graph.add_nodes_from(mapping.values())
    main_graph.add_edges_from(
        (mapping[source], mapping[destination])
        for source, destination in subdag.edges()
    )
    return mapping


def wrap_with_root(graph):
    """Return a copy with one new root connected to every original source."""
    wrapped = graph.copy()
    sources = [
        node for node in wrapped.nodes() if wrapped.in_degree(node) == 0
    ]
    root = fresh_id(wrapped)
    wrapped.add_node(root)
    wrapped.add_edges_from((root, source) for source in sources)
    return wrapped, root


def wrap_with_sink(graph):
    """Return a copy with every original sink connected to one new sink."""
    wrapped = graph.copy()
    sinks = [
        node for node in wrapped.nodes() if wrapped.out_degree(node) == 0
    ]
    sink = fresh_id(wrapped)
    wrapped.add_node(sink)
    wrapped.add_edges_from((node, sink) for node in sinks)
    return wrapped, sink


def split_levels_at(levels, cut):
    """Return levels above and below a cut, ordered by distance from it."""
    level_count = len(levels)
    above = (
        [list(levels[cut - distance]) for distance in range(cut + 1)]
        if cut >= 0
        else []
    )
    below = (
        [
            list(levels[cut + 1 + distance])
            for distance in range(level_count - cut - 1)
        ]
        if cut < level_count - 1
        else []
    )
    return above, below


def geometric_offset(probability, rng, max_offset):
    """Sample a clipped geometric offset."""
    if max_offset <= 1:
        return 1
    probability = min(max(probability, 1e-6), 1 - 1e-6)
    uniform = rng.random()
    offset = 1 + int(
        math.floor(
            math.log(1 - uniform) / math.log(1 - probability)
        )
    )
    return max(1, min(offset, max_offset))


def expected_count(proportion, rng):
    """Draw an integer count with the requested expected value."""
    if proportion <= 0:
        return 0
    base = int(proportion)
    fraction = proportion - base
    return base + (1 if rng.random() < fraction else 0)


def add_layered_edges(graph, levels, proportion, locality, rng):
    """Add sampled forward edges to a layered DAG."""
    if proportion <= 0 or len(levels) < 2:
        return
    last = len(levels) - 1
    for level_index in range(last):
        for source in levels[level_index]:
            count = expected_count(proportion, rng)
            for _ in range(count):
                offset = geometric_offset(
                    locality, rng, last - level_index
                )
                destination = rng.choice(levels[level_index + offset])
                if not graph.has_edge(source, destination):
                    graph.add_edge(source, destination)


def pick_locality_target(levels_by_distance, locality, rng):
    """Pick a target using geometric distance and uniform node sampling."""
    nonempty = [nodes for nodes in levels_by_distance if nodes]
    if not nonempty:
        return None
    index = geometric_offset(locality, rng, len(nonempty)) - 1
    return rng.choice(nonempty[index])


def attach_direction(
    graph,
    splice_map,
    endpoints,
    levels_by_distance,
    attach_proportion,
    locality,
    rng,
    endpoint_to_pool,
):
    """Add sampled edges between spliced endpoints and a main-graph pool."""
    pool_size = sum(len(nodes) for nodes in levels_by_distance)
    if not endpoints or pool_size == 0:
        return []
    edge_count = expected_count(attach_proportion * pool_size, rng)
    edges = []
    for _ in range(edge_count):
        endpoint = rng.choice(endpoints)
        spliced = splice_map[endpoint]
        target = pick_locality_target(levels_by_distance, locality, rng)
        if target is None:
            continue
        if endpoint_to_pool:
            graph.add_edge(spliced, target)
            edges.append((spliced, target))
        else:
            graph.add_edge(target, spliced)
            edges.append((target, spliced))
    return edges


def attach_cache_function(
    graph,
    splice_map,
    tree_dag,
    wrapper_root_id,
    main_levels,
    attach_proportion,
    locality,
    rng,
):
    """Attach a cache-function tree to a main DAG."""
    above, below = split_levels_at(
        main_levels, rng.randint(-1, len(main_levels) - 1)
    )
    leaves = [
        node for node in tree_dag.nodes() if tree_dag.out_degree(node) == 0
    ]
    edges = attach_direction(
        graph, splice_map, [wrapper_root_id], above,
        attach_proportion, locality, rng, endpoint_to_pool=False,
    )
    edges += attach_direction(
        graph, splice_map, leaves, below,
        attach_proportion, locality, rng, endpoint_to_pool=True,
    )
    return edges


def attach_extract_helper(
    graph,
    splice_map,
    tree_dag,
    wrapper_sink_id,
    main_levels,
    attach_proportion,
    locality,
    rng,
):
    """Attach a reversed extract-helper tree to a main DAG."""
    above, below = split_levels_at(
        main_levels, rng.randint(-1, len(main_levels) - 1)
    )
    original_sinks = [
        node for node in tree_dag.nodes() if tree_dag.out_degree(node) == 0
    ]
    edges = attach_direction(
        graph, splice_map, original_sinks, above,
        attach_proportion, locality, rng, endpoint_to_pool=False,
    )
    edges += attach_direction(
        graph, splice_map, [wrapper_sink_id], below,
        attach_proportion, locality, rng, endpoint_to_pool=True,
    )
    return edges


def reverse_graph(graph):
    """Return a graph with the same node order and reversed edges."""
    reversed_graph = nx.DiGraph()
    reversed_graph.add_nodes_from(graph.nodes())
    reversed_graph.add_edges_from(
        (destination, source) for source, destination in graph.edges()
    )
    return reversed_graph


def relabel_spliced_main(
    combined_graph,
    main_map,
    splice_map,
    subdag_map,
    wrapper_id,
    wrapper_name,
):
    """Relabel a main graph and the sub-DAG that was spliced into it."""
    full_map = dict(main_map)
    for subdag_node, spliced_id in splice_map.items():
        full_map[spliced_id] = (
            wrapper_name
            if subdag_node == wrapper_id
            else subdag_map[subdag_node]
        )
    return nx.relabel_nodes(combined_graph, full_map), full_map

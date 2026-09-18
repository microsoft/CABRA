import argparse
from dataclasses import dataclass
import json
import os
import random
import shutil
from typing import Any

from tqdm import tqdm
import uuid

import networkx as nx

from data.utils.graph_transform import (
    add_layered_edges,
    attach_cache_function,
    attach_direction,
    attach_extract_helper,
    expected_count,
    geometric_offset,
    relabel_spliced_main,
    reverse_graph,
    splice_subdag,
    split_levels_at,
    wrap_with_root,
    wrap_with_sink,
)
from data.utils.word_pool import WordPool, WordPoolType
from data.utils.validate_dag import validate_cache_function, validate_extract_helper

MAX_LCA_NCD_RETRIES = 50


class RandomSource:
    """Seeded RNG compatible with the original generator's sampling order."""

    def __init__(self, seed):
        self._random = random.Random(seed)

    def __getattr__(self, name):
        return getattr(self._random, name)

    def poisson(self, lam):
        threshold = pow(2.718281828459045, -lam)
        count = 0
        product = 1.0
        while True:
            count += 1
            product *= self._random.random()
            if product <= threshold:
                return count - 1


@dataclass
class MainDag:
    graph: Any
    levels: list


@dataclass
class GraphVariant:
    dag: Any
    wrapper_id: Any
    combined: Any
    splice_map: dict
    chosen_edges: list


@dataclass
class TargetVariants:
    main: MainDag
    attach_prop: float
    edit_dag: Any
    tree_dag: Any
    add_return_value: GraphVariant
    add_parameter: GraphVariant
    cache_function: GraphVariant
    extract_helper: GraphVariant


def poisson_sizes(total, num_buckets, rng):
    """Distribute a total across nonempty buckets using Poisson draws."""
    sizes = []
    remaining = total
    for i in range(num_buckets):
        remaining_buckets = num_buckets - i
        if i == num_buckets - 1:
            sizes.append(max(1, remaining))
            break
        lam = max(1.0, remaining / remaining_buckets)
        size = rng.poisson(lam)
        size = max(1, min(size, remaining - (remaining_buckets - 1)))
        sizes.append(size)
        remaining -= size
    return sizes


def random_dag(num_nodes, prop, p_same, rng):
    """Generate a layered DAG and return it with its node levels."""
    depth = max(1, round(num_nodes ** prop))
    depth = min(depth, num_nodes)  # can't have more layers than nodes
    widths = poisson_sizes(num_nodes, depth, rng)

    G = nx.DiGraph()
    levels = []
    next_id = 0
    for w in widths:
        level = []
        for _ in range(w):
            G.add_node(next_id)
            level.append(next_id)
            next_id += 1
        levels.append(level)

    for j in range(1, len(levels)):
        for v in levels[j]:
            d = geometric_offset(p_same, rng, j)
            u = rng.choice(levels[j - d])
            G.add_edge(u, v)

    assert G.number_of_nodes() == num_nodes
    return G, levels


def sample_dag_params(args, prefix, rng):
    n = rng.randint(
        getattr(args, f"{prefix}_min_num_nodes"),
        getattr(args, f"{prefix}_max_num_nodes"),
    )
    prop = rng.uniform(
        getattr(args, f"{prefix}_min_depth_breadth_prop"),
        getattr(args, f"{prefix}_max_depth_breadth_prop"),
    )
    p = rng.uniform(
        getattr(args, f"{prefix}_min_prob_same_layer"),
        getattr(args, f"{prefix}_max_prob_same_layer"),
    )
    p_extra = rng.uniform(
        getattr(args, f"{prefix}_min_extra_edge_prop"),
        getattr(args, f"{prefix}_max_extra_edge_prop"),
    )
    return n, prop, p, p_extra


def build_main_dags(args, rng):
    main_dags = []
    for _ in range(rng.randint(args.code_min_entry, args.code_max_entry)):
        n, prop, p, p_extra = sample_dag_params(args, "code", rng)
        graph, levels = random_dag(n, prop, p, rng)
        add_layered_edges(graph, levels, p_extra, p, rng)
        if args.force_code_single_entry:
            graph, root = wrap_with_root(graph)
            levels = [[root]] + levels
        main_dags.append(MainDag(graph, levels))

    rng.shuffle(main_dags)
    return main_dags


def build_edit_variants(main, args, rng, attach_prop, attach_p_same):
    n, prop, p, p_extra = sample_dag_params(args, "edit", rng)
    edit_dag, edit_levels = random_dag(n, prop, p, rng)
    add_layered_edges(edit_dag, edit_levels, p_extra, p, rng)

    return_dag, return_sink = wrap_with_sink(edit_dag)
    parameter_dag, parameter_root = wrap_with_root(edit_dag)

    return_combined = main.graph.copy()
    return_splice = splice_subdag(return_combined, return_dag)
    parameter_combined = main.graph.copy()
    parameter_splice = splice_subdag(parameter_combined, parameter_dag)

    inner_endpoints = list(edit_dag.nodes())
    above, below = split_levels_at(
        main.levels, rng.randint(-1, len(main.levels) - 1)
    )
    return_edges = attach_direction(
        return_combined, return_splice, inner_endpoints, above,
        attach_prop, attach_p_same, rng, endpoint_to_pool=True,
    )
    return_edges += attach_direction(
        return_combined, return_splice, [return_sink], below,
        attach_prop, attach_p_same, rng, endpoint_to_pool=True,
    )

    above, below = split_levels_at(
        main.levels, rng.randint(-1, len(main.levels) - 1)
    )
    parameter_edges = attach_direction(
        parameter_combined, parameter_splice, [parameter_root], above,
        attach_prop, attach_p_same, rng, endpoint_to_pool=False,
    )
    parameter_edges += attach_direction(
        parameter_combined, parameter_splice, inner_endpoints, below,
        attach_prop, attach_p_same, rng, endpoint_to_pool=False,
    )

    return (
        edit_dag,
        GraphVariant(
            return_dag, return_sink, return_combined, return_splice, return_edges
        ),
        GraphVariant(
            parameter_dag, parameter_root, parameter_combined,
            parameter_splice, parameter_edges,
        ),
    )


def build_tree_variants(main, args, rng, attach_prop, attach_p_same):
    cache_error = extract_error = None
    for _ in range(MAX_LCA_NCD_RETRIES):
        n, prop, p, _ = sample_dag_params(args, "edit", rng)
        tree_dag, _ = random_dag(n, prop, p, rng)

        reversed_tree = reverse_graph(tree_dag)

        cache_dag, cache_root = wrap_with_root(tree_dag)
        extract_dag, extract_sink = wrap_with_sink(reversed_tree)

        cache_combined = main.graph.copy()
        cache_splice = splice_subdag(cache_combined, cache_dag)
        cache_edges = attach_cache_function(
            cache_combined, cache_splice, tree_dag, cache_root,
            main.levels, attach_prop, attach_p_same, rng,
        )
        remapped_cache = nx.relabel_nodes(cache_dag, cache_splice)
        cache_error = validate_cache_function(
            remapped_cache, cache_combined, cache_splice[cache_root]
        )
        if cache_error is not None:
            continue

        extract_combined = main.graph.copy()
        extract_splice = splice_subdag(extract_combined, extract_dag)
        extract_edges = attach_extract_helper(
            extract_combined, extract_splice, tree_dag, extract_sink,
            main.levels, attach_prop, attach_p_same, rng,
        )
        remapped_extract = nx.relabel_nodes(extract_dag, extract_splice)
        extract_error = validate_extract_helper(
            remapped_extract, extract_combined, extract_splice[extract_sink]
        )
        if extract_error is None:
            return (
                tree_dag,
                GraphVariant(
                    cache_dag, cache_root, cache_combined,
                    cache_splice, cache_edges,
                ),
                GraphVariant(
                    extract_dag, extract_sink, extract_combined,
                    extract_splice, extract_edges,
                ),
            )

    raise RuntimeError(
        f"LCA/NCD validation failed after {MAX_LCA_NCD_RETRIES} retries: "
        f"{cache_error or extract_error}"
    )


def build_target_variants(main, args, rng):
    attach_prop = rng.uniform(
        args.attach_min_extra_edge_prop, args.attach_max_extra_edge_prop
    )
    attach_p_same = rng.uniform(
        args.attach_min_prob_same_layer, args.attach_max_prob_same_layer
    )
    edit_dag, add_return_value, add_parameter = build_edit_variants(
        main, args, rng, attach_prop, attach_p_same
    )
    tree_dag, cache_function, extract_helper = build_tree_variants(
        main, args, rng, attach_prop, attach_p_same
    )
    return TargetVariants(
        main,
        attach_prop,
        edit_dag,
        tree_dag,
        add_return_value,
        add_parameter,
        cache_function,
        extract_helper,
    )


def name_and_assemble_sample(main_dags, targets, args, rng):
    """Apply names and return the complete object written to dag.json."""
    
    # Size the shared word pool for every graph node and wrapper.
    total = sum(main.graph.number_of_nodes() for main in main_dags)
    total += sum(target.edit_dag.number_of_nodes() + 2 for target in targets)
    total += sum(target.tree_dag.number_of_nodes() + 2 for target in targets)
    pool = WordPool(args.variable_names, total, rng)

    # Assign unique names to the main DAG nodes.
    main_maps = [
        dict(
            zip(main.graph.nodes(), pool.sample(main.graph.number_of_nodes()))
        )
        for main in main_dags
    ]

    # Assign names to edit, tree, and wrapper nodes for each target.
    edit_maps = []
    tree_maps = []
    return_sink_words = []
    parameter_root_words = []
    cache_root_words = []
    extract_sink_words = []
    for target in targets:
        edit_size = target.edit_dag.number_of_nodes()
        edit_words = pool.sample(edit_size + 2)
        edit_maps.append(
            dict(zip(target.edit_dag.nodes(), edit_words[:edit_size]))
        )
        return_sink_words.append(edit_words[edit_size])
        parameter_root_words.append(edit_words[edit_size + 1])

        tree_size = target.tree_dag.number_of_nodes()
        tree_words = pool.sample(tree_size + 2)
        tree_maps.append(
            dict(zip(target.tree_dag.nodes(), tree_words[:tree_size]))
        )
        cache_root_words.append(tree_words[tree_size])
        extract_sink_words.append(tree_words[tree_size + 1])

    # Apply the generated names to the main DAGs.
    named_main_dags = [
        nx.relabel_nodes(main.graph, main_maps[index])
        for index, main in enumerate(main_dags)
    ]

    # Relabel a standalone variant and its wrapper node.
    def named_variant_dag(variant, node_map, wrapper_word):
        full_map = dict(node_map)
        full_map[variant.wrapper_id] = wrapper_word
        return nx.relabel_nodes(variant.dag, full_map)

    # Build the named standalone edit variants.
    add_return_value_dags = [
        named_variant_dag(
            target.add_return_value,
            edit_maps[index],
            return_sink_words[index],
        )
        for index, target in enumerate(targets)
    ]
    add_parameter_dags = [
        named_variant_dag(
            target.add_parameter,
            edit_maps[index],
            parameter_root_words[index],
        )
        for index, target in enumerate(targets)
    ]

    # Build the named standalone tree variants.
    cache_function_dags = [
        named_variant_dag(
            target.cache_function,
            tree_maps[index],
            cache_root_words[index],
        )
        for index, target in enumerate(targets)
    ]
    extract_helper_dags = [
        named_variant_dag(
            target.extract_helper,
            tree_maps[index],
            extract_sink_words[index],
        )
        for index, target in enumerate(targets)
    ]

    # Build dead-code DAGs and attach them to their named main DAGs.
    dead_code_dags = []
    main_with_dead_code_dags = []
    dead_code_attach_edges = []
    for index, target in enumerate(targets):
        if args.force_edit_single_entry:
            dead_map = dict(edit_maps[index])
            dead_map[target.add_parameter.wrapper_id] = (
                parameter_root_words[index]
            )
            dead_code_dag = nx.relabel_nodes(
                target.add_parameter.dag, dead_map
            )
        else:
            dead_code_dag = nx.relabel_nodes(
                target.edit_dag, edit_maps[index]
            )

        combined = nx.compose(named_main_dags[index], dead_code_dag)
        main_targets = [
            node
            for node in named_main_dags[index].nodes()
            if named_main_dags[index].in_degree(node) > 0
        ]
        attach_edges = []
        if main_targets:
            for dead_node in dead_code_dag.nodes():
                count = min(
                    expected_count(target.attach_prop, rng),
                    len(main_targets),
                )
                for main_node in rng.sample(main_targets, count):
                    combined.add_edge(dead_node, main_node)
                    attach_edges.append([dead_node, main_node])

        dead_code_dags.append(dead_code_dag)
        main_with_dead_code_dags.append(combined)
        dead_code_attach_edges.append(attach_edges)

    # Name variants whose attachment edges all point in one direction.
    def name_one_direction_variants(variant_name, wrapper_words, sub_to_main):
        combined_dags = []
        all_attach_edges = []
        all_injection_ids = []
        for index, target in enumerate(targets):
            variant = getattr(target, variant_name)
            combined, full_map = relabel_spliced_main(
                variant.combined,
                main_maps[index],
                variant.splice_map,
                edit_maps[index],
                variant.wrapper_id,
                wrapper_words[index],
            )
            if sub_to_main:
                attach_edges = [
                    [full_map[source], main_maps[index][destination]]
                    for source, destination in variant.chosen_edges
                ]
                injection_ids = sorted(
                    {destination for _, destination in attach_edges}
                )
            else:
                attach_edges = [
                    [main_maps[index][source], full_map[destination]]
                    for source, destination in variant.chosen_edges
                ]
                injection_ids = sorted(
                    {source for source, _ in attach_edges}
                )
            combined_dags.append(combined)
            all_attach_edges.append(attach_edges)
            all_injection_ids.append(injection_ids)
        return combined_dags, all_attach_edges, all_injection_ids

    # Assemble the return-value and parameter variants.
    (
        main_with_add_return_value_dags,
        add_return_value_attach_edges,
        add_return_value_injection_ids,
    ) = name_one_direction_variants(
        "add_return_value", return_sink_words, sub_to_main=True
    )
    (
        main_with_add_parameter_dags,
        add_parameter_attach_edges,
        add_parameter_injection_ids,
    ) = name_one_direction_variants(
        "add_parameter", parameter_root_words, sub_to_main=False
    )

    # Name variants containing attachment edges in both directions.
    def name_mixed_variants(variant_name, wrapper_words):
        combined_dags = []
        all_attach_edges = []
        all_injection_ids = []
        for index, target in enumerate(targets):
            variant = getattr(target, variant_name)
            combined, full_map = relabel_spliced_main(
                variant.combined,
                main_maps[index],
                variant.splice_map,
                tree_maps[index],
                variant.wrapper_id,
                wrapper_words[index],
            )
            spliced_nodes = set(variant.splice_map.values())
            attach_edges = [
                [full_map[source], full_map[destination]]
                for source, destination in variant.chosen_edges
            ]
            injection_nodes = {
                destination if source in spliced_nodes else source
                for source, destination in variant.chosen_edges
            }
            combined_dags.append(combined)
            all_attach_edges.append(attach_edges)
            all_injection_ids.append(
                sorted(
                    main_maps[index][node] for node in injection_nodes
                )
            )
        return combined_dags, all_attach_edges, all_injection_ids

    # Assemble the cache-function and extract-helper variants.
    (
        main_with_cache_function_dags,
        cache_function_attach_edges,
        cache_function_injection_ids,
    ) = name_mixed_variants("cache_function", cache_root_words)
    (
        main_with_extract_helper_dags,
        extract_helper_attach_edges,
        extract_helper_injection_ids,
    ) = name_mixed_variants("extract_helper", extract_sink_words)

    # Serialize every named graph and its attachment metadata.
    graph_data = nx.node_link_data
    return {
        "main_code_dags": [graph_data(graph) for graph in named_main_dags],
        "num_target": len(targets),
        "dead_code_dags": [graph_data(graph) for graph in dead_code_dags],
        "main_code_with_dead_code_dags": [
            graph_data(graph) for graph in main_with_dead_code_dags
        ],
        "dead_code_attach_edges": dead_code_attach_edges,
        "add_return_value_dags": [
            graph_data(graph) for graph in add_return_value_dags
        ],
        "add_return_value_sink_ids": return_sink_words,
        "add_return_value_injection_node_ids": (
            add_return_value_injection_ids
        ),
        "add_return_value_attach_edges": add_return_value_attach_edges,
        "add_parameter_dags": [
            graph_data(graph) for graph in add_parameter_dags
        ],
        "add_parameter_root_ids": parameter_root_words,
        "add_parameter_injection_node_ids": add_parameter_injection_ids,
        "add_parameter_attach_edges": add_parameter_attach_edges,
        "cache_function_dags": [
            graph_data(graph) for graph in cache_function_dags
        ],
        "cache_function_root_ids": cache_root_words,
        "cache_function_injection_node_ids": cache_function_injection_ids,
        "cache_function_attach_edges": cache_function_attach_edges,
        "main_code_with_cache_function_dags": [
            graph_data(graph) for graph in main_with_cache_function_dags
        ],
        "extract_helper_dags": [
            graph_data(graph) for graph in extract_helper_dags
        ],
        "extract_helper_sink_ids": extract_sink_words,
        "extract_helper_injection_node_ids": extract_helper_injection_ids,
        "extract_helper_attach_edges": extract_helper_attach_edges,
        "main_code_with_extract_helper_dags": [
            graph_data(graph) for graph in main_with_extract_helper_dags
        ],
        "main_code_with_add_return_value_dags": [
            graph_data(graph) for graph in main_with_add_return_value_dags
        ],
        "main_code_with_add_return_value_target_ids": return_sink_words,
        "main_code_with_add_parameter_dags": [
            graph_data(graph) for graph in main_with_add_parameter_dags
        ],
        "main_code_with_add_parameter_target_ids": parameter_root_words,
    }


def prepare_save_path(args):
    save_path = os.path.join(args.save_dir, args.run_name)
    if os.path.exists(save_path):
        if not args.yes:
            response = input(
                f"Run '{args.run_name}' already exists at {save_path}. "
                "Overwrite? [y/N]: "
            )
            if response.lower() != "y":
                print("Aborting.")
                return None
        shutil.rmtree(save_path)
    os.makedirs(save_path, exist_ok=True)
    return save_path


def generate_sample(args, rng):
    """Generate, validate, name, and assemble one complete sample."""
    main_dags = build_main_dags(args, rng)
    num_targets = rng.randint(
        args.edit_min_entry, min(len(main_dags), args.edit_max_entry)
    )
    targets = [
        build_target_variants(main_dags[index], args, rng)
        for index in range(num_targets)
    ]
    return name_and_assemble_sample(main_dags, targets, args, rng)


def save_sample(save_path, sample_data, rng):
    dag_id = str(uuid.UUID(int=rng.getrandbits(128)))
    dag_dir = os.path.join(save_path, dag_id)
    os.makedirs(dag_dir, exist_ok=True)
    with open(os.path.join(dag_dir, "dag.json"), "w") as file:
        json.dump(sample_data, file)


def sample_dags(args):
    save_path = prepare_save_path(args)
    if save_path is None:
        return

    rng = RandomSource(args.seed)
    for _ in tqdm(range(args.num_dags), desc=f"sampling DAGs [{args.run_name}]"):
        sample_data = generate_sample(args, rng)
        save_sample(save_path, sample_data, rng)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate random DAGs based on input constraints.")
    
    # General arguments
    parser.add_argument("--run_name", type=str, required=True, help="Name for this run")
    parser.add_argument("--save_dir", type=str, required=True, help="Directory to save results")
    parser.add_argument("--num_dags", type=int, default=1000, help="Number of DAGs to generate")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompts.")
    
    # Random: what should the variable names be (we use symbols in experiments, e.g., aa = ...)
    parser.add_argument( "--variable_names", type=WordPoolType, default=WordPoolType.SYMBOLIC, choices=list(WordPoolType), help="Word pool used to name variables")

    # Edit the complexity of the initial codebase
    parser.add_argument("--code_min_entry", type=int, default=1, help="Min independent DAGs per sample in the main code block")
    parser.add_argument("--code_max_entry", type=int, default=1, help="Max independent DAGs per sample in the main code block")
    parser.add_argument("--code_min_num_nodes", type=int, default=8, help="Min total nodes per starter code DAG")
    parser.add_argument("--code_max_num_nodes", type=int, default=20, help="Max total nodes per starter code DAG")
    parser.add_argument("--code_min_depth_breadth_prop", type=float, default=0.45, help="Min depth/breadth proportion for starter code DAGs (0=flat, 1=chain). depth = N**prop")
    parser.add_argument("--code_max_depth_breadth_prop", type=float, default=0.55, help="Max depth/breadth proportion for starter code DAGs (0=flat, 1=chain). depth = N**prop")
    parser.add_argument("--code_min_prob_same_layer", type=float, default=0.6, help="Min Geom parameter for picking source-layer offset; higher = more nearest-layer preference")
    parser.add_argument("--code_max_prob_same_layer", type=float, default=0.9, help="Max Geom parameter for picking source-layer offset; higher = more nearest-layer preference")
    parser.add_argument("--code_min_extra_edge_prop", type=float, default=0.0, help="Min extra outgoing edges per node within each main code DAG (expected count)")
    parser.add_argument("--code_max_extra_edge_prop", type=float, default=0.0, help="Max extra outgoing edges per node within each main code DAG (expected count)")
    parser.add_argument("--force_code_single_entry", action="store_true", help="Wrap each main code DAG with a single root entrypoint")

    # Edit the graph for the required edit
    parser.add_argument("--edit_min_entry", type=int, default=1, help="Min number of main code DAGs that receive edits")
    parser.add_argument("--edit_max_entry", type=int, default=1, help="Max number of main code DAGs that receive edits")
    parser.add_argument("--edit_min_num_nodes", type=int, default=25, help="Min total nodes per injected edit/tree DAG")
    parser.add_argument("--edit_max_num_nodes", type=int, default=25, help="Max total nodes per injected edit/tree DAG")
    parser.add_argument("--edit_min_depth_breadth_prop", type=float, default=0.45, help="Min depth/breadth proportion for edit DAGs (0=flat, 1=chain)")
    parser.add_argument("--edit_max_depth_breadth_prop", type=float, default=0.55, help="Max depth/breadth proportion for edit DAGs (0=flat, 1=chain)")
    parser.add_argument("--edit_min_prob_same_layer", type=float, default=0.9, help="Min Geom parameter for edit DAG layer offsets")
    parser.add_argument("--edit_max_prob_same_layer", type=float, default=0.9, help="Max Geom parameter for edit DAG layer offsets")
    parser.add_argument("--edit_min_extra_edge_prop", type=float, default=0.3, help="Min extra outgoing edges per node within each edit DAG")
    parser.add_argument("--edit_max_extra_edge_prop", type=float, default=0.3, help="Max extra outgoing edges per node within each edit DAG")
    parser.add_argument("--force_edit_single_entry", action="store_true", help="Wrap each dead-code edit DAG with a single root entrypoint")

    # Attaching the code DAG and the edit DAG
    parser.add_argument("--attach_min_extra_edge_prop", type=float, default=0.3, help="Min expected cross-DAG attach edges per source node (per target)")
    parser.add_argument("--attach_max_extra_edge_prop", type=float, default=0.3, help="Max expected cross-DAG attach edges per source node (per target)")
    parser.add_argument("--attach_min_prob_same_layer", type=float, default=0.9, help="Min Geom parameter for cross-DAG attach locality over main-DAG layer distance")
    parser.add_argument("--attach_max_prob_same_layer", type=float, default=0.9, help="Max Geom parameter for cross-DAG attach locality over main-DAG layer distance")

    args = parser.parse_args()
    sample_dags(args)

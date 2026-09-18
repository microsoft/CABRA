"""Load an experiment YAML file and emit shell-safe bash assignments."""

from __future__ import annotations

import itertools
import shlex
import sys
from pathlib import Path
from typing import Any

import yaml


SCALARS = (
    "experiment_name", "run_name", "dag_dir", "tasks_root", "test_cases_root",
    "response_dir", "output_root", "prompt_file", "limit", "n_parallel",
    "input_field", "score_seed", "num_tests", "timeout_seconds", "max_failures",
    "retry_errors", "dry_run", "n", "d", "num_dags", "num_examples", "seed",
    "min_block", "max_resample_attempts", "overwrite", "yes",
    "parallelize_tasks", "variable_names", "force_code_single_entry",
    "force_edit_single_entry", "use_constraint_country_names", "num_params",
    "otherwise_constraint_prob", "runtime_if_type", "runtime_num_branches",
    "runtime_breadth_depth_ratio", "bucket_mode",
)
BUCKET_KINDS = (
    "num_nodes", "depth_breadth_prop", "prob_same_layer", "code_extra_edge",
    "edit_extra_edge", "attach", "attach_prob_same_layer", "code_entry",
    "edit_entry",
)
RUN_NAME_PARTS = (
    ("num_nodes", "n"),
    ("depth_breadth_prop", "prop"),
    ("prob_same_layer", "psame"),
    ("code_extra_edge", "ce"),
    ("edit_extra_edge", "ee"),
    ("attach", "attach"),
    ("code_entry", "centry"),
    ("edit_entry", "eentry"),
)
ALL_PERTURBATIONS = ("swap_factor", "flip_sign", "change_coeff", "add_factor")


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def emit_scalar(name: str, value: Any) -> None:
    if value is None:
        text = ""
    elif isinstance(value, bool):
        text = "true" if value else "false"
    else:
        text = str(value)
    print(f"{name}={shlex.quote(text)}")


def emit_array(name: str, values: list[Any] | tuple[Any, ...]) -> None:
    quoted = " ".join(shlex.quote(str(value)) for value in values)
    print(f"{name}=({quoted})")


def parse_pairs(name: str, values: list[Any]) -> list[tuple[Any, Any]]:
    pairs = []
    for value in values:
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise ValueError(f"{name}: each entry must be [min, max], got {value!r}")
        pairs.append((value[0], value[1]))
    return pairs


def parse_ranges(name: str, values: list[Any]) -> list[tuple[Any, Any]]:
    ranges = []
    for value in values:
        if isinstance(value, (list, tuple)):
            if len(value) != 2:
                raise ValueError(
                    f"{name}: range entries must be [min, max], got {value!r}"
                )
            ranges.append((value[0], value[1]))
        else:
            ranges.append((value, value))
    return ranges


def set_name(values: str) -> str:
    items = values.split()
    if items == list(ALL_PERTURBATIONS):
        return "all"
    if not items:
        return "none"
    return items[0] if len(items) == 1 else "+".join(items)


def range_name(value_range: tuple[Any, Any]) -> str:
    low, high = value_range
    return f"({low},{high})"


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: load_config.py <config.yaml>", file=sys.stderr)
        raise SystemExit(2)

    cfg = yaml.safe_load(Path(sys.argv[1]).read_text()) or {}
    if not isinstance(cfg, dict):
        raise ValueError("experiment config must contain a YAML mapping")

    for key in SCALARS:
        emit_scalar(key, cfg.get(key))

    task_sets = as_list(cfg.get("task_set_name"))
    if not all(isinstance(value, str) for value in task_sets):
        raise ValueError("task_set_name must be a string or list of strings")
    emit_array("task_set_names_arr", task_sets)

    task_types = as_list(cfg.get("task_types"))
    emit_scalar("task_types", " ".join(str(value) for value in task_types))
    emit_array("task_types_arr", task_types)
    emit_array("skip_task_types_arr", as_list(cfg.get("skip_task_types")))
    emit_array("models", as_list(cfg.get("models")))
    emit_array("copilot_models", as_list(cfg.get("copilot_models")))

    buckets = cfg.get("buckets") or {}
    bucket_mode = cfg.get("bucket_mode", "single")
    split_nodes = any(
        key in buckets for key in ("code_num_nodes", "main_num_nodes", "edit_num_nodes")
    )
    if split_nodes and bucket_mode != "single":
        raise ValueError("split code/edit node buckets require bucket_mode=single")

    raw_nodes = (
        buckets.get("num_nodes")
        or buckets.get("code_num_nodes")
        or buckets.get("main_num_nodes")
        or []
    )
    parsed = {
        kind: parse_pairs(
            f"buckets.{kind}",
            raw_nodes if kind == "num_nodes" else buckets.get(kind) or [],
        )
        for kind in BUCKET_KINDS
    }
    edit_nodes = parse_pairs(
        "buckets.edit_num_nodes", buckets.get("edit_num_nodes") or raw_nodes
    )
    lengths = {kind: len(values) for kind, values in parsed.items() if values}
    if lengths:
        missing = set(BUCKET_KINDS) - set(lengths)
        if missing:
            raise ValueError(f"all bucket arrays must be populated; empty: {sorted(missing)}")
        if bucket_mode == "single" and len(set(lengths.values())) != 1:
            raise ValueError(
                f"bucket_mode=single requires equal array lengths; got {lengths}"
            )
        if split_nodes and len(edit_nodes) != len(parsed["num_nodes"]):
            raise ValueError("code and edit node bucket arrays must have equal lengths")

    if bucket_mode == "nested" and lengths:
        combos = list(itertools.product(*(parsed[kind] for kind in BUCKET_KINDS)))
        for index, kind in enumerate(BUCKET_KINDS):
            emit_array(
                f"{kind}_buckets",
                [f"{combo[index][0]} {combo[index][1]}" for combo in combos],
            )
    else:
        size = next(iter(lengths.values()), 0)
        combos = [
            tuple(parsed[kind][index] for kind in BUCKET_KINDS)
            for index in range(size)
        ]
        for kind in BUCKET_KINDS:
            emit_array(
                f"{kind}_buckets",
                [f"{low} {high}" for low, high in parsed[kind]],
            )
    emit_array(
        "code_num_nodes_buckets",
        [f"{low} {high}" for low, high in parsed["num_nodes"]],
    )
    emit_array(
        "edit_num_nodes_buckets",
        [f"{low} {high}" for low, high in edit_nodes],
    )

    bucket_index = {kind: index for index, kind in enumerate(BUCKET_KINDS)}
    dag_run_names = []
    for combo_index, combo in enumerate(combos):
        parts = []
        if split_nodes:
            code_pair = combo[bucket_index["num_nodes"]]
            edit_pair = edit_nodes[combo_index]
            parts.extend(
                (f"cn=({code_pair[0]},{code_pair[1]})",
                 f"en=({edit_pair[0]},{edit_pair[1]})")
            )
        for kind, short in RUN_NAME_PARTS:
            if split_nodes and kind == "num_nodes":
                continue
            pair = combo[bucket_index[kind]]
            parts.append(f"{short}=({pair[0]},{pair[1]})")
        dag_run_names.append(f"{cfg.get('experiment_name', '')}_{'_'.join(parts)}")
    emit_array("dag_run_names", dag_run_names)

    constraint_cfg = cfg.get("constraint_buckets") or {}
    constraint_mode = cfg.get("constraint_bucket_mode", "nested")
    emit_scalar("constraint_bucket_mode", constraint_mode)
    constraint_kinds = ("num_constraints", "depth_breadth_prop", "num_distractors")
    constraints = {
        kind: parse_ranges(
            f"constraint_buckets.{kind}", constraint_cfg.get(kind) or []
        )
        for kind in constraint_kinds
    }
    constraint_lengths = {
        kind: len(values) for kind, values in constraints.items() if values
    }
    if constraint_lengths and constraint_mode == "single":
        if len(set(constraint_lengths.values())) != 1:
            raise ValueError(
                "constraint_bucket_mode=single requires equal array lengths"
            )
        count = next(iter(constraint_lengths.values()))
        constraint_combos = [
            tuple(constraints[kind][index] for kind in constraint_kinds)
            for index in range(count)
        ]
    elif constraint_lengths:
        constraint_combos = list(
            itertools.product(
                *(constraints[kind] or [(None, None)] for kind in constraint_kinds)
            )
        )
    else:
        constraint_combos = []
    for index, kind in enumerate(constraint_kinds):
        emit_array(
            f"constraint_{kind}_buckets",
            [f"{combo[index][0]} {combo[index][1]}" for combo in constraint_combos],
        )

    run_names = []
    if constraint_combos:
        for dag_name, combo in itertools.product(dag_run_names, constraint_combos):
            nc, prop, distractors = combo
            suffix = f"_nc={range_name(nc)}"
            if prop[0] is not None:
                suffix += f"_cp={range_name(prop)}"
            if distractors[0] is not None:
                suffix += f"_nd={range_name(distractors)}"
            run_names.append(dag_name + suffix)
    else:
        run_names = list(dag_run_names)

    runtime_hops = as_list(cfg.get("runtime_if_num_hops"))
    emit_array("runtime_if_num_hops", runtime_hops)
    if runtime_hops:
        run_names = [
            f"{dag_name}_ifhops={hop}"
            for dag_name, hop in itertools.product(dag_run_names, runtime_hops)
        ]
    emit_array("run_names", run_names)
    emit_array("llm_run_names", run_names)
    emit_array("agent_run_names", run_names)

    transformations = cfg.get("allowed_transformations") or []
    if transformations and all(not isinstance(item, list) for item in transformations):
        transformation_values = [str(item) for item in transformations]
        transformation_sets = [" ".join(transformation_values)]
    else:
        transformation_values = []
        transformation_sets = [
            " ".join(str(item) for item in values) for values in transformations
        ]
    emit_array("allowed_transformations", transformation_values)
    emit_array("allowed_transformation_sets", transformation_sets)
    effective_transformation_sets = transformation_sets or [
        "rename_variables shuffle_lines multi_lines reorder logical_equiv"
    ]

    perturbation_enabled = "allowed_perturbations" in cfg
    perturbations = cfg.get("allowed_perturbations") or []
    if perturbations and all(not isinstance(item, list) for item in perturbations):
        perturbation_values = [str(item) for item in perturbations]
        perturbation_sets = [" ".join(perturbation_values)]
    else:
        perturbation_values = []
        perturbation_sets = [
            " ".join(str(item) for item in values) for values in perturbations
        ]
    if not perturbation_sets:
        perturbation_sets = [" ".join(ALL_PERTURBATIONS)]
    emit_array("allowed_perturbations", perturbation_values)
    emit_array("allowed_perturbation_sets", perturbation_sets)
    emit_scalar("perturbation_sweep_enabled", perturbation_enabled)

    sweep_keys = (
        "n", "d", "num_params", "min_block", "seed", "num_examples",
        "max_resample_attempts",
    )
    for key in sweep_keys:
        emit_array(f"merge_code_{key}_values", as_list(cfg.get(key)))
    sweep_values = {
        "n": as_list(cfg.get("n")) or [50],
        "d": as_list(cfg.get("d")) or [5],
        "num_params": as_list(cfg.get("num_params")) or [10],
        "min_block": as_list(cfg.get("min_block")) or [3],
        "seed": as_list(cfg.get("seed")) or [42],
    }
    base_name = cfg.get("run_name") or cfg.get("experiment_name") or "merge_code"
    merge_run_names = []
    sweep_product = itertools.product(
        sweep_values["n"], sweep_values["d"], sweep_values["num_params"],
        sweep_values["min_block"], sweep_values["seed"],
    )
    for values in sweep_product:
        for transformation_index, perturbation_index in itertools.product(
            range(len(effective_transformation_sets)), range(len(perturbation_sets))
        ):
            name = (
                f"{base_name}_n={values[0]}_d={values[1]}_p={values[2]}_"
                f"b={values[3]}_seed={values[4]}_tf={transformation_index}"
            )
            if perturbation_enabled:
                name += f"_pt={set_name(perturbation_sets[perturbation_index])}"
            merge_run_names.append(name)
    emit_array("merge_code_run_names", merge_run_names)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"config error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

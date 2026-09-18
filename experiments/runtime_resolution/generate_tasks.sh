#!/bin/bash
# Generate fixed n=10 DAGs, then runtime tasks/test cases for each hop count.

set -e

dir="$(cd "$(dirname "$0")" && pwd)"
lib_dir="$(cd "$dir" && while [ ! -d "_lib" ]; do cd ..; done && pwd)/_lib"
root_dir="$(cd "$lib_dir/../.." && pwd)"
eval "$(uv run python "$lib_dir/load_config.py" "$dir/config.yaml")"
cd "$root_dir"

for i in "${!dag_run_names[@]}"; do
  read -r n_min n_max <<< "${num_nodes_buckets[$i]}"
  read -r p_min p_max <<< "${depth_breadth_prop_buckets[$i]}"
  read -r s_min s_max <<< "${prob_same_layer_buckets[$i]}"
  read -r ce_min ce_max <<< "${code_extra_edge_buckets[$i]}"
  read -r ee_min ee_max <<< "${edit_extra_edge_buckets[$i]}"
  read -r a_min a_max <<< "${attach_buckets[$i]}"
  read -r ap_min ap_max <<< "${attach_prob_same_layer_buckets[$i]}"
  read -r eentry_min eentry_max <<< "${edit_entry_buckets[$i]}"
  read -r centry_min centry_max <<< "${code_entry_buckets[$i]}"

  dag_run_name="${dag_run_names[$i]}"
  echo "=== DAG ${dag_run_name} ==="

  force_flags=""
  [[ "$force_code_single_entry" == "true" ]] && force_flags+=" --force_code_single_entry"
  [[ "$force_edit_single_entry" == "true" ]] && force_flags+=" --force_edit_single_entry"

  uv run python -m data.generate_dags \
    --run_name "$dag_run_name" \
    --save_dir "$dag_dir" \
    --num_dags $num_dags \
    --code_min_entry $centry_min \
    --code_max_entry $centry_max \
    --edit_min_entry $eentry_min \
    --edit_max_entry $eentry_max \
    --code_min_num_nodes $n_min \
    --code_max_num_nodes $n_max \
    --code_min_depth_breadth_prop $p_min \
    --code_max_depth_breadth_prop $p_max \
    --code_min_prob_same_layer $s_min \
    --code_max_prob_same_layer $s_max \
    --code_min_extra_edge_prop $ce_min \
    --code_max_extra_edge_prop $ce_max \
    --edit_min_num_nodes $n_min \
    --edit_max_num_nodes $n_max \
    --edit_min_depth_breadth_prop $p_min \
    --edit_max_depth_breadth_prop $p_max \
    --edit_min_prob_same_layer $s_min \
    --edit_max_prob_same_layer $s_max \
    --edit_min_extra_edge_prop $ee_min \
    --edit_max_extra_edge_prop $ee_max \
    --attach_min_extra_edge_prop $a_min \
    --attach_max_extra_edge_prop $a_max \
    --attach_min_prob_same_layer $ap_min \
    --attach_max_prob_same_layer $ap_max \
    --variable_names $variable_names \
    --seed $seed \
    $force_flags \
    -y

  for if_num_hops in "${runtime_if_num_hops[@]}"; do
    run_name="${dag_run_name}_ifhops=${if_num_hops}"
    echo "=== tasks ${run_name} ==="

    uv run python -m data.generate_tasks \
      --input_path "$dag_dir" \
      --output_dir "$tasks_root" \
      --run_name "$run_name" \
      --input_run_name "$dag_run_name" \
      --seed $seed \
      -y \
      --program-args if_type="$runtime_if_type" num_branches="$runtime_num_branches" if_num_hops="$if_num_hops" if_breadth_depth_ratio="$runtime_breadth_depth_ratio"

    uv run python -m data.generate_test_cases \
      --tasks_dir "$tasks_root" \
      --output_dir "$test_cases_root" \
      --run_name "$run_name" \
      -y
  done
done
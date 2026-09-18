#!/bin/bash
# Generate fixed n=10 DAGs, then add-instructions tasks/test cases for each nc.

set -e

dir="$(cd "$(dirname "$0")" && pwd)"
lib_dir="$(cd "$dir" && while [ ! -d "_lib" ]; do cd ..; done && pwd)/_lib"
root_dir="$(cd "$lib_dir/../.." && pwd)"
eval "$(uv run python "$lib_dir/load_config.py" "$dir/config.yaml")"
cd "$root_dir"

constraint_count="${#constraint_num_constraints_buckets[@]}"
if [ "$constraint_count" -eq 0 ]; then
  constraint_num_constraints_buckets=("")
  constraint_count=1
fi

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

  for j in $(seq 0 $((constraint_count - 1))); do
    read -r num_constraints _ <<< "${constraint_num_constraints_buckets[$j]}"
    run_name="${run_names[$((i * constraint_count + j))]}"

    echo "=== tasks ${run_name} ==="

    program_args=(
      --program-args
      if_type=none
      "num_constraints=${num_constraints}"
      "num_params=${num_params:-5}"
    )

    uv run python -m data.generate_tasks \
      --input_path "$dag_dir" \
      --input_run_name "$dag_run_name" \
      --output_dir "$tasks_root" \
      --run_name "$run_name" \
      --seed $seed \
      --constraints \
      -y \
      "${program_args[@]}"

    uv run python -m data.generate_test_cases \
      --tasks_dir "$tasks_root" \
      --output_dir "$test_cases_root" \
      --run_name "$run_name" \
      --constraints \
      -y \
      "${program_args[@]}"
  done
done
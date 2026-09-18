#!/bin/bash
# Score responses across all runtime hop sweeps from config.yaml.

set -e

dir="$(cd "$(dirname "$0")" && pwd)"
lib_dir="$(cd "$dir" && while [ ! -d "_lib" ]; do cd ..; done && pwd)/_lib"
eval "$(uv run python "$lib_dir/load_config.py" "$dir/config.yaml")"

scored_models=()
for model in "${models[@]}"; do
  scored_models+=("code/${model}")
done
for model in "${copilot_models[@]}"; do
  scored_models+=("copilot/${model}")
done

repo_root="$(cd "$lib_dir/../.." && pwd)"

for run_name in "${run_names[@]}"; do
  task_dir="${tasks_root}/${run_name}"
  test_cases_dir="${test_cases_root}/${run_name}"

  echo "=== scoring ${run_name} ==="
  cd "$repo_root"
  uv run python -m analysis.score \
    --task-dir "$task_dir" \
    --test-cases-dir "$test_cases_dir" \
    --task-set-name "${task_set_names_arr[@]}" \
    --task-types "${task_types_arr[@]}" \
    --responses-dir "$response_dir" \
    --output-dir "$output_root" \
    --run-name "$run_name" \
    --models "${scored_models[@]}" \
    --n-parallel-tests 32 \
    --memoize \
    --overwrite -y
done
#!/bin/bash
# Run LLM scaffold (full-code response) across all add-instructions sweeps.

set -e

dir="$(cd "$(dirname "$0")" && pwd)"
lib_dir="$(cd "$dir" && while [ ! -d "_lib" ]; do cd ..; done && pwd)/_lib"
eval "$(uv run python "$lib_dir/load_config.py" "$dir/config.yaml")"

agent="llm"
return_type="code"
session_prefix="llm_${experiment_name}"

quoted_run_names=""
for rn in "${run_names[@]}"; do
  quoted_run_names+="'${rn}' "
done

quoted_task_sets=""
for ts in "${task_set_names_arr[@]}"; do
  quoted_task_sets+="'${ts}' "
done

for model_name in "${models[@]}"; do
  safe_model="${model_name//\//_}"
  safe_model="${safe_model//./_}"
  session="${session_prefix}_${safe_model}"

  cmd="echo '=== model=${model_name} ===' && \
uv run python -m model.run_cabra \
  --tasks-root '${tasks_root}' \
  --task-set-name ${quoted_task_sets} \
  --task-types ${task_types_arr[@]} \
  --agent '${agent}' \
  --model-name '${model_name}' \
  --response-dir '${response_dir}' \
  --run-names ${quoted_run_names} \
  --limit ${limit} \
  --n-parallel ${n_parallel} \
  --retry-errors \
  --agent-kwargs return_type=${return_type}"

  tmux kill-session -t "$session" 2>/dev/null || true
  tmux new-session -d -s "$session" "$cmd"
  echo "started tmux session: $session"
done

echo
echo "attach with: tmux attach -t <session>"
echo "list with:   tmux ls"
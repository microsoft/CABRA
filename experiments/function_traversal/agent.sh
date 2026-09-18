#!/bin/bash
# Run copilot agent scaffold across all distractor-code bucket sweeps.
# One tmux session per model; all run_names and task_set_names are passed in a
# single python invocation (n_parallel controls concurrency across them).
# Results land under ${response_dir}/<run_name>/<task_set>/...

set -e

dir="$(cd "$(dirname "$0")" && pwd)"
lib_dir="$(cd "$dir" && while [ ! -d "_lib" ]; do cd ..; done && pwd)/_lib"
eval "$(uv run python "$lib_dir/load_config.py" "$dir/config.yaml")"

agent="copilot"
session_prefix="agent_${experiment_name}"
tmux_debug="${TMUX_DEBUG:-false}"

quoted_run_names=""
for rn in "${run_names[@]}"; do
  quoted_run_names+="'${rn}' "
done

quoted_task_sets=""
for ts in "${task_set_names_arr[@]}"; do
  quoted_task_sets+="'${ts}' "
done

for model_name in "${copilot_models[@]}"; do
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
  --agent-kwargs timeout=1800 \
  --retry-errors"

  if [ "$tmux_debug" = "true" ]; then
    cmd="tmux set-option -w -t '$session' remain-on-exit on; $cmd"
  fi
  tmux kill-session -t "$session" 2>/dev/null || true
  tmux new-session -d -s "$session" "$cmd"
  echo "started tmux session: $session"
done

echo
echo "attach with: tmux attach -t <session>"
echo "list with:   tmux ls"
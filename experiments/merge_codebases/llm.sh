#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CONFIG_PATH="${CONFIG_PATH:-${SCRIPT_DIR}/config.yaml}"

eval "$(uv run python "${ROOT_DIR}/experiments/_lib/load_config.py" "${CONFIG_PATH}")"

tasks_root="${tasks_root:-local_data/tasks}"
if [[ "${tasks_root}" != /* ]]; then tasks_root="${ROOT_DIR}/${tasks_root}"; fi

response_dir="${response_dir:-local_data/responses}"
if [[ "${response_dir}" != /* ]]; then response_dir="${ROOT_DIR}/${response_dir}"; fi

prompt_file="${prompt_file:-data/tasks/merge_code/prompt.txt}"
if [[ "${prompt_file}" != /* ]]; then prompt_file="${ROOT_DIR}/${prompt_file}"; fi

if [[ ${#merge_code_run_names[@]} -eq 0 ]]; then
	merge_code_run_names=("${run_name:-testing}")
fi

if [[ ${#models[@]} -eq 0 ]]; then
	models=("openrouter/openai/gpt-5.4-mini")
fi

limit="${limit:-5}"
n_parallel="${n_parallel:-5}"
input_field="${input_field:-input}"
overwrite="${overwrite:-true}"
yes="${yes:-false}"
retry_errors="${retry_errors:-true}"
dry_run="${dry_run:-false}"

cd "${ROOT_DIR}"

session_prefix="llm_${experiment_name:-merge_code_sweep}"

for model_name in "${models[@]}"; do
	safe_model="${model_name//\//_}"
	safe_model="${safe_model//./_}"
	session="${session_prefix}_${safe_model}"

	cmd=(
		uv run python -m model.run_merge_code
		--tasks-root "${tasks_root}"
		--response-dir "${response_dir}"
		--prompt-file "${prompt_file}"
		--agent llm
		--model-name "${model_name}"
		--input-field "${input_field}"
		--n-parallel "${n_parallel}"
		--run-names
	)

	for current_run_name in "${merge_code_run_names[@]}"; do
		cmd+=("${current_run_name}")
	done

	cmd+=(--agent-kwargs return_type=code)

	if [[ -n "${limit}" ]]; then
		cmd+=(--limit "${limit}")
	fi

	if [[ "${overwrite}" == "true" ]]; then
		cmd+=(--overwrite)
	fi

	if [[ "${yes}" == "true" ]]; then
		cmd+=(-y)
	fi

	if [[ "${retry_errors}" == "true" ]]; then
		cmd+=(--retry-errors)
	fi

	if [[ "${dry_run}" == "true" ]]; then
		cmd+=(--dry-run)
	fi

	printf -v quoted_cmd '%q ' "${cmd[@]}"
	tmux kill-session -t "${session}" 2>/dev/null || true
	tmux new-session -d -s "${session}" "${quoted_cmd}"
	echo "started tmux session: ${session}"
done

echo
echo "attach with: tmux attach -t <session>"
echo "list with:   tmux ls"

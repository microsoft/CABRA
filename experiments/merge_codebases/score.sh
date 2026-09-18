#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CONFIG_PATH="${CONFIG_PATH:-${SCRIPT_DIR}/config.yaml}"

eval "$(uv run python "${ROOT_DIR}/experiments/_lib/load_config.py" "${CONFIG_PATH}")"

tasks_root="${tasks_root:-local_data/tasks}"
if [[ "${tasks_root}" != /* ]]; then tasks_root="${ROOT_DIR}/${tasks_root}"; fi

responses_dir="${response_dir:-local_data/responses}"
if [[ "${responses_dir}" != /* ]]; then responses_dir="${ROOT_DIR}/${responses_dir}"; fi

output_dir="${output_root:-local_data/results}"
if [[ "${output_dir}" != /* ]]; then output_dir="${ROOT_DIR}/${output_dir}"; fi

if [[ ${#merge_code_run_names[@]} -eq 0 ]]; then
	merge_code_run_names=("${run_name:-testing}")
fi

score_models=()
# Agent (copilot) responses live under `<run>/copilot/<model>.jsonl`.
for model_name in "${copilot_models[@]}"; do
	score_models+=("copilot/${model_name}")
done
# LLM responses live under `<run>/code/<model>.jsonl` (return_type=code).
for model_name in "${models[@]}"; do
	score_models+=("code/${model_name}")
done
if [[ ${#score_models[@]} -eq 0 ]]; then
	score_models=("copilot/claude-opus-4.8")
fi

limit="${limit:-}"
num_tests="${num_tests:-20}"
seed="${score_seed:-${merge_code_seed_values[0]:-42}}"
timeout_seconds="${timeout_seconds:-5}"
max_failures="${max_failures:-5}"
overwrite="true"
yes="true"

cd "${ROOT_DIR}"

for current_run_name in "${merge_code_run_names[@]}"; do
	args=(
		uv run python -m data.tasks.merge_code.score
		--tasks-root "${tasks_root}"
		--responses-dir "${responses_dir}"
		--output-dir "${output_dir}"
		--run-name "${current_run_name}"
		--models
	)

	for model in "${score_models[@]}"; do
		args+=("${model}")
	done

	if [[ -n "${limit}" ]]; then
		args+=(--limit "${limit}")
	fi

	args+=(
		--num-tests "${num_tests}"
		--seed "${seed}"
		--timeout-seconds "${timeout_seconds}"
		--max-failures "${max_failures}"
	)

	if [[ "${overwrite}" == "true" ]]; then
		args+=(--overwrite)
	fi

	if [[ "${yes}" == "true" ]]; then
		args+=(-y)
	fi

	"${args[@]}"
done
